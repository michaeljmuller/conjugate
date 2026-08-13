"""The add-a-verb endpoint and its background job, end to end.

Neither cplp.org nor the model is contacted: the language adapter and the `llm`
calls are stubbed, so what's under test is validation, the job lifecycle, and
what actually lands in the database.
"""

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from web import api as api_mod
from web import jobs
from web.auth import current_user
from web.languages import NotAVerb, UnknownWord
from web.languages.base import Cell, Paradigm
from web.languages.regular import regular_forms
from web.db import get_db
from web.main import app
from web.models import Base, Form, User, Verb

def _paradigm(infinitive="partir"):
    """A small but structurally complete paradigm: a cell with alternatives, a
    stored-but-never-drilled vós, and both participle rows."""
    return Paradigm(
        infinitive=infinitive,
        cells={
            ("present_indicative", "eu"): Cell(("parto",)),
            ("present_indicative", "tu"): Cell(("partes",)),
            ("present_indicative", "vos"): Cell(("partis",)),
            ("preterite", "eu"): Cell(("parti",)),
            ("present_subjunctive", "eu"): Cell(("oiça", "ouça")),
            ("past_participle", "inv"): Cell(("partido",)),
            ("past_participle", "short"): Cell(("partido",)),
            ("present_participle", "inv"): Cell(("partindo",)),
        },
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A client wired to a throwaway SQLite DB, with the network stubbed out."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'add.db'}",
        # _save runs in a worker thread, so its connection is not the one that
        # created the schema.
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine)
    with TS() as db:
        user = User(google_sub="t", email="t@example.com", name="T")
        db.add(user)
        db.commit()
        user_obj = db.get(User, user.id)
        db.expunge(user_obj)

    def override_db():
        db = TS()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: user_obj
    monkeypatch.setattr(jobs, "SessionLocal", TS)
    # A key is required to add a verb at all, so pretend there is one and stub
    # the generation itself. Tests that care about the no-key path unset it.
    monkeypatch.setattr(jobs.llm, "is_configured", lambda: True)
    monkeypatch.setattr(api_mod.llm, "is_configured", lambda: True)

    async def _examples(paradigm, **kw):
        result = jobs.llm.ExampleResult(translation=None)
        for (tense, person) in paradigm.cells:
            result.pairs[(tense, person)] = jobs.llm.ExamplePair(
                tense=tense, person=person, example_en="An example.", example_pt="Um exemplo.",
            )
        return result

    monkeypatch.setattr(jobs.llm, "generate_examples", _examples)

    yield TestClient(app), TS
    app.dependency_overrides.clear()


def _stub_lookup(monkeypatch, error=None):
    """Stand in for the adapter so no test touches cplp.org."""
    class _Adapter:
        code = "pt-PT"

        async def paradigm(self, infinitive):
            if error:
                raise error
            return _paradigm(infinitive)

    monkeypatch.setattr(jobs, "get_adapter", lambda *a, **k: _Adapter())


def _confirmed(client, infinitive):
    """Start a job past the confirmation.

    Every add now stops after the lookup to report what it found, so a test
    about anything later has to answer yes up front.
    """
    return client.post("/api/verbs", json={"infinitive": infinitive, "force": True})


def _await_job(client, job_id, timeout=10.0):
    """Poll until the job leaves `running`. Polling also yields to the loop so
    the background task gets to run between requests."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/verbs/jobs/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} never finished: {job}")


# ---- validation ----------------------------------------------------------

@pytest.mark.parametrize("bad", ["", "  ", "two words", "ab3", "x", "-"])
def test_rejects_non_words(env, bad):
    client, _ = env
    assert client.post("/api/verbs", json={"infinitive": bad}).status_code == 400


def test_accepts_accented_infinitive(env, monkeypatch):
    client, _ = env
    _stub_lookup(monkeypatch)
    assert client.post("/api/verbs", json={"infinitive": "pôr"}).status_code == 202


def test_duplicate_verb_is_rejected(env, monkeypatch):
    client, TS = env
    with TS() as db:
        db.add(Verb(infinitive="partir"))
        db.commit()
    _stub_lookup(monkeypatch)

    r = client.post("/api/verbs", json={"infinitive": " Partir "})
    assert r.status_code == 409
    assert "already" in r.json()["detail"]


# ---- the happy path ------------------------------------------------------

def test_job_saves_verb_with_forms_and_ownership(env, monkeypatch):
    client, TS = env
    _stub_lookup(monkeypatch)

    started = _confirmed(client, "partir")
    assert started.status_code == 202
    job = _await_job(client, started.json()["job_id"])
    assert job["status"] == "done", job

    with TS() as db:
        verb = db.scalar(select(Verb).where(Verb.infinitive == "partir"))
        assert verb is not None
        assert job["verb_id"] == verb.id
        assert verb.created_by is not None  # the column that was never written before
        forms = {(f.tense, f.person): f.form_text for f in verb.forms}

    assert forms[("present_indicative", "eu")] == "parto"
    assert forms[("present_indicative", "vos")] == "partis"  # stored, never drilled
    assert forms[("past_participle", "inv")] == "partido"
    assert forms[("present_participle", "inv")] == "partindo"


def test_without_an_api_key_the_request_is_refused_outright(env, monkeypatch):
    """No key means no example sentences, and a verb whose rows have no prompt
    is not worth adding — so it is refused before the lookup, not after."""
    client, TS = env
    _stub_lookup(monkeypatch)
    monkeypatch.setattr(api_mod.llm, "is_configured", lambda: False)

    r = client.post("/api/verbs", json={"infinitive": "partir"})
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]

    with TS() as db:
        assert db.scalar(select(Verb).where(Verb.infinitive == "partir")) is None


def test_a_failure_writing_examples_saves_nothing(env, monkeypatch):
    """Rejected key, exhausted credit, an outage — the job fails and the
    catalogue is left untouched, rather than gaining a verb with blank prompts."""
    client, TS = env
    _stub_lookup(monkeypatch)

    async def boom(paradigm, **kw):
        raise jobs.llm.ExamplesUnavailable("The Anthropic account cannot be billed: no credit.")

    monkeypatch.setattr(jobs.llm, "generate_examples", boom)

    job = _await_job(client, _confirmed(client, "partir").json()["job_id"])
    steps = {s["key"]: s for s in job["steps"]}

    assert job["status"] == "failed"
    assert "cannot be billed" in job["error"]
    assert steps["save"]["status"] == "pending"
    with TS() as db:
        assert db.scalar(select(Verb).where(Verb.infinitive == "partir")) is None


def test_examples_and_translation_are_applied(env, monkeypatch):
    client, TS = env
    _stub_lookup(monkeypatch)

    async def fake_generate(paradigm, **kw):
        result = jobs.llm.ExampleResult(translation="to leave")
        result.pairs[("present_indicative", "eu")] = jobs.llm.ExamplePair(
            tense="present_indicative", person="eu",
            example_en="I leave at eight.", example_pt="Parto às oito.",
        )
        return result

    monkeypatch.setattr(jobs.llm, "generate_examples", fake_generate)
    monkeypatch.setattr(jobs.llm, "is_configured", lambda: True)

    job = _await_job(client, _confirmed(client, "partir").json()["job_id"])
    assert job["status"] == "done"

    with TS() as db:
        verb = db.scalar(select(Verb).where(Verb.infinitive == "partir"))
        assert verb.translation == "to leave"
        by_key = {(f.tense, f.person): f for f in verb.forms}
        assert by_key[("present_indicative", "eu")].example_pt == "Parto às oito."


def test_alternative_forms_are_stored_and_served(env, monkeypatch):
    """A cell with more than one valid form keeps them all, and the drill ships
    them so the client can grade and offer them."""
    client, TS = env
    _stub_lookup(monkeypatch)

    job = _await_job(client, _confirmed(client, "partir").json()["job_id"])

    with TS() as db:
        verb = db.scalar(select(Verb).where(Verb.infinitive == "partir"))
        cell = {(f.tense, f.person): f for f in verb.forms}[("present_subjunctive", "eu")]
        assert cell.form_text == "oiça"
        assert [v.text for v in cell.variants] == ["ouça"]
        assert cell.accepted == ["oiça", "ouça"]

    rows = client.get(f"/api/verbs/{job['verb_id']}/forms").json()["blocks"]
    subjunctive = next(b for b in rows if b["tense"] == "present_subjunctive")
    row = next(r for r in subjunctive["rows"] if r["person"] == "eu")
    assert row["answer"] == "oiça"
    assert row["variants"] == ["ouça"]


def test_both_participle_rows_are_drilled(env, monkeypatch):
    client, TS = env
    _stub_lookup(monkeypatch)
    job = _await_job(client, _confirmed(client, "partir").json()["job_id"])

    blocks = client.get(f"/api/verbs/{job['verb_id']}/forms").json()["blocks"]
    participle = next(b for b in blocks if b["tense"] == "past_participle")
    assert [(r["person"], r["label"]) for r in participle["rows"]] == [
        ("inv", "ter / haver"),
        ("short", "ser / estar"),
    ]


# ---- failure -------------------------------------------------------------

def test_unknown_verb_fails_the_step_and_writes_nothing(env, monkeypatch):
    client, TS = env
    _stub_lookup(monkeypatch, error=UnknownWord("zzzz"))

    job = _await_job(client, _confirmed(client, "zzzz").json()["job_id"])
    steps = {s["key"]: s for s in job["steps"]}

    assert job["status"] == "failed"
    assert steps["look_up"]["status"] == "failed"
    assert "No European-Portuguese verb" in job["error"]
    assert steps["save"]["status"] == "pending"

    with TS() as db:
        assert db.scalar(select(Verb).where(Verb.infinitive == "zzzz")) is None
        assert db.scalars(select(Form)).all() == []


def test_a_non_verb_is_rejected(env, monkeypatch):
    client, TS = env
    _stub_lookup(monkeypatch, error=NotAVerb("mesa"))

    job = _await_job(client, _confirmed(client, "mesa").json()["job_id"])
    assert job["status"] == "failed"
    assert "is not a verb" in job["error"]
    with TS() as db:
        assert db.scalar(select(Verb).where(Verb.infinitive == "mesa")) is None


def test_unknown_job_id_is_404(env):
    client, _ = env
    assert client.get("/api/verbs/jobs/nope").status_code == 404


# ---- the confirmation ----------------------------------------------------

def _regular_paradigm(infinitive="falar"):
    """A verb with nothing but predictable forms, built from the same ending
    table the check uses."""
    return Paradigm(
        infinitive=infinitive,
        cells={key: Cell((form,)) for key, form in regular_forms(infinitive).items()},
    )


def _stub_regular_lookup(monkeypatch):
    class _Adapter:
        code = "pt-PT"

        async def paradigm(self, infinitive):
            return _regular_paradigm(infinitive)

    monkeypatch.setattr(jobs, "get_adapter", lambda *a, **k: _Adapter())


def test_the_confirmation_comes_before_the_expensive_half(env, monkeypatch):
    client, TS = env
    _stub_regular_lookup(monkeypatch)

    called = []

    async def _never(paradigm, **kw):
        called.append(paradigm.infinitive)
        raise AssertionError("examples must not be written before the user says yes")

    monkeypatch.setattr(jobs.llm, "generate_examples", _never)

    job = _await_job(client, client.post("/api/verbs", json={"infinitive": "falar"}).json()["job_id"])

    assert job["status"] == "needs_confirmation"
    assert called == []
    steps = {s["key"]: s for s in job["steps"]}
    assert steps["look_up"]["status"] == "done"  # the lookup itself succeeded
    assert steps["draft"]["status"] == "pending"
    with TS() as db:
        assert db.scalar(select(Verb).where(Verb.infinitive == "falar")) is None


def test_a_plainly_regular_verb_says_so(env, monkeypatch):
    client, _ = env
    _stub_regular_lookup(monkeypatch)

    job = _await_job(client, client.post("/api/verbs", json={"infinitive": "falar"}).json()["job_id"])
    assert job["question"] == "falar is a regular verb. Add it?"


def test_a_spelling_change_is_named_rather_than_hidden(env, monkeypatch):
    """`jogar` is entirely predictable but respells its stem throughout, which
    is worth saying out loud rather than filing under plain "regular"."""
    client, _ = env
    _stub_regular_lookup(monkeypatch)

    job = _await_job(client, client.post("/api/verbs", json={"infinitive": "jogar"}).json()["job_id"])
    assert job["question"] == (
        "jogar is regular, apart from a spelling change: g → gu before e "
        "(jogue, joguei). Add it?"
    )


def test_an_irregular_verb_is_confirmed_too(env, monkeypatch):
    """Confirmation is not a warning: it reports on every verb, including the
    ones most worth adding."""
    client, _ = env
    _stub_lookup(monkeypatch)  # `partir` stub, which carries an oiça/ouça cell

    job = _await_job(client, client.post("/api/verbs", json={"infinitive": "partir"}).json()["job_id"])

    assert job["status"] == "needs_confirmation"
    assert job["question"] == "partir is an irregular verb. Add it?"


def test_saying_yes_adds_the_verb(env, monkeypatch):
    client, TS = env
    _stub_regular_lookup(monkeypatch)

    job = _await_job(
        client,
        client.post("/api/verbs", json={"infinitive": "jogar", "force": True}).json()["job_id"],
    )

    assert job["status"] == "done", job
    with TS() as db:
        verb = db.scalar(select(Verb).where(Verb.infinitive == "jogar"))
        assert verb is not None
        forms = {(f.tense, f.person): f.form_text for f in verb.forms}
    assert forms[("present_subjunctive", "eu")] == "jogue"  # the spelling rule survived


def test_confirming_skips_straight_to_the_work(env, monkeypatch):
    client, _ = env
    _stub_lookup(monkeypatch)

    job = _await_job(client, _confirmed(client, "partir").json()["job_id"])

    assert job["status"] == "done"
    assert job["question"] == ""
