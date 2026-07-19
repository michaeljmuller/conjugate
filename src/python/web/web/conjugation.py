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
# Each carries both English (``label``/``mood``) and European-Portuguese
# (``label_pt``/``mood_pt``) names; the UI's Interface setting picks which to show.
TENSES: list[dict[str, str]] = [
    {"key": "present_indicative", "label": "Present", "mood": "indicative", "label_pt": "Presente", "mood_pt": "indicativo"},
    {"key": "preterite", "label": "Preterite", "mood": "indicative", "label_pt": "Pretérito perfeito", "mood_pt": "indicativo"},
    {"key": "past_imperfect_indicative", "label": "Past imperfect", "mood": "indicative", "label_pt": "Pretérito imperfeito", "mood_pt": "indicativo"},
    {"key": "past_pluperfect", "label": "Pluperfect", "mood": "indicative", "label_pt": "Pretérito mais-que-perfeito", "mood_pt": "indicativo"},
    {"key": "future_indicative", "label": "Future", "mood": "indicative", "label_pt": "Futuro", "mood_pt": "indicativo"},
    {"key": "conditional", "label": "Conditional", "mood": "conditional", "label_pt": "Condicional", "mood_pt": "condicional"},
    {"key": "present_subjunctive", "label": "Present", "mood": "subjunctive", "label_pt": "Presente", "mood_pt": "conjuntivo"},
    {"key": "past_imperfect_subjunctive", "label": "Past imperfect", "mood": "subjunctive", "label_pt": "Pretérito imperfeito", "mood_pt": "conjuntivo"},
    {"key": "future_subjunctive", "label": "Future", "mood": "subjunctive", "label_pt": "Futuro", "mood_pt": "conjuntivo"},
    {"key": "imperative_affirmative", "label": "Imperative (affirmative)", "mood": "imperative", "label_pt": "Imperativo (afirmativo)", "mood_pt": "imperativo"},
    {"key": "imperative_negative", "label": "Imperative (negative)", "mood": "imperative", "label_pt": "Imperativo (negativo)", "mood_pt": "imperativo"},
    {"key": "personal_infinitive", "label": "Personal infinitive", "mood": "infinitive", "label_pt": "Infinitivo pessoal", "mood_pt": "infinitivo"},
    {"key": PAST_PARTICIPLE_TENSE, "label": "Past participle", "mood": "participle", "label_pt": "Particípio passado", "mood_pt": "particípio"},
    {"key": PRESENT_PARTICIPLE_TENSE, "label": "Present participle", "mood": "participle", "label_pt": "Gerúndio", "mood_pt": "gerúndio"},
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


_TENSE_BY_KEY: dict[str, dict[str, str]] = {t["key"]: t for t in TENSES}


def resolve_tense_prefs(saved: list[dict]) -> list[dict]:
    """Reconcile a (possibly stale) saved tense-preference list against ``TENSES``.

    ``saved`` is ``[{"key", "enabled"}, …]`` in the user's chosen order. Unknown
    or duplicate keys are dropped; valid keys keep their order and ``enabled``
    flag; any canonical tense missing from ``saved`` is appended at the end as
    enabled — so newly-added tenses show up by default rather than vanishing for
    users who saved settings before the tense existed. An empty ``saved`` yields
    every tense enabled in canonical order (the default, no-settings behavior).

    Returns ``[{"key", "label", "mood", "enabled"}, …]`` ready for the UI.
    """
    resolved: list[dict] = []
    seen: set[str] = set()
    for item in saved:
        key = item.get("key")
        if key in _TENSE_BY_KEY and key not in seen:
            seen.add(key)
            t = _TENSE_BY_KEY[key]
            resolved.append({**t, "enabled": bool(item.get("enabled", True))})
    for t in TENSES:
        if t["key"] not in seen:
            resolved.append({**t, "enabled": True})
    return resolved


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
