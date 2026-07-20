"""Create tables and seed verbs on startup (idempotent)."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .conjugation import (
    INVARIABLE_PERSON,
    PAST_PARTICIPLE_TENSE,
    PRESENT_PARTICIPLE_TENSE,
)
from .models import Base, Form, Verb

DATA_DIR = Path(__file__).parent / "data"
SEED_FILE = DATA_DIR / "verbs_seed.json"
EXAMPLES_FILE = DATA_DIR / "examples.json"


def init_db(engine) -> None:
    """Create tables if absent."""
    Base.metadata.create_all(engine)


def seed_verbs(db: Session) -> int:
    """Sync seed verbs into the DB. Returns the number of ``Form`` rows inserted.

    Runs every startup and is incremental: missing verbs are created, and any
    ``(tense, person)`` form absent from an existing verb is added. This lets a
    redeploy introduce a new tense (e.g. the imperative) just by extending
    ``verbs_seed.json`` — no wipe, no schema change. Existing forms are left
    untouched (their text/examples are owned elsewhere); only gaps are filled.

    Blank cells are skipped, so the seed can carry empty placeholders for slots
    that aren't filled in yet — they become real forms once populated and the app
    is redeployed. The two participles have no person, so they are stored as forms
    under the invariable pseudo-person, sourced from the verb's top-level
    ``past_participle`` / ``present_participle`` fields.
    """
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    inserted = 0
    for entry in data:
        verb = db.scalar(select(Verb).where(Verb.infinitive == entry["infinitive"]))
        if verb is None:
            verb = Verb(
                infinitive=entry["infinitive"],
                past_participle=entry.get("past_participle"),
                present_participle=entry.get("present_participle"),
            )
            db.add(verb)
        else:
            # Backfill participles that were null before the seed grew them.
            if verb.past_participle is None:
                verb.past_participle = entry.get("past_participle")
            if verb.present_participle is None:
                verb.present_participle = entry.get("present_participle")

        # Person-inflected forms from the JSON, plus the two personless participles
        # synthesized from the verb's top-level fields.
        candidates = [
            (tense, person, text)
            for tense, persons in entry["forms"].items()
            for person, text in persons.items()
        ]
        candidates.append(
            (PAST_PARTICIPLE_TENSE, INVARIABLE_PERSON, entry.get("past_participle"))
        )
        candidates.append(
            (PRESENT_PARTICIPLE_TENSE, INVARIABLE_PERSON, entry.get("present_participle"))
        )

        existing = {(f.tense, f.person) for f in verb.forms}
        for tense, person, text in candidates:
            if not (text or "").strip():
                continue  # unfilled placeholder — leave it for a later redeploy
            if (tense, person) in existing:
                continue
            verb.forms.append(Form(tense=tense, person=person, form_text=text))
            existing.add((tense, person))
            inserted += 1
    # Commit unconditionally: new verbs and participle backfills are dirty even
    # when no new forms were inserted.
    db.commit()
    return inserted


def strip_negative_imperative_prefix(db: Session) -> int:
    """Drop a leading "não " from stored negative-imperative forms.

    These were originally seeded as ``"não sejas"``, which made the drill demand
    the ``não`` even though nothing in the prompt asked for it. The ``não`` now
    lives in the person label (see ``conjugation._PERSON_PREFIX``), matching how
    the subjunctives show ``que`` / ``se`` / ``quando`` without storing them. This
    migrates rows seeded before that change; it is idempotent and a no-op on a
    fresh DB. Returns the number of rows rewritten.
    """
    forms = db.scalars(
        select(Form).where(Form.tense == "imperative_negative")
    ).all()
    fixed = 0
    for form in forms:
        text = (form.form_text or "").strip()
        if text.lower().startswith("não "):
            form.form_text = text[4:].strip()
            fixed += 1
    if fixed:
        db.commit()
    return fixed


def seed_examples(db: Session) -> int:
    """Sync example sentences (English + pt-PT) from examples.json into forms.

    Runs every startup so re-deploying with a more-filled form updates the DB.
    Only non-empty values are applied; blanks never wipe existing text. Returns
    the number of fields updated.
    """
    if not EXAMPLES_FILE.exists():
        return 0
    data = json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))
    updated = 0
    for entry in data.get("verbs", []):
        verb = db.scalar(select(Verb).where(Verb.infinitive == entry["infinitive"]))
        if verb is None:
            continue
        by_key = {(f.tense, f.person): f for f in verb.forms}
        for slot in entry.get("forms", []):
            form = by_key.get((slot["tense"], slot["person"]))
            if form is None:
                continue
            for col in ("example_en", "example_pt"):
                text = (slot.get(col) or "").strip()
                if text and getattr(form, col) != text:
                    setattr(form, col, text)
                    updated += 1
    if updated:
        db.commit()
    return updated
