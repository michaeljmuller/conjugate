"""Seeding is incremental: it backfills missing forms without a wipe."""

import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import web.seed as seed_mod
from web.languages.pt.catalogue import (
    INVARIABLE_PERSON,
    PAST_PARTICIPLE_TENSE,
    PRESENT_PARTICIPLE_TENSE,
    SHORT_PERSON,
)
from web.models import Base, Form, FormVariant, Verb
from web.languages import get_adapter
from web.languages.base import Cell, Paradigm
from web.seed import (
    apply_examples,
    paradigm_from_entry,
    seed_verbs,
    upsert_verb,
)

ADAPTER = get_adapter()


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
        # Three rows: the past participle is drilled twice (with ter/haver and
        # with ser/estar), which for a verb with one participle is the same form.
        assert seed_verbs(db) == 3
        keys = {(f.tense, f.person, f.form_text) for f in db.scalars(select(Form)).all()}
        assert (PAST_PARTICIPLE_TENSE, INVARIABLE_PERSON, "ido") in keys
        assert (PAST_PARTICIPLE_TENSE, SHORT_PERSON, "ido") in keys
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


# ---- upsert_verb / apply_examples, shared with the add-a-verb flow -------

def test_upsert_verb_records_owner_and_translation(tmp_path):
    """Fields the seeder never sets, but a verb added in the app does."""
    Session = _session(tmp_path)
    entry = {
        "infinitive": "partir",
        "translation": "to leave",
        "past_participle": "partido",
        "forms": {"present_indicative": {"eu": "parto"}},
    }
    with Session() as db:
        verb, inserted = upsert_verb(db, paradigm_from_entry(entry), adapter=ADAPTER, created_by=7)
        db.commit()
        assert inserted == 3  # the present form plus both participle rows
        assert verb.created_by == 7
        assert verb.translation == "to leave"


def test_upsert_verb_never_overwrites_existing_form_text(tmp_path):
    """Startup seeding must not clobber a verb that was added — or corrected —
    through the app."""
    Session = _session(tmp_path)
    with Session() as db:
        upsert_verb(
            db,
            paradigm_from_entry({"infinitive": "ir", "forms": {"present": {"eu": "vou"}}}),
            adapter=ADAPTER,
        )
        db.commit()
    with Session() as db:
        # A later entry disagrees about the same cell.
        _, inserted = upsert_verb(
            db,
            paradigm_from_entry({"infinitive": "ir", "forms": {"present": {"eu": "XXX"}}}),
            adapter=ADAPTER,
        )
        db.commit()
        assert inserted == 0
        assert db.scalar(select(Form)).form_text == "vou"


def test_apply_examples_fills_only_matching_slots(tmp_path):
    Session = _session(tmp_path)
    with Session() as db:
        verb, _ = upsert_verb(
            db,
            paradigm_from_entry({"infinitive": "ir", "forms": {"present": {"eu": "vou"}}}),
            adapter=ADAPTER,
        )
        db.flush()
        updated = apply_examples(
            verb,
            [
                {"tense": "present", "person": "eu",
                 "example_en": "I go home.", "example_pt": "Vou para casa."},
                # No such form: ignored rather than an error.
                {"tense": "present", "person": "vos",
                 "example_en": "x", "example_pt": "y"},
                # Blank values never wipe what's there.
                {"tense": "present", "person": "eu", "example_en": "", "example_pt": ""},
            ],
        )
        db.commit()
        assert updated == 2  # the two columns of the one matching slot
        form = db.scalar(select(Form))
        assert form.example_en == "I go home."
        assert form.example_pt == "Vou para casa."


def test_upsert_verb_stores_alternative_forms(tmp_path):
    """A cell with several valid forms keeps them all — one displayed, the rest
    as variants that grade as correct."""
    Session = _session(tmp_path)
    paradigm = Paradigm(
        infinitive="ouvir",
        cells={
            ("present_indicative", "eu"): Cell(("oiço", "ouça")),
            ("preterite", "eu"): Cell(("ouvi",)),
        },
    )
    with Session() as db:
        verb, inserted = upsert_verb(db, paradigm, adapter=ADAPTER)
        db.commit()
        assert inserted == 2
        by_key = {(f.tense, f.person): f for f in verb.forms}
        assert by_key[("present_indicative", "eu")].accepted == ["oiço", "ouça"]
        assert by_key[("preterite", "eu")].accepted == ["ouvi"]


def test_seed_cells_accept_alternatives(tmp_path, monkeypatch):
    """A list-valued cell seeds its alternatives, which all grade as correct.

    ``oiço``/``ouço`` are both current European Portuguese. If the seed file
    could only carry one, re-seeding a verb exported from the database would
    start marking the other one wrong.
    """
    Session = _session(tmp_path)
    monkeypatch.setattr(
        seed_mod,
        "SEED_FILE",
        _write_seed(
            tmp_path,
            [{
                "infinitive": "ouvir",
                "forms": {"present_indicative": {"eu": ["oiço", "ouço"]}},
            }],
        ),
    )
    with Session() as db:
        assert seed_verbs(db) == 1
        form = db.scalar(select(Form))
        assert form.form_text == "oiço"  # the answer is the first entry
        assert [v.text for v in form.variants] == ["ouço"]


def test_short_participle_can_differ(tmp_path, monkeypatch):
    """``aceitar`` takes ``aceitado`` with ter/haver but ``aceite`` with ser/estar.

    Without the second field both rows would seed as ``aceitado``, quietly
    losing the distinction the two participle rows exist to drill.
    """
    Session = _session(tmp_path)
    monkeypatch.setattr(
        seed_mod,
        "SEED_FILE",
        _write_seed(
            tmp_path,
            [{
                "infinitive": "aceitar",
                "past_participle": "aceitado",
                "past_participle_short": ["aceite", "aceito"],
                "forms": {},
            }],
        ),
    )
    with Session() as db:
        assert seed_verbs(db) == 2
        by_person = {f.person: f for f in db.scalars(select(Form)).all()}
        assert by_person[INVARIABLE_PERSON].form_text == "aceitado"
        assert by_person[SHORT_PERSON].form_text == "aceite"
        assert [v.text for v in by_person[SHORT_PERSON].variants] == ["aceito"]
        # The verb column tracks the ter/haver participle, not the short one.
        assert db.scalar(select(Verb)).past_participle == "aceitado"


def test_paradigm_from_verb_carries_alternatives_back(tmp_path):
    """The inverse of upsert_verb: a cell survives the trip out and in.

    Rewriting a stored verb's sentences means describing it to the model again,
    so a cell that loses its alternatives here would be offered back as a
    narrower verb than the one in the database.
    """
    Session = _session(tmp_path)
    with Session() as db:
        verb = Verb(infinitive="ouvir", translation="to hear")
        form = Form(tense="present_indicative", person="eu", form_text="oiço")
        form.variants = [FormVariant(text="ouço")]
        verb.forms.append(form)
        verb.forms.append(Form(tense="preterite", person="eu", form_text="ouvi"))
        db.add(verb)
        db.commit()

        paradigm = seed_mod.paradigm_from_verb(db.get(Verb, verb.id))

    assert paradigm.infinitive == "ouvir"
    assert paradigm.translation == "to hear"
    assert paradigm.cell("present_indicative", "eu").forms == ("oiço", "ouço")
    assert paradigm.cell("preterite", "eu").forms == ("ouvi",)
