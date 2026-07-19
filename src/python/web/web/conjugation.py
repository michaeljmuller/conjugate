"""Domain constants for European-Portuguese conjugation.

Mirrors the original Excel tool: 7 tenses, and a drill that shows 5 persons
(``vos`` is stored for completeness but skipped in the drill, as in the sheet).
Subjunctive tenses display a pronoun prefix (que / se / quando) — a presentation
detail kept here, not in the database.
"""

# Ordered tenses, matching the Excel sheet's left-to-right layout.
TENSES: list[dict[str, str]] = [
    {"key": "present_indicative", "label": "Present", "mood": "indicative"},
    {"key": "preterite", "label": "Preterite", "mood": "indicative"},
    {"key": "past_imperfect_indicative", "label": "Past imperfect", "mood": "indicative"},
    {"key": "present_subjunctive", "label": "Present", "mood": "subjunctive"},
    {"key": "past_imperfect_subjunctive", "label": "Past imperfect", "mood": "subjunctive"},
    {"key": "future_subjunctive", "label": "Future", "mood": "subjunctive"},
    {"key": "conditional", "label": "Conditional", "mood": "conditional"},
]

TENSE_KEYS: list[str] = [t["key"] for t in TENSES]

# All six persons are stored; the drill shows every person except ``vos``.
PERSONS: list[str] = ["eu", "tu", "ele", "nos", "vos", "eles"]
DRILL_PERSONS: list[str] = ["eu", "tu", "ele", "nos", "eles"]

# Pronoun prefix shown before the person in subjunctive tenses.
_SUBJUNCTIVE_PREFIX: dict[str, str] = {
    "present_subjunctive": "que",
    "past_imperfect_subjunctive": "se",
    "future_subjunctive": "quando",
}

# Display spelling for each person (the DB stores ascii-safe keys).
_PERSON_DISPLAY: dict[str, str] = {
    "eu": "eu",
    "tu": "tu",
    "ele": "ele",
    "nos": "nós",
    "vos": "vós",
    "eles": "eles",
}


def person_label(tense: str, person: str) -> str:
    """Human label for a (tense, person) pair, e.g. ``que eu`` or ``nós``."""
    base = _PERSON_DISPLAY.get(person, person)
    prefix = _SUBJUNCTIVE_PREFIX.get(tense)
    return f"{prefix} {base}" if prefix else base
