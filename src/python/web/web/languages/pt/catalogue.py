"""Domain constants for European-Portuguese conjugation.

Started from the original Excel tool (7 tenses, 5 drilled persons — ``vos`` is
stored for completeness but skipped in the drill, as in the sheet), then extended
with the imperative, future, personal infinitive, past pluperfect, and the two
participles. Some tenses display a prefix before the person (que / se / quando for
the subjunctives, não for the negative imperative) — a presentation detail kept
here, not in the database.

Participles have no person, so they are stored as forms under a pseudo-person
(``INVARIABLE_PERSON``, shared vocabulary from ``base``) and rendered with an
empty person label.
"""

from ..base import INVARIABLE_PERSON

# How the language is named to the user, and to the model when it writes
# example sentences.
NAME = "European Portuguese"

# Where paradigms come from, named in the add-a-verb progress and errors, and
# what to suggest when a lookup comes back empty.
SOURCE_NAME = "cplp.org"
NOT_FOUND_HINT = "Check the spelling — a Brazilian form will not be listed."

# Letters the accent bar offers, for typing answers without a Portuguese
# keyboard. Only those the drill actually needs: no ü, which the Acordo dropped.
ACCENTS = ["á", "â", "ã", "à", "é", "ê", "í", "ó", "ô", "õ", "ú", "ç"]

# The past participle is drilled as two rows, distinguished by the auxiliary the
# form takes rather than by person: the regular participle goes with ter/haver
# ("tinha aceitado") and the short one with ser/estar ("foi aceite"). Most verbs
# have the same form in both. The regular one reuses ``INVARIABLE_PERSON``; this
# is the second row, and is pt-PT's alone — no other language here splits the
# participle.
SHORT_PERSON = "short"
PAST_PARTICIPLE_TENSE = "past_participle"
PRESENT_PARTICIPLE_TENSE = "present_participle"

# Ordered tenses. The original Excel block comes first; the added slots follow.
# Each carries both English (``label``/``mood``) and Portuguese
# (``label_native``/``mood_native``) names; the UI's Interface setting picks
# which to show.
TENSES: list[dict[str, str]] = [
    {"key": "present_indicative", "label": "Present", "mood": "indicative", "label_native": "Presente", "mood_native": "indicativo"},
    {"key": "preterite", "label": "Preterite (simple past)", "mood": "indicative", "label_native": "Pretérito perfeito", "mood_native": "indicativo"},
    {"key": "past_imperfect_indicative", "label": "Past imperfect", "mood": "indicative", "label_native": "Pretérito imperfeito", "mood_native": "indicativo"},
    {"key": "past_pluperfect", "label": "Pluperfect (perfect past)", "mood": "indicative", "label_native": "Pretérito mais-que-perfeito", "mood_native": "indicativo"},
    {"key": "future_indicative", "label": "Future", "mood": "indicative", "label_native": "Futuro", "mood_native": "indicativo"},
    {"key": "conditional", "label": "Conditional", "mood": "conditional", "label_native": "Condicional", "mood_native": "condicional"},
    {"key": "present_subjunctive", "label": "Present", "mood": "subjunctive", "label_native": "Presente", "mood_native": "conjuntivo"},
    {"key": "past_imperfect_subjunctive", "label": "Past imperfect", "mood": "subjunctive", "label_native": "Pretérito imperfeito", "mood_native": "conjuntivo"},
    {"key": "future_subjunctive", "label": "Future", "mood": "subjunctive", "label_native": "Futuro", "mood_native": "conjuntivo"},
    {"key": "imperative_affirmative", "label": "Imperative (affirmative)", "mood": "imperative", "label_native": "Imperativo (afirmativo)", "mood_native": "imperativo"},
    {"key": "imperative_negative", "label": "Imperative (negative)", "mood": "imperative", "label_native": "Imperativo (negativo)", "mood_native": "imperativo"},
    {"key": "personal_infinitive", "label": "Personal infinitive", "mood": "infinitive", "label_native": "Infinitivo pessoal", "mood_native": "infinitivo"},
    {"key": PAST_PARTICIPLE_TENSE, "label": "Past participle", "mood": "participle", "label_native": "Particípio passado", "mood_native": "particípio"},
    {"key": PRESENT_PARTICIPLE_TENSE, "label": "Present participle", "mood": "participle", "label_native": "Gerúndio", "mood_native": "gerúndio"},
]

TENSE_KEYS: list[str] = [t["key"] for t in TENSES]

# All six persons are stored; the drill shows every person except ``vos``. The
# invariable person is appended last so participle rows render after real persons
# (for every other tense the (tense, "inv") lookup simply misses and is skipped).
PERSONS: list[str] = ["eu", "tu", "ele", "nos", "vos", "eles"]
DRILL_PERSONS: list[str] = [
    "eu", "tu", "ele", "nos", "eles", INVARIABLE_PERSON, SHORT_PERSON,
]

# Prefix shown before the person for tenses whose stored answer isn't the bare
# verb form: the subjunctive cue words, and the negative imperative's "não"
# (answers are stored as "não sejas", so the prompt has to ask for it).
_PERSON_PREFIX: dict[str, str] = {
    "present_subjunctive": "que",
    "past_imperfect_subjunctive": "se",
    "future_subjunctive": "quando",
    "imperative_negative": "não",
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


# Reverse of _PERSON_DISPLAY. The conjugation lookup reads display spellings off
# a web page ("nós") and needs the ascii key ("nos") the database stores.
_PERSON_BY_DISPLAY: dict[str, str] = {v: k for k, v in _PERSON_DISPLAY.items()}


def person_key(display: str) -> str | None:
    """Ascii person key for a display spelling (``nós`` -> ``nos``).

    Returns ``None`` for anything that isn't a person, which is how the
    conjugation parser tells a pronoun apart from a cue word (``que``, ``não``).
    """
    return _PERSON_BY_DISPLAY.get(display.strip().lower())


# The past participle's two rows are labelled by the auxiliary they take. These
# are verb names, so they read the same whichever interface language is chosen.
_PARTICIPLE_LABELS: dict[tuple[str, str], str] = {
    (PAST_PARTICIPLE_TENSE, INVARIABLE_PERSON): "ter / haver",
    (PAST_PARTICIPLE_TENSE, SHORT_PERSON): "ser / estar",
}


def person_label(tense: str, person: str) -> str:
    """Human label for a (tense, person) pair, e.g. ``que eu``, ``não tu``, ``nós``.

    Participles have no person. The past participle's rows are labelled with the
    auxiliary instead, which is the thing that actually distinguishes them; the
    gerund has a single row and needs no label, since the tense heading is the
    whole prompt.
    """
    if person in (INVARIABLE_PERSON, SHORT_PERSON):
        return _PARTICIPLE_LABELS.get((tense, person), "")
    base = _PERSON_DISPLAY.get(person, person)
    prefix = _PERSON_PREFIX.get(tense)
    return f"{prefix} {base}" if prefix else base
