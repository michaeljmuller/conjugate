"""The seed-file export: what it builds, and who is allowed to ask for it.

Startup seeding fills blanks only now, so the database outruns the committed
files. This is the path back — it has to produce something that can be written
straight over those files and committed.
"""

import importlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web import export
from web.db import get_db
from web.languages import INVARIABLE_PERSON
from web.main import app
from web.models import Base, Form, FormVariant, User, Verb


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'export.db'}")
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine)
    with TS() as db:
        verb = Verb(infinitive="ouvir", translation="to hear")
        eu = Form(
            tense="present_indicative", person="eu", form_text="oiço",
            example_en="I hear the rain.", example_pt="Oiço a chuva.",
        )
        eu.variants = [FormVariant(text="ouço")]
        verb.forms.append(eu)
        verb.forms.append(Form(
            tense="preterite", person="eu", form_text="ouvi",
            example_en="I heard it yesterday.", example_pt="Ouvi ontem.",
        ))
        # No sentence yet: it belongs in the paradigm but not in examples.json.
        verb.forms.append(Form(
            tense="past_participle", person=INVARIABLE_PERSON, form_text="ouvido"
        ))
        verb.forms.append(Form(
            tense="past_participle", person="short", form_text="ouvido"
        ))
        db.add(verb)
        db.commit()
    with TS() as db:
        yield db


def test_seed_entry_keeps_alternatives_and_participles(db_session):
    [entry] = export.verbs_seed(db_session)

    assert entry["infinitive"] == "ouvir"
    assert entry["translation"] == "to hear"
    # A cell with alternatives is a list, answer first.
    assert entry["forms"]["present_indicative"]["eu"] == ["oiço", "ouço"]
    assert entry["forms"]["preterite"]["eu"] == "ouvi"
    assert entry["past_participle"] == "ouvido"
    # Both participle rows hold the same form, so no second field is written.
    assert "past_participle_short" not in entry


def test_a_distinct_short_participle_is_written(db_session):
    verb = db_session.query(Verb).one()
    short = next(f for f in verb.forms if f.person == "short")
    short.form_text = "aceite"
    db_session.commit()

    [entry] = export.verbs_seed(db_session)
    assert entry["past_participle_short"] == "aceite"


def test_examples_carry_the_prompt_material_across(db_session, tmp_path):
    """_instructions and _guidance live only in the file and must survive."""
    packaged = tmp_path / "examples.json"
    packaged.write_text(
        '{"_instructions": "Fill both fields.", "_guidance": {"variety": "pt-PT"},'
        ' "verbs": [{"infinitive": "stale"}]}',
        encoding="utf-8",
    )

    out = export.examples(db_session, examples_file=packaged)
    assert out["_instructions"] == "Fill both fields."
    assert out["_guidance"] == {"variety": "pt-PT"}
    # The verbs come from the database, not from the file it read them beside.
    assert [v["infinitive"] for v in out["verbs"]] == ["ouvir"]


def test_only_forms_with_a_sentence_are_exported(db_session):
    [entry] = export.examples(db_session)["verbs"]
    keys = {(f["tense"], f["person"]) for f in entry["forms"]}

    assert ("present_indicative", "eu") in keys
    assert ("past_participle", INVARIABLE_PERSON) not in keys  # no sentence


def test_output_is_serialized_like_the_committed_files(db_session):
    text = export.as_json(export.verbs_seed(db_session))
    assert text.endswith("\n")
    assert "oiço" in text              # not \u escaped
    assert '\n  {\n' in text           # indent=2


# ---- the endpoint --------------------------------------------------------

@pytest.fixture
def client(db_session, monkeypatch):
    monkeypatch.setenv("EXPORT_USER", "robot")
    monkeypatch.setenv("EXPORT_PASSWORD", "s3cret")
    import web.export_api as export_api
    importlib.reload(export_api)   # credentials are read at import

    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app), export_api
    app.dependency_overrides.clear()
    importlib.reload(export_api)


def _get(client, path, **kw):
    return client.get(path, **kw)


def test_export_needs_credentials(client):
    c, _ = client
    assert _get(c, "/export/verbs_seed.json").status_code == 401
    assert _get(c, "/export/verbs_seed.json", auth=("robot", "wrong")).status_code == 401
    assert _get(c, "/export/verbs_seed.json", auth=("nobody", "s3cret")).status_code == 401


def test_export_serves_the_file_body(client):
    c, _ = client
    r = _get(c, "/export/verbs_seed.json", auth=("robot", "s3cret"))

    assert r.status_code == 200
    assert r.json()[0]["infinitive"] == "ouvir"
    assert r.headers["cache-control"] == "no-store"


def test_examples_endpoint_serves_the_other_file(client):
    c, _ = client
    r = _get(c, "/export/examples.json", auth=("robot", "s3cret"))

    assert r.status_code == 200
    assert "_guidance" in r.json()
    assert r.json()["verbs"][0]["infinitive"] == "ouvir"


def test_unconfigured_export_does_not_admit_it_exists(db_session, monkeypatch):
    """404, not 401: an endpoint that is switched off should look absent."""
    monkeypatch.delenv("EXPORT_USER", raising=False)
    monkeypatch.delenv("EXPORT_PASSWORD", raising=False)
    import web.export_api as export_api
    importlib.reload(export_api)

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        c = TestClient(app)
        assert c.get("/export/verbs_seed.json").status_code == 404
        assert c.get("/export/verbs_seed.json", auth=("robot", "s3cret")).status_code == 404
    finally:
        app.dependency_overrides.clear()
        importlib.reload(export_api)


def test_export_follows_the_committed_file_order(db_session, tmp_path):
    """A re-export must diff as the sentences that changed, not as a reshuffle.

    The files were curated in a deliberate order (ser first, not abrir), so
    sorting alphabetically would rewrite every line of a 2000-line file to carry
    one corrected sentence.
    """
    with db_session.no_autoflush:
        for name in ("abrir", "ser"):
            db_session.add(Verb(infinitive=name))
        db_session.commit()

    seed_file = tmp_path / "verbs_seed.json"
    seed_file.write_text(
        '[{"infinitive": "ser"}, {"infinitive": "ouvir"}]', encoding="utf-8"
    )

    order = [e["infinitive"] for e in export.verbs_seed(db_session, seed_file=seed_file)]
    # The file's order first, then anything it has never heard of.
    assert order == ["ser", "ouvir", "abrir"]


def test_a_verb_missing_from_the_file_still_exports(db_session, tmp_path):
    """The file is a hint about order, not a filter on content."""
    empty = tmp_path / "verbs_seed.json"
    empty.write_text("[]", encoding="utf-8")

    assert [e["infinitive"] for e in export.verbs_seed(db_session, seed_file=empty)] == ["ouvir"]
