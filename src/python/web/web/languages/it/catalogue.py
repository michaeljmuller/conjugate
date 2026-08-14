"""Domain constants for Italian conjugation.

Ten drilled tenses, all of them *simple*. Reverso publishes ten more — the four
compound indicative tenses, the two compound subjunctives, the compound
conditional, the past gerund, plus ``Infinito presente`` (which is just the
infinitive) and ``Participio presente`` (``parlante``, adjectival rather than
verbal). None are drilled.

Compound tenses are excluded on purpose, and not only to match the Portuguese
drill. Their row count depends on the verb: an *avere* verb gives six, an
*essere* verb gives eight because the participle agrees in gender and number
(``è arrivato`` / ``è arrivata``, ``sono arrivati`` / ``sono arrivate``), and a
verb taking both auxiliaries in different senses — ``correre``, ``vivere`` —
gives fourteen. One answer per ``(tense, person)`` could not hold that, and the
agreement forms are not interchangeable alternatives: ``sono corso`` and ``sono
corsa`` are each right for a different subject, so accepting either would teach
the wrong thing. Drilling them needs an agreement axis the model does not have.

Unlike Portuguese's ``vós``, Italian's ``voi`` is everyday and *is* drilled.
"""

from ..base import INVARIABLE_PERSON

NAME = "Italian"

SOURCE_NAME = "Reverso"
NOT_FOUND_HINT = "Check the spelling — enter the infinitive, e.g. parlare."

# Letters the accent bar offers. Italian marks stress on final vowels (parlò,
# perché, città) and nothing else needs a bar; the Portuguese tilde and cedilla
# have no place here.
ACCENTS = ["à", "è", "é", "ì", "ò", "ó", "ù"]

# Personless forms: the gerund and the past participle each have a single row.
# Italian does not split the participle the way pt-PT does, so there is no
# second participle person.
GERUND_TENSE = "gerundio"
PAST_PARTICIPLE_TENSE = "participio_passato"

# Ordered as the drill shows them: indicative, subjunctive, conditional,
# imperative, then the two personless forms.
TENSES: list[dict[str, str]] = [
    {"key": "presente", "label": "Present", "mood": "indicative", "label_native": "Presente", "mood_native": "indicativo"},
    {"key": "imperfetto", "label": "Imperfect", "mood": "indicative", "label_native": "Imperfetto", "mood_native": "indicativo"},
    {"key": "passato_remoto", "label": "Past historic", "mood": "indicative", "label_native": "Passato remoto", "mood_native": "indicativo"},
    {"key": "futuro_semplice", "label": "Future", "mood": "indicative", "label_native": "Futuro semplice", "mood_native": "indicativo"},
    {"key": "congiuntivo_presente", "label": "Present", "mood": "subjunctive", "label_native": "Presente", "mood_native": "congiuntivo"},
    {"key": "congiuntivo_imperfetto", "label": "Imperfect", "mood": "subjunctive", "label_native": "Imperfetto", "mood_native": "congiuntivo"},
    {"key": "condizionale_presente", "label": "Conditional", "mood": "conditional", "label_native": "Condizionale", "mood_native": "condizionale"},
    {"key": "imperativo", "label": "Imperative", "mood": "imperative", "label_native": "Imperativo", "mood_native": "imperativo"},
    {"key": GERUND_TENSE, "label": "Gerund", "mood": "gerund", "label_native": "Gerundio", "mood_native": "gerundio"},
    {"key": PAST_PARTICIPLE_TENSE, "label": "Past participle", "mood": "participle", "label_native": "Participio passato", "mood_native": "participio"},
]

TENSE_KEYS: list[str] = [t["key"] for t in TENSES]

# All six are drilled — there is no stored-but-skipped person as in pt-PT.
PERSONS: list[str] = ["io", "tu", "lui", "noi", "voi", "loro"]
DRILL_PERSONS: list[str] = [*PERSONS, INVARIABLE_PERSON]

# The subjunctive is cued by "che", which Reverso prints as part of the pronoun
# ("che io") and which the drill shows as a prefix instead — the stored answer
# is the bare verb form.
_PERSON_PREFIX: dict[str, str] = {
    "congiuntivo_presente": "che",
    "congiuntivo_imperfetto": "che",
}

_PERSON_DISPLAY: dict[str, str] = {
    "io": "io",
    "tu": "tu",
    "lui": "lui/lei",
    "noi": "noi",
    "voi": "voi",
    "loro": "loro",
}

# The imperative's rows are the polite ones: its 3rd-person slots address "Lei"
# and "Loro" (formal you), not "him/her" — so they cannot use the display
# spellings above without saying something false.
_IMPERATIVE_LABELS: dict[str, str] = {
    "tu": "tu",
    "lui": "Lei",
    "noi": "noi",
    "voi": "voi",
    "loro": "Loro",
}

_PERSON_BY_DISPLAY: dict[str, str] = {
    "io": "io",
    "tu": "tu",
    # Reverso writes the third person as "lei/lui"; the compound tenses split it
    # into bare "lui" and "lei", which are not drilled but cost nothing to map.
    "lei/lui": "lui",
    "lui/lei": "lui",
    "lui": "lui",
    "lei": "lui",
    "noi": "noi",
    "voi": "voi",
    "loro": "loro",
}


def person_key(display: str) -> str | None:
    """Ascii person key for a pronoun as printed (``lei/lui`` -> ``lui``).

    Returns ``None`` for anything that isn't a pronoun, which is how the
    paradigm parser recognises the imperative's unlabelled rows.
    """
    return _PERSON_BY_DISPLAY.get(display.strip().lower())


def person_label(tense: str, person: str) -> str:
    """Human label for a ``(tense, person)`` pair — ``che io``, ``Lei``, ``noi``.

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
