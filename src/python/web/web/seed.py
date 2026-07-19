"""Create tables and seed verbs on startup (idempotent)."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Base, Form, Verb

DATA_DIR = Path(__file__).parent / "data"
SEED_FILE = DATA_DIR / "verbs_seed.json"
EXAMPLES_FILE = DATA_DIR / "examples.json"


def init_db(engine) -> None:
    """Create tables if absent."""
    Base.metadata.create_all(engine)


def seed_verbs(db: Session) -> int:
    """Load seed verbs if the ``verbs`` table is empty. Returns verbs inserted."""
    existing = db.scalar(select(Verb.id).limit(1))
    if existing is not None:
        return 0

    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    for entry in data:
        verb = Verb(
            infinitive=entry["infinitive"],
            past_participle=entry.get("past_participle"),
            present_participle=entry.get("present_participle"),
        )
        for tense, persons in entry["forms"].items():
            for person, text in persons.items():
                verb.forms.append(Form(tense=tense, person=person, form_text=text))
        db.add(verb)
    db.commit()
    return len(data)


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
