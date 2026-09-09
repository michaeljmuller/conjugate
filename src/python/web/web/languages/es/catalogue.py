"""Domain constants for Spanish conjugation.

Sixteen drilled tenses: eight simple, six compound, and the two personless
forms. The audience is US school Spanish, levels 1 through 4, and that decides
the two questions a Spanish catalogue has to answer.

**vosotros is drilled.** The textbooks US classrooms use — Realidades/Auténtico,
Descubre/Vistas, Avancemos — teach Latin American Spanish but print the
six-person chart with vosotros in it, and the AP exam expects a student to
recognise the forms. This is the opposite of the ``vós`` call in ``pt``, and
deliberately: ``vós`` is archaic everywhere, while vosotros is ordinary speech
in Spain. Nothing is missing for a learner who will never say it — Latin
American *ustedes* takes the same forms as *ellos*, so that row is already here.

**Compound tenses are drilled**, unlike Italian's. The reason Italian leaves
them out does not apply: after *haber* the participle never agrees, so every
Spanish compound tense is exactly six rows — ``he hablado``, ``has hablado`` —
where an Italian *essere* verb gives eight and ``correre`` gives fourteen. They
are also core Spanish 2-4 material rather than an extra.

Three of Reverso's blocks are dropped as dead rather than as out of scope:
``Pretérito anterior`` (*hube hablado*) survives only in literary narration
after *cuando*, and the future subjunctive (*hablare*, *hubiere hablado*) is
gone outside legal boilerplate and fossilised proverbs. That last one is worth
naming because ``pt`` does drill its future subjunctive: in Portuguese the tense
is alive and everyday, and Spanish is where it died.
"""

from ..base import INVARIABLE_PERSON

NAME = "Spanish"

SOURCE_NAME = "Reverso"
NOT_FOUND_HINT = "Check the spelling — enter the infinitive, e.g. hablar."

# Letters the accent bar offers. The five stress-marked vowels, plus ñ (añado)
# and ü, which a -guar verb needs in the preterite (averigüé).
ACCENTS = ["á", "é", "í", "ó", "ú", "ü", "ñ"]

# Personless forms: one row each. Spanish does not split the participle the way
# pt-PT does — a Spanish verb has exactly one — so there is no second
# participle person.
GERUND_TENSE = "gerundio"
PAST_PARTICIPLE_TENSE = "participio"

# Ordered as the drill shows them, and roughly as they are taught: the simple
# tenses first, then the compounds built on them, then the two personless forms.
TENSES: list[dict[str, str]] = [
    {"key": "presente", "label": "Present", "mood": "indicative", "label_native": "Presente", "mood_native": "indicativo"},
    {"key": "imperfecto", "label": "Imperfect", "mood": "indicative", "label_native": "Pretérito imperfecto", "mood_native": "indicativo"},
    {"key": "preterito", "label": "Preterite", "mood": "indicative", "label_native": "Pretérito perfecto simple", "mood_native": "indicativo"},
    {"key": "futuro", "label": "Future", "mood": "indicative", "label_native": "Futuro", "mood_native": "indicativo"},
    {"key": "condicional", "label": "Conditional", "mood": "conditional", "label_native": "Condicional", "mood_native": "condicional"},
    {"key": "subjuntivo_presente", "label": "Present", "mood": "subjunctive", "label_native": "Presente", "mood_native": "subjuntivo"},
    {"key": "subjuntivo_imperfecto", "label": "Imperfect", "mood": "subjunctive", "label_native": "Pretérito imperfecto", "mood_native": "subjuntivo"},
    {"key": "imperativo", "label": "Imperative", "mood": "imperative", "label_native": "Imperativo", "mood_native": "imperativo"},
    {"key": "perfecto", "label": "Present perfect", "mood": "indicative", "label_native": "Pretérito perfecto compuesto", "mood_native": "indicativo"},
    {"key": "pluscuamperfecto", "label": "Pluperfect", "mood": "indicative", "label_native": "Pretérito pluscuamperfecto", "mood_native": "indicativo"},
    {"key": "futuro_perfecto", "label": "Future perfect", "mood": "indicative", "label_native": "Futuro perfecto", "mood_native": "indicativo"},
    {"key": "condicional_perfecto", "label": "Conditional perfect", "mood": "conditional", "label_native": "Condicional perfecto", "mood_native": "condicional"},
    {"key": "subjuntivo_perfecto", "label": "Present perfect", "mood": "subjunctive", "label_native": "Pretérito perfecto", "mood_native": "subjuntivo"},
    {"key": "subjuntivo_pluscuamperfecto", "label": "Pluperfect", "mood": "subjunctive", "label_native": "Pretérito pluscuamperfecto", "mood_native": "subjuntivo"},
    {"key": GERUND_TENSE, "label": "Gerund", "mood": "gerund", "label_native": "Gerundio", "mood_native": "gerundio"},
    {"key": PAST_PARTICIPLE_TENSE, "label": "Past participle", "mood": "participle", "label_native": "Participio pasado", "mood_native": "participio"},
]

TENSE_KEYS: list[str] = [t["key"] for t in TENSES]

# All six are drilled — there is no stored-but-skipped person as in pt-PT.
#
# ``vos`` here is *vosotros*, and in ``pt`` it is *vós*. The keys are read only
# against their own language's catalogue, so the two never meet, but the
# coincidence is worth knowing about before copying a person map between them.
PERSONS: list[str] = ["yo", "tu", "el", "nos", "vos", "ellos"]
DRILL_PERSONS: list[str] = [*PERSONS, INVARIABLE_PERSON]

# Spanish has no 1st-person-singular imperative, so it is these five.
IMPERATIVE_PERSONS: list[str] = ["tu", "el", "nos", "vos", "ellos"]


def positional_persons(title: str, rows: int) -> list[str]:
    """Persons for a block whose rows print no pronoun.

    Spanish has two such blocks where Italian has one, and the row count is
    what tells them apart:

    - Five rows: the imperative, which addresses its subject instead of naming
      it. True of every verb.
    - Six rows: any block of a *reflexive* verb. Reverso puts the clitic in
      ``particletxt`` where the pronoun would go, so ``levantarse`` prints
      ``me levanto`` with no ``yo`` anywhere. The clitic is part of the answer
      and is kept — see ``Site.particle_in_form`` — but it cannot identify the
      person, because ``se`` is both third singular and third plural.
    """
    return IMPERATIVE_PERSONS if rows == len(IMPERATIVE_PERSONS) else PERSONS


# The subjunctive is cued by "que". Unlike Italian's "che", Reverso does not
# print it, so nothing has to be stripped — it exists only as a row label.
_PERSON_PREFIX: dict[str, str] = {
    "subjuntivo_presente": "que",
    "subjuntivo_imperfecto": "que",
    "subjuntivo_perfecto": "que",
    "subjuntivo_pluscuamperfecto": "que",
}

_PERSON_DISPLAY: dict[str, str] = {
    "yo": "yo",
    "tu": "tú",
    "el": "él/ella/Ud.",
    "nos": "nosotros",
    "vos": "vosotros",
    "ellos": "ellos/ellas/Uds.",
}

# The imperative's third-person rows are the polite ones: they address Ud. and
# Uds., not him or her, so they cannot use the display spellings above without
# saying something false. Italian has the same problem with Lei and Loro.
_IMPERATIVE_LABELS: dict[str, str] = {
    "tu": "tú",
    "el": "Ud.",
    "nos": "nosotros",
    "vos": "vosotros",
    "ellos": "Uds.",
}

_PERSON_BY_DISPLAY: dict[str, str] = {
    "yo": "yo",
    "tú": "tu",
    "él/ella/ud.": "el",
    "nosotros": "nos",
    "vosotros": "vos",
    "ellos/ellas/uds.": "ellos",
}


def person_key(display: str) -> str | None:
    """Ascii person key for a pronoun as printed (``él/ella/Ud.`` -> ``el``).

    Returns ``None`` for anything that isn't a pronoun, which is how the
    paradigm parser recognises a block whose rows are unlabelled.
    """
    return _PERSON_BY_DISPLAY.get(display.strip().lower())


def person_label(tense: str, person: str) -> str:
    """Human label for a ``(tense, person)`` pair — ``que yo``, ``Ud.``, ``tú``.

    The gerund and participle have one row each and need no label: the tense
    heading is the whole prompt.
    """
    if person == INVARIABLE_PERSON:
        return ""
    if tense == "imperativo":
        return _IMPERATIVE_LABELS.get(person, person)
    base = _PERSON_DISPLAY.get(person, person)
    prefix = _PERSON_PREFIX.get(tense)
    return f"{prefix} {base}" if prefix else base
