"""Seeding is incremental: it backfills missing forms without a wipe."""

import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import web.seed as seed_mod
from web.conjugation import (
    INVARIABLE_PERSON,
    PAST_PARTICIPLE_TENSE,
    PRESENT_PARTICIPLE_TENSE,
)
from web.models import Base, Form, Verb
from web.seed import seed_verbs


def _write_seed(tmp_path, data):
    p = tmp_path / "verbs_seed.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'seed_test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_seed_is_incremental_and_idempotent(tmp_path, monkeypatch):
    Session = _session(tmp_path)

    v1 = [{"infinitive": "ir", "forms": {"present": {"eu": "vou", "tu": "vais"}}}]
    monkeypatch.setattr(seed_mod, "SEED_FILE", _write_seed(tmp_path, v1))

    with Session() as db:
        assert seed_verbs(db) == 2  # both present forms inserted
    with Session() as db:
        assert seed_verbs(db) == 0  # re-run inserts nothing

    # Grow the seed with a brand-new tense on the same verb.
    v2 = [
        {
            "infinitive": "ir",
            "forms": {
                "present": {"eu": "vou", "tu": "vais"},
                "imperative": {"tu": "vai"},
            },
        }
    ]
    monkeypatch.setattr(seed_mod, "SEED_FILE", _write_seed(tmp_path, v2))

    with Session() as db:
        assert seed_verbs(db) == 1  # only the new imperative form
        keys = {(f.tense, f.person) for f in db.scalars(select(Form)).all()}
        assert ("imperative", "tu") in keys
        assert len(keys) == 3


def test_participles_become_form_rows(tmp_path, monkeypatch):
    Session = _session(tmp_path)
    monkeypatch.setattr(
        seed_mod,
        "SEED_FILE",
        _write_seed(
            tmp_path,
            [{
                "infinitive": "ir",
                "past_participle": "ido",
                "present_participle": "indo",
                "forms": {},
            }],
        ),
    )
    with Session() as db:
        assert seed_verbs(db) == 2  # the two participles, as forms
        keys = {(f.tense, f.person, f.form_text) for f in db.scalars(select(Form)).all()}
        assert (PAST_PARTICIPLE_TENSE, INVARIABLE_PERSON, "ido") in keys
        assert (PRESENT_PARTICIPLE_TENSE, INVARIABLE_PERSON, "indo") in keys
    # Re-running inserts nothing (idempotent), and the column is set too.
    with Session() as db:
        assert seed_verbs(db) == 0
        verb = db.scalar(select(Verb).where(Verb.infinitive == "ir"))
        assert verb.past_participle == "ido"


def test_blank_cells_are_skipped(tmp_path, monkeypatch):
    Session = _session(tmp_path)
    monkeypatch.setattr(
        seed_mod,
        "SEED_FILE",
        _write_seed(
            tmp_path,
            [{
                "infinitive": "ir",
                "present_participle": "   ",  # whitespace-only: not a real form
                "forms": {
                    "future_indicative": {"eu": "irei", "tu": "", "ele": "  "},
                },
            }],
        ),
    )
    with Session() as db:
        assert seed_verbs(db) == 1  # only the non-blank "irei"
        rows = db.scalars(select(Form)).all()
        assert {(f.tense, f.person) for f in rows} == {("future_indicative", "eu")}
