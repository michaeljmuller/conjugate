"""Dump the database back into the committed seed files.

Startup seeding fills blanks only, so a sentence corrected in the running app
outlives a redeploy — which leaves the committed files behind. This is how they
catch up: build ``verbs_seed.json`` and ``examples.json`` from what the database
now holds, so the export can be written straight over the files and committed.

A whole-file dump, not a merge: the database is seeded from these files at every
startup, so it already holds everything they do plus whatever was added or fixed
since. The one part that lives only in the file is the prompt material
(``_instructions`` / ``_guidance``), which is carried across unchanged.

pt-PT only, as both files are.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .languages import INVARIABLE_PERSON, get_adapter
from .languages.pt.catalogue import (
    PAST_PARTICIPLE_TENSE,
    PERSONS,
    PRESENT_PARTICIPLE_TENSE,
    SHORT_PERSON,
    TENSE_KEYS,
)
from .languages.pt.prompts import EXAMPLES_FILE
from .models import Verb
from .seed import SEED_FILE

LANGUAGE = "pt-PT"

# Cells are written in catalogue order so the file reads like the drill and a
# re-export produces a diff of what changed, not a reshuffle.
_PERSON_ORDER = {p: i for i, p in enumerate([*PERSONS, INVARIABLE_PERSON, SHORT_PERSON])}
_TENSE_ORDER = {t: i for i, t in enumerate(TENSE_KEYS)}


def _sorted_cells(verb: Verb):
    return sorted(
        verb.forms,
        key=lambda f: (_TENSE_ORDER.get(f.tense, 99), _PERSON_ORDER.get(f.person, 99)),
    )


def _verbs(db: Session, order: list[str]) -> list[Verb]:
    """Every pt-PT verb, in the order the committed file already lists them.

    Not alphabetical: the files were hand-curated in a deliberate order (``ser``
    first, not ``abrir``), and re-sorting them would turn every export into a
    whole-file reshuffle that buries the one sentence that actually changed.
    Verbs the file does not know about are appended, alphabetically among
    themselves.
    """
    verbs = {
        v.infinitive: v
        for v in db.scalars(
            select(Verb).where(Verb.language == LANGUAGE).order_by(Verb.infinitive)
        ).all()
    }
    known = [verbs.pop(name) for name in order if name in verbs]
    return known + [verbs[name] for name in sorted(verbs)]


def _order_from(path: Path, key: str = "") -> list[str]:
    """The infinitives a committed file lists, in its order. Missing file: none."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get(key, []) if key else data
    return [e["infinitive"] for e in entries if "infinitive" in e]


def seed_entry(verb: Verb) -> dict:
    """One ``verbs_seed.json`` entry: the paradigm, participles and variants.

    A cell with alternatives is written as a list (answer first) rather than a
    string — ``oiço``/``ouço`` both have to survive the round trip, or re-seeding
    would start marking a correct answer wrong.
    """
    forms: dict[str, dict[str, object]] = {}
    participles: dict[str, object] = {}
    for form in _sorted_cells(verb):
        texts = [form.form_text, *[v.text for v in form.variants]]
        value: object = texts[0] if len(texts) == 1 else texts
        if form.tense == PAST_PARTICIPLE_TENSE:
            participles[form.person] = value
        elif form.tense == PRESENT_PARTICIPLE_TENSE:
            participles["present"] = value
        else:
            forms.setdefault(form.tense, {})[form.person] = value

    entry: dict[str, object] = {"infinitive": verb.infinitive}
    if verb.translation:
        entry["translation"] = verb.translation
    entry["past_participle"] = participles.get(INVARIABLE_PERSON)
    # Only when the ser/estar row genuinely differs (aceitado vs aceite); most
    # verbs use one form for both and need no second field.
    short = participles.get(SHORT_PERSON)
    if short and short != entry["past_participle"]:
        entry["past_participle_short"] = short
    entry["present_participle"] = participles.get("present")
    entry["forms"] = forms
    return entry


def examples_entry(verb: Verb) -> dict:
    """One ``examples.json`` entry: every form that actually has a sentence."""
    return {
        "infinitive": verb.infinitive,
        "english": verb.translation or "",
        "forms": [
            {
                "tense": f.tense,
                "person": f.person,
                "form": f.form_text,
                "example_en": f.example_en,
                "example_pt": f.example_pt,
            }
            for f in _sorted_cells(verb)
            if f.example_en and f.example_pt
        ],
    }


def verbs_seed(db: Session, *, seed_file: Path = SEED_FILE) -> list[dict]:
    """The whole of ``verbs_seed.json``, from the database."""
    return [seed_entry(v) for v in _verbs(db, _order_from(seed_file))]


def examples(db: Session, *, examples_file: Path = EXAMPLES_FILE) -> dict:
    """The whole of ``examples.json``, from the database.

    ``_instructions`` and ``_guidance`` are the style guide the model is prompted
    with. They are not in the database and never will be, so they are read from
    the packaged file and passed through untouched.
    """
    packaged = (
        json.loads(examples_file.read_text(encoding="utf-8"))
        if examples_file.exists()
        else {}
    )
    order = [e["infinitive"] for e in packaged.get("verbs", []) if "infinitive" in e]
    return {
        "_instructions": packaged.get("_instructions", ""),
        "_guidance": packaged.get("_guidance", {}),
        "verbs": [examples_entry(v) for v in _verbs(db, order)],
    }


def as_json(payload) -> str:
    """Serialized the way the committed files are, so a diff shows only content."""
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
