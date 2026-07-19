"""Domain constants for European-Portuguese conjugation.

Started from the original Excel tool (7 tenses, 5 drilled persons — ``vos`` is
stored for completeness but skipped in the drill, as in the sheet), then extended
with the imperative, future, personal infinitive, past pluperfect, and the two
participles. Subjunctive tenses display a pronoun prefix (que / se / quando) — a
presentation detail kept here, not in the database.

Participles have no person, so they are stored as forms under a pseudo-person
(``INVARIABLE_PERSON``) and rendered with an empty person label.
"""

# Placeholder person for personless forms (participles). Real conjugations never
# use this key, so it only ever matches a participle row.
INVARIABLE_PERSON = "inv"
PAST_PARTICIPLE_TENSE = "past_participle"
PRESENT_PARTICIPLE_TENSE = "present_participle"

# Ordered tenses. The original Excel block comes first; the added slots follow.
TENSES: list[dict[str, str]] = [
    {"key": "present_indicative", "label": "Present", "mood": "indicative"},
    {"key": "preterite", "label": "Preterite", "mood": "indicative"},
    {"key": "past_imperfect_indicative", "label": "Past imperfect", "mood": "indicative"},
    {"key": "past_pluperfect", "label": "Pluperfect", "mood": "indicative"},
    {"key": "future_indicative", "label": "Future", "mood": "indicative"},
    {"key": "conditional", "label": "Conditional", "mood": "conditional"},
    {"key": "present_subjunctive", "label": "Present", "mood": "subjunctive"},
    {"key": "past_imperfect_subjunctive", "label": "Past imperfect", "mood": "subjunctive"},
    {"key": "future_subjunctive", "label": "Future", "mood": "subjunctive"},
    {"key": "imperative_affirmative", "label": "Imperative (affirmative)", "mood": "imperative"},
    {"key": "imperative_negative", "label": "Imperative (negative)", "mood": "imperative"},
    {"key": "personal_infinitive", "label": "Personal infinitive", "mood": "infinitive"},
    {"key": PAST_PARTICIPLE_TENSE, "label": "Past participle", "mood": "participle"},
    {"key": PRESENT_PARTICIPLE_TENSE, "label": "Present participle", "mood": "participle"},
]

TENSE_KEYS: list[str] = [t["key"] for t in TENSES]

# All six persons are stored; the drill shows every person except ``vos``. The
# invariable person is appended last so participle rows render after real persons
# (for every other tense the (tense, "inv") lookup simply misses and is skipped).
PERSONS: list[str] = ["eu", "tu", "ele", "nos", "vos", "eles"]
DRILL_PERSONS: list[str] = ["eu", "tu", "ele", "nos", "eles", INVARIABLE_PERSON]

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
    """Human label for a (tense, person) pair, e.g. ``que eu`` or ``nós``.

    Participles are personless, so their row carries no label — the tense heading
    ("Past participle") is the whole prompt.
    """
    if person == INVARIABLE_PERSON:
        return ""
    base = _PERSON_DISPLAY.get(person, person)
    prefix = _SUBJUNCTIVE_PREFIX.get(tense)
    return f"{prefix} {base}" if prefix else base
