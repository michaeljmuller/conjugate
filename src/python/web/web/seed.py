"""Create tables and seed verbs on startup (idempotent)."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .languages import INVARIABLE_PERSON, get_adapter
from .languages.base import Cell, Paradigm
from .languages.pt.catalogue import (
    PAST_PARTICIPLE_TENSE,
    PRESENT_PARTICIPLE_TENSE,
    SHORT_PERSON,
)
from .models import Base, Form, FormVariant, Verb

DATA_DIR = Path(__file__).parent / "data"
SEED_FILE = DATA_DIR / "verbs_seed.json"
EXAMPLES_FILE = DATA_DIR / "examples.json"


def init_db(engine) -> None:
    """Create tables if absent."""
    Base.metadata.create_all(engine)


def paradigm_from_entry(entry: dict) -> Paradigm:
    """Convert a ``verbs_seed.json`` entry into a ``Paradigm``.

    pt-PT only, as the seed file is: it predates the language abstraction and
    holds one form per cell with the participles as top-level fields. Lifting it
    into the same type the adapter produces means there is a single writer below
    this point.

    The past participle becomes both drilled rows — the ter/haver one and the
    ser/estar one — with the same form, which is right for every seeded verb.
    """
    paradigm = Paradigm(
        infinitive=entry["infinitive"], translation=entry.get("translation")
    )
    for tense, persons in entry.get("forms", {}).items():
        for person, text in persons.items():
            if (text or "").strip():
                paradigm.cells[(tense, person)] = Cell((text,))

    past = (entry.get("past_participle") or "").strip()
    if past:
        paradigm.cells[(PAST_PARTICIPLE_TENSE, INVARIABLE_PERSON)] = Cell((past,))
        paradigm.cells[(PAST_PARTICIPLE_TENSE, SHORT_PERSON)] = Cell((past,))
    present = (entry.get("present_participle") or "").strip()
    if present:
        paradigm.cells[(PRESENT_PARTICIPLE_TENSE, INVARIABLE_PERSON)] = Cell((present,))
    return paradigm


def upsert_verb(
    db: Session, paradigm: Paradigm, *, adapter, created_by: int | None = None
) -> tuple[Verb, int]:
    """Create or top up one verb from a paradigm. Returns ``(verb, inserted)``.

    ``adapter`` is consulted only to name the participle cells that fill
    ``Verb.past_participle`` / ``present_participle``; the forms themselves are
    written straight from ``paradigm.cells`` and need no language knowledge.

    Incremental: a missing verb is created, and any ``(tense, person)`` cell the
    verb lacks is added along with its alternative forms. Existing forms are
    never overwritten — their text and example sentences are owned elsewhere once
    written — so startup seeding can never disturb a verb added through the app.

    The single writer for both the startup seeder and the add-a-verb flow, so a
    looked-up verb and a seeded one land in the database by the same path.
    Does not commit.
    """
    verb = db.scalar(select(Verb).where(Verb.infinitive == paradigm.infinitive))
    past_tense = adapter.past_participle_tense
    present_tense = adapter.present_participle_tense
    past = paradigm.cell(past_tense, INVARIABLE_PERSON) if past_tense else None
    present = paradigm.cell(present_tense, INVARIABLE_PERSON) if present_tense else None

    if verb is None:
        verb = Verb(
            infinitive=paradigm.infinitive,
            past_participle=past.answer if past else None,
            present_participle=present.answer if present else None,
            translation=paradigm.translation,
            created_by=created_by,
        )
        db.add(verb)
    else:
        # Backfill fields that were null before the paradigm grew them.
        if verb.past_participle is None and past:
            verb.past_participle = past.answer
        if verb.present_participle is None and present:
            verb.present_participle = present.answer
        if verb.translation is None and paradigm.translation:
            verb.translation = paradigm.translation

    inserted = 0
    existing = {(f.tense, f.person) for f in verb.forms}
    for (tense, person), cell in paradigm.cells.items():
        if (tense, person) in existing:
            continue
        form = Form(tense=tense, person=person, form_text=cell.answer)
        form.variants = [FormVariant(text=t) for t in cell.alternatives]
        verb.forms.append(form)
        existing.add((tense, person))
        inserted += 1
    return verb, inserted


def seed_verbs(db: Session) -> int:
    """Sync seed verbs into the DB. Returns the number of ``Form`` rows inserted.

    Runs every startup and is incremental, so a redeploy can introduce a new
    tense just by extending ``verbs_seed.json`` — no wipe, no schema change.
    Verbs added through the app are untouched by this: ``upsert_verb`` only ever
    fills gaps.
    """
    adapter = get_adapter()
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    inserted = sum(
        upsert_verb(db, paradigm_from_entry(entry), adapter=adapter)[1] for entry in data
    )
    # Commit unconditionally: new verbs and participle backfills are dirty even
    # when no new forms were inserted.
    db.commit()
    return inserted


def apply_examples(verb: Verb, slots: list[dict]) -> int:
    """Write example sentences onto a verb's forms. Returns fields updated.

    Each slot is ``{"tense", "person", "example_en", "example_pt"}``. Only
    non-empty values are applied, so a blank never wipes existing text, and
    slots with no matching form are ignored. Does not commit.
    """
    by_key = {(f.tense, f.person): f for f in verb.forms}
    updated = 0
    for slot in slots:
        form = by_key.get((slot.get("tense"), slot.get("person")))
        if form is None:
            continue
        for col in ("example_en", "example_pt"):
            text = (slot.get(col) or "").strip()
            if text and getattr(form, col) != text:
                setattr(form, col, text)
                updated += 1
    return updated


def seed_examples(db: Session) -> int:
    """Sync example sentences (English + pt-PT) from examples.json into forms.

    Runs every startup so re-deploying with a more-filled form updates the DB.
    Returns the number of fields updated.
    """
    if not EXAMPLES_FILE.exists():
        return 0
    data = json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))
    updated = 0
    for entry in data.get("verbs", []):
        verb = db.scalar(select(Verb).where(Verb.infinitive == entry["infinitive"]))
        if verb is None:
            continue
        updated += apply_examples(verb, entry.get("forms", []))
    if updated:
        db.commit()
    return updated
