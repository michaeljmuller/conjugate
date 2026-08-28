"""Reviewing a verb's example sentences: list, propose, accept.

The model is stubbed — what's under test is that a proposal is never written
until someone accepts it, that only the accepted ones land, and that the
sentences come from the job rather than from whatever the client sends back.
"""

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from web import api as api_mod
from web import jobs
from web.auth import current_user
from web.db import get_db
from web.languages import INVARIABLE_PERSON
from web.llm import Proposal, ReviseResult, SlotProblem
from web.main import app
from web.models import Base, Form, FormVariant, User, Verb

# The verb every test reviews: two ordinary cells and one with an alternative,
# so paradigm_from_verb has something to carry back.
_FORMS = [
    ("present_indicative", "eu", "corro", ["corr0"], "I run.", "Corro."),
    ("preterite", "eu", "corri", [], "I ran.", "Corri."),
    ("past_participle", INVARIABLE_PERSON, "corrido", [], "I have run.", "Tenho corrido."),
]


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'review.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine)
    with TS() as db:
        user = User(google_sub="t", email="t@example.com", name="T")
        db.add(user)
        verb = Verb(infinitive="correr", translation="to run")
        for tense, person, text, variants, en, pt in _FORMS:
            form = Form(
                tense=tense, person=person, form_text=text, example_en=en, example_pt=pt
            )
            form.variants = [FormVariant(text=v) for v in variants]
            verb.forms.append(form)
        db.add(verb)
        db.commit()
        user_obj, verb_id = db.get(User, user.id), verb.id
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
    monkeypatch.setattr(api_mod.llm, "is_configured", lambda: True)

    yield TestClient(app), TS, verb_id
    app.dependency_overrides.clear()


def _stub_revision(monkeypatch, proposals, unresolved=()):
    async def _revise(paradigm, adapter, **kw):
        _revise.seen = kw
        return ReviseResult(proposals=list(proposals), unresolved=list(unresolved))

    monkeypatch.setattr(jobs.llm, "revise_examples", _revise)
    return _revise


def _await_job(client, job_id, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/verbs/jobs/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("job never finished")


def _proposal(tense="preterite", person="eu", form="corri"):
    return Proposal(
        tense=tense, person=person, form=form, reason="could be present or past",
        before_en="I ran.", before_native="Corri.",
        after_en="Yesterday I ran 5 km.", after_native="Ontem corri 5 km.",
    )


# ---- listing -------------------------------------------------------------

def test_listing_returns_every_sentence_with_its_form(env):
    client, _, verb_id = env
    body = client.get(f"/api/verbs/{verb_id}/examples").json()

    assert body["infinitive"] == "correr"
    rows = [r for b in body["blocks"] for r in b["rows"]]
    by_key = {(r["tense"], r["person"]): r for r in rows}
    assert by_key[("preterite", "eu")]["example_native"] == "Corri."
    assert by_key[("preterite", "eu")]["form"] == "corri"


def test_listing_ignores_the_users_disabled_tenses(env):
    """You are editing the verb's data, not drilling it: a tense you switched
    off still has sentences someone else will be shown."""
    client, _, verb_id = env
    client.put("/api/settings", json={"tenses": [
        {"key": "present_indicative", "enabled": True},
        {"key": "preterite", "enabled": False},
    ]})

    body = client.get(f"/api/verbs/{verb_id}/examples").json()
    tenses = {b["key"] for b in body["blocks"]}
    assert "preterite" in tenses
    # The drill, in contrast, drops it.
    drill = client.get(f"/api/verbs/{verb_id}/forms").json()
    assert "preterite" not in {b["tense"] for b in drill["blocks"]}


def test_listing_hides_a_redundant_short_participle(env):
    """The panel offers exactly the rows the drill renders."""
    client, TS, verb_id = env
    with TS() as db:
        verb = db.get(Verb, verb_id)
        verb.forms.append(Form(
            tense="past_participle", person="short", form_text="corrido",
        ))
        db.commit()

    body = client.get(f"/api/verbs/{verb_id}/examples").json()
    persons = {(r["tense"], r["person"]) for b in body["blocks"] for r in b["rows"]}
    assert ("past_participle", "short") not in persons


# ---- proposing -----------------------------------------------------------

def test_revise_needs_something_to_go_on(env):
    client, _, verb_id = env
    r = client.post(f"/api/verbs/{verb_id}/examples/revise", json={})
    assert r.status_code == 400


def test_revise_without_an_api_key_is_refused(env, monkeypatch):
    client, _, verb_id = env
    monkeypatch.setattr(api_mod.llm, "is_configured", lambda: False)
    r = client.post(
        f"/api/verbs/{verb_id}/examples/revise", json={"comment": "check the tenses"}
    )
    assert r.status_code == 503


def test_a_proposal_is_not_written_until_it_is_accepted(env, monkeypatch):
    client, TS, verb_id = env
    _stub_revision(monkeypatch, [_proposal()])

    job = _await_job(client, client.post(
        f"/api/verbs/{verb_id}/examples/revise",
        json={"comments": [{"tense": "preterite", "person": "eu", "comment": "vague"}]},
    ).json()["job_id"])

    assert job["status"] == "done"
    assert len(job["proposals"]) == 1
    # Still the old sentence: proposing changes nothing.
    with TS() as db:
        form = db.scalar(select(Form).where(Form.tense == "preterite"))
        assert form.example_pt == "Corri."


def test_the_comment_reaches_the_model_keyed_by_slot(env, monkeypatch):
    client, _, verb_id = env
    spy = _stub_revision(monkeypatch, [])

    _await_job(client, client.post(
        f"/api/verbs/{verb_id}/examples/revise",
        json={
            "comments": [{"tense": "preterite", "person": "eu", "comment": "add yesterday"}],
            "comment": "check every tense",
        },
    ).json()["job_id"])

    assert spy.seen["comments"] == {("preterite", "eu"): "add yesterday"}
    assert spy.seen["batch_comment"] == "check every tense"
    # The sentences already on the verb are what the model is asked to improve.
    assert spy.seen["current"][("preterite", "eu")].example_native == "Corri."


# ---- accepting -----------------------------------------------------------

def _propose(client, monkeypatch, verb_id, proposals):
    _stub_revision(monkeypatch, proposals)
    return _await_job(client, client.post(
        f"/api/verbs/{verb_id}/examples/revise", json={"comment": "check the tenses"},
    ).json()["job_id"])


def test_only_the_accepted_slots_are_written(env, monkeypatch):
    client, TS, verb_id = env
    job = _propose(client, monkeypatch, verb_id, [
        _proposal(),
        _proposal(tense="present_indicative", form="corro"),
    ])

    r = client.post(f"/api/verbs/{verb_id}/examples/apply", json={
        "job_id": job["job_id"],
        "accept": [{"tense": "preterite", "person": "eu"}],
    })
    assert r.status_code == 200

    with TS() as db:
        by_tense = {f.tense: f for f in db.get(Verb, verb_id).forms}
        assert by_tense["preterite"].example_pt == "Ontem corri 5 km."
        assert by_tense["present_indicative"].example_pt == "Corro."  # rejected


def test_rejecting_everything_writes_nothing(env, monkeypatch):
    client, TS, verb_id = env
    job = _propose(client, monkeypatch, verb_id, [_proposal()])

    body = client.post(f"/api/verbs/{verb_id}/examples/apply", json={
        "job_id": job["job_id"], "accept": [],
    }).json()

    assert body["applied"] == 0
    with TS() as db:
        assert db.scalar(select(Form).where(Form.tense == "preterite")).example_pt == "Corri."


def test_the_client_cannot_supply_its_own_sentence(env, monkeypatch):
    """Only the slot is sent back; the text comes from the job."""
    client, TS, verb_id = env
    job = _propose(client, monkeypatch, verb_id, [_proposal()])

    client.post(f"/api/verbs/{verb_id}/examples/apply", json={
        "job_id": job["job_id"],
        "accept": [{"tense": "preterite", "person": "eu",
                    "after_native": "Qualquer coisa."}],
    })

    with TS() as db:
        form = db.scalar(select(Form).where(Form.tense == "preterite"))
        assert form.example_pt == "Ontem corri 5 km."


def test_accepting_a_slot_that_was_never_proposed_does_nothing(env, monkeypatch):
    client, TS, verb_id = env
    job = _propose(client, monkeypatch, verb_id, [_proposal()])

    body = client.post(f"/api/verbs/{verb_id}/examples/apply", json={
        "job_id": job["job_id"],
        "accept": [{"tense": "future_indicative", "person": "eu"}],
    }).json()
    assert body["applied"] == 0


def test_an_expired_review_says_so(env):
    client, _, verb_id = env
    r = client.post(f"/api/verbs/{verb_id}/examples/apply", json={
        "job_id": "nosuchjob", "accept": [],
    })
    assert r.status_code == 404


def test_a_review_cannot_be_applied_to_another_verb(env, monkeypatch):
    client, TS, verb_id = env
    job = _propose(client, monkeypatch, verb_id, [_proposal()])
    with TS() as db:
        other = Verb(infinitive="falar")
        other.forms.append(Form(tense="preterite", person="eu", form_text="falei"))
        db.add(other)
        db.commit()
        other_id = other.id

    r = client.post(f"/api/verbs/{other_id}/examples/apply", json={
        "job_id": job["job_id"], "accept": [{"tense": "preterite", "person": "eu"}],
    })
    assert r.status_code == 400
