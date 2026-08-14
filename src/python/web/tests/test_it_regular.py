"""Telling a predictable Italian verb from one worth drilling.

The paradigm half runs against saved Reverso pages; the spelling half tests
`regular_forms` directly, which needs no source at all.
"""

from pathlib import Path

import pytest

from web.languages.it import catalogue, reverso
from web.languages.it.adapter import to_paradigm
from web.languages.it.regular import (
    ENDINGS,
    PATTERNS,
    IRREGULAR,
    REGULAR,
    REGULAR_WITH_SPELLING,
    classify,
    is_regular,
    patterns_for,
    regular_forms,
    spelling_change,
)

FIXTURES = Path(__file__).parent / "fixtures" / "reverso"


def paradigm(verb: str):
    page = (FIXTURES / f"verb-{verb}.html").read_text(encoding="utf-8")
    return to_paradigm(reverso.parse_paradigm(page, verb, catalogue.person_key))


# ---- the four regular patterns -------------------------------------------

@pytest.mark.parametrize(
    "verb,pattern",
    [
        ("parlare", "are"),
        ("arrivare", "are"),
        ("credere", "ere"),
        ("partire", "ire"),
        ("capire", "ire-isc"),
    ],
)
def test_each_regular_pattern_is_recognised(verb, pattern):
    verdict = classify(paradigm(verb))
    assert verdict.kind == REGULAR
    assert verdict.pattern == pattern


@pytest.mark.parametrize("verb", ["andare", "essere", "correre"])
def test_an_irregular_verb_is_not(verb):
    assert is_regular(paradigm(verb)) is False


def test_an_ire_verb_is_tried_against_both_ire_patterns():
    """Nothing in the infinitive says whether an -ire verb infixes -isc-, so
    both are candidates and either counts as regular."""
    assert patterns_for("partire") == ["ire", "ire-isc"]
    assert patterns_for("parlare") == ["are"]
    assert patterns_for("credere") == ["ere"]


@pytest.mark.parametrize("infinitive", ["porre", "trarre", "condurre", "are"])
def test_an_infinitive_outside_the_three_conjugations_has_no_pattern(infinitive):
    """The -rre verbs are a closed irregular class and match no ending; a bare
    "are" has no stem left once the ending is stripped."""
    assert patterns_for(infinitive) == []


def test_matching_the_shape_is_not_enough():
    """dire and fare end in -ire and -are but conjugate nothing like them, so
    having a candidate pattern says nothing until the forms are compared."""
    assert patterns_for("dire") == ["ire", "ire-isc"]
    assert patterns_for("fare") == ["are"]
    # ...and the real check still rejects them: "dico" is not "disco"/"do".
    assert regular_forms("dire", "ire")[("presente", "io")][0] == "do"


def test_the_regular_ere_passato_remoto_takes_both_endings():
    """credetti/credei is part of the regular -ere pattern, not a defect. If
    the table held only one, every regular -ere verb would read as irregular.
    """
    ere = PATTERNS.index("ere")
    assert ENDINGS[("passato_remoto", "io")][ere] == ("etti", "ei")
    assert ENDINGS[("passato_remoto", "lui")][ere] == ("ette", "é")
    forms = regular_forms("credere", "ere")
    assert set(forms[("passato_remoto", "io")]) == {"credetti", "credei"}


def test_a_verb_with_an_unexpected_alternative_is_irregular():
    """andare's imperative offers va'/vai, which no regular pattern predicts."""
    verdict = classify(paradigm("andare"))
    assert verdict.kind == IRREGULAR


# ---- the -are spelling rules ---------------------------------------------

@pytest.mark.parametrize(
    "infinitive,tense,person,expected",
    [
        # c/g harden with an h before a front vowel.
        ("cercare", "presente", "tu", "cerchi"),
        ("cercare", "futuro_semplice", "io", "cercherò"),
        ("pagare", "presente", "tu", "paghi"),
        ("pagare", "congiuntivo_presente", "io", "paghi"),
        # ci/gi/sci drop the i rather than double it.
        ("cominciare", "presente", "tu", "cominci"),
        ("cominciare", "futuro_semplice", "io", "comincerò"),
        ("mangiare", "futuro_semplice", "io", "mangerò"),
        ("lasciare", "presente", "tu", "lasci"),
        # A back-vowel ending leaves the stem alone: not "cerchavo".
        ("cercare", "imperfetto", "io", "cercavo"),
        ("cominciare", "imperfetto", "io", "cominciavo"),
        ("parlare", "presente", "tu", "parli"),
    ],
)
def test_are_spelling(infinitive, tense, person, expected):
    assert regular_forms(infinitive, "are")[(tense, person)][0] == expected


def test_ere_and_ire_stems_are_never_respelt():
    """Italian lets leggo/leggi differ in sound at the same spelling, so no
    respelling rule applies outside -are."""
    assert regular_forms("credere", "ere")[("presente", "io")][0] == "credo"
    assert regular_forms("credere", "ere")[("presente", "tu")][0] == "credi"
    assert spelling_change("credere") is None
    assert spelling_change("partire") is None


@pytest.mark.parametrize(
    "infinitive,described",
    [
        ("cercare", "c → ch before e/i (cerchi, cercherò)"),
        ("pagare", "g → gh before e/i (paghi, pagherò)"),
        ("mangiare", "gi → g before e/i (mangi, mangerò)"),
    ],
)
def test_a_spelling_change_is_described_with_its_own_examples(infinitive, described):
    assert spelling_change(infinitive).describe() == described


def test_a_stem_needing_no_respelling_has_no_change_to_report():
    assert spelling_change("parlare") is None


# ---- what the confirmation says ------------------------------------------

@pytest.mark.parametrize(
    "verb,expected",
    [
        ("parlare", "is a regular -are verb."),
        ("credere", "is a regular -ere verb."),
        ("partire", "is a regular -ire verb."),
        ("capire", "is a regular -ire (with the -isc- infix) verb."),
        ("essere", "is an irregular verb."),
    ],
)
def test_the_verdict_names_the_pattern(verb, expected):
    assert classify(paradigm(verb)).describe() == expected


def test_the_verdict_agrees_with_the_boolean():
    for verb in ("parlare", "credere", "capire", "essere", "andare"):
        assert classify(paradigm(verb)).is_regular is is_regular(paradigm(verb))


def test_regular_forms_covers_every_cell_a_paradigm_has():
    """The table and the drilled catalogue must not drift apart."""
    for verb, pattern in [("parlare", "are"), ("credere", "ere"), ("capire", "ire-isc")]:
        assert set(regular_forms(verb, pattern)) == set(paradigm(verb).cells)


def test_a_spelling_change_still_counts_as_regular():
    """Synthesised rather than fetched: a verb whose only deviation is the
    predictable respelling is regular, and says so."""
    from web.languages.base import Cell, Paradigm

    forms = regular_forms("cercare", "are")
    verdict = classify(
        Paradigm(infinitive="cercare", cells={k: Cell(v) for k, v in forms.items()})
    )
    assert verdict.kind == REGULAR_WITH_SPELLING
    assert verdict.describe() == (
        "is a regular -are verb, apart from a spelling change: "
        "c → ch before e/i (cerchi, cercherò)."
    )
