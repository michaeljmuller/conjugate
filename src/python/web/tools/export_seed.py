"""Export app-added verbs from a database into the committed seed files.

A verb added through "Add a verb" exists only in the database it was added to:
its paradigm came from the source site and its ~60 example sentences from the
model, and neither is cheap to reproduce. This lifts those verbs back into
``data/verbs_seed.json`` and ``languages/pt/examples.json`` so a deploy seeds
them like any hand-curated verb — no lookup, no model call.

Run against the database, with the repo mounted, e.g.

    docker run --rm --network conjugate_default -v "$REPO:/repo" \
        -e DATABASE_URL=... conjugate-web python /repo/src/python/web/tools/export_seed.py

Existing entries are left exactly as they are; only verbs missing from a file
are appended. pt-PT only, as both files are.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.languages.pt.catalogue import (  # noqa: E402
    PAST_PARTICIPLE_TENSE,
    PERSONS,
    PRESENT_PARTICIPLE_TENSE,
    SHORT_PERSON,
    TENSE_KEYS,
)
from web.languages.base import INVARIABLE_PERSON  # noqa: E402
from web.models import Verb  # noqa: E402

LANGUAGE = "pt-PT"
WEB = Path(__file__).resolve().parent.parent / "web"
SEED_FILE = WEB / "data" / "verbs_seed.json"
EXAMPLES_FILE = WEB / "languages" / "pt" / "examples.json"

# Cells are written in catalogue order so the file reads like the drill.
_PERSON_ORDER = {p: i for i, p in enumerate([*PERSONS, INVARIABLE_PERSON, SHORT_PERSON])}
_TENSE_ORDER = {t: i for i, t in enumerate(TENSE_KEYS)}


def _sorted_cells(verb: Verb):
    return sorted(
        verb.forms,
        key=lambda f: (_TENSE_ORDER.get(f.tense, 99), _PERSON_ORDER.get(f.person, 99)),
    )


def seed_entry(verb: Verb) -> dict:
    """One ``verbs_seed.json`` entry: the paradigm, participles and variants.

    A cell with alternatives is written as a list (answer first) rather than a
    string — ``oiço``/``ouço`` both have to survive the round trip, or the drill
    would start marking a correct answer wrong.
    """
    forms: dict[str, dict[str, object]] = {}
    participles: dict[str, str] = {}
    for form in _sorted_cells(verb):
        texts = [form.form_text, *[v.text for v in form.variants]]
        value: object = texts[0] if len(texts) == 1 else texts
        if form.tense == PAST_PARTICIPLE_TENSE:
            participles[form.person] = value
            continue
        if form.tense == PRESENT_PARTICIPLE_TENSE:
            participles["present"] = value
            continue
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
    slots = [
        {
            "tense": f.tense,
            "person": f.person,
            "form": f.form_text,
            "example_en": f.example_en,
            "example_pt": f.example_pt,
        }
        for f in _sorted_cells(verb)
        if f.example_en and f.example_pt
    ]
    return {
        "infinitive": verb.infinitive,
        "english": verb.translation or "",
        "forms": slots,
    }


def main() -> int:
    url = os.environ["DATABASE_URL"]
    engine = create_engine(url)
    with Session(engine) as db:
        verbs = db.scalars(
            select(Verb)
            .where(Verb.language == LANGUAGE)
            .options(selectinload(Verb.forms))
            .order_by(Verb.infinitive)
        ).all()
        verbs = [v for v in verbs if v.created_by is not None]

        seed = json.loads(SEED_FILE.read_text(encoding="utf-8"))
        have_seed = {e["infinitive"] for e in seed}
        examples = json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))
        have_examples = {e["infinitive"] for e in examples["verbs"]}

        added_seed = added_examples = 0
        for verb in verbs:
            if verb.infinitive not in have_seed:
                seed.append(seed_entry(verb))
                added_seed += 1
            if verb.infinitive not in have_examples:
                entry = examples_entry(verb)
                examples["verbs"].append(entry)
                added_examples += 1
                print(f"  {verb.infinitive}: {len(entry['forms'])} sentences")

        SEED_FILE.write_text(
            json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        EXAMPLES_FILE.write_text(
            json.dumps(examples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"{added_seed} verb(s) seeded, {added_examples} with examples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
