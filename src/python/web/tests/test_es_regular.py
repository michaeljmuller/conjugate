"""Telling a predictable Spanish verb from one worth drilling.

The paradigm half runs against saved Reverso pages; the spelling half tests
`regular_forms` directly, which needs no source at all.
"""

from pathlib import Path

import pytest

from web.languages import reverso
from web.languages.es import catalogue
from web.languages.es.adapter import SITE, to_paradigm
from web.languages.es.regular import (
    ENDINGS,
    IRREGULAR,
    PATTERNS,
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
    page = (FIXTURES / f"es-verb-{verb}.html").read_text(encoding="utf-8")
    return to_paradigm(reverso.parse_paradigm(page, verb, catalogue.person_key, SITE))


# ---- the three regular patterns ------------------------------------------

@pytest.mark.parametrize(
    "verb,pattern",
    [("hablar", "ar"), ("comer", "er"), ("vivir", "ir")],
)
def test_the_model_verbs_are_regular(verb, pattern):
    result = classify(paradigm(verb))
    assert result.kind == REGULAR
    assert result.pattern == pattern
    assert result.describe() == f"is a regular -{pattern} verb."


def test_the_infinitive_names_the_conjugation():
    """No -ire-style ambiguity: unlike Italian, one ending means one pattern."""
    assert patterns_for("hablar") == ["ar"]
    assert patterns_for("comer") == ["er"]
    assert patterns_for("vivir") == ["ir"]
    assert patterns_for("mesa") == []
    assert patterns_for("ir") == []  # the ending is the whole word


@pytest.mark.parametrize("verb", ["ir", "ser", "oler", "erguir"])
def test_irregular_verbs_are_reported_as_such(verb):
    assert not is_regular(paradigm(verb))
    assert classify(paradigm(verb)).describe() == "is an irregular verb."


def test_a_reflexive_reads_as_irregular():
    """The other documented gap. levantarse is a textbook-regular -ar verb, but
    it does not end in -ar, and its answers carry a clitic no ending table
    predicts — so the check has nothing to match it against."""
    assert patterns_for("levantarse") == []
    assert classify(paradigm("levantarse")).kind == IRREGULAR


def test_a_stem_change_reads_as_irregular():
    """The gap the module documents: which vowel changes, and whether one
    changes at all, is not recoverable from the infinitive — pensar changes and
    pasar does not — so a stem-changer classifies as irregular even though it
    is otherwise entirely predictable. empezar is both stem-changing and
    spelling-changing, and the stem change is what decides it."""
    result = classify(paradigm("empezar"))
    assert result.kind == IRREGULAR
    assert paradigm("empezar").cells[("presente", "yo")].answer == "empiezo"
    # The spelling half of the same verb is still recognised on its own.
    assert spelling_change("empezar").old == "z"


# ---- spelling changes, in both directions --------------------------------

def test_an_ar_stem_is_respelt_before_a_front_vowel():
    result = classify(paradigm("buscar"))
    assert result.kind == REGULAR_WITH_SPELLING
    assert result.pattern == "ar"
    assert result.describe() == (
        "is a regular -ar verb, apart from a spelling change: "
        "c → qu before e/é (busqué, busque)."
    )


def test_an_er_stem_is_respelt_before_a_back_vowel():
    """The opposite direction, which neither Portuguese nor Italian needs."""
    result = classify(paradigm("coger"))
    assert result.kind == REGULAR_WITH_SPELLING
    assert result.pattern == "er"
    assert result.describe() == (
        "is a regular -er verb, apart from a spelling change: "
        "g → j before a/o/á (cojo, coja)."
    )


@pytest.mark.parametrize(
    "infinitive,cell,expected",
    [
        # -ar: the ending's front vowel disturbs a stem written for a back one.
        ("buscar", ("preterito", "yo"), "busqué"),
        ("llegar", ("preterito", "yo"), "llegué"),
        ("cruzar", ("preterito", "yo"), "crucé"),
        ("averiguar", ("preterito", "yo"), "averigüé"),
        ("buscar", ("subjuntivo_presente", "nos"), "busquemos"),
        # ...and leaves it alone before a back one.
        ("buscar", ("presente", "yo"), "busco"),
        ("llegar", ("imperfecto", "yo"), "llegaba"),
        # -er/-ir: the mirror image.
        ("vencer", ("presente", "yo"), "venzo"),
        ("coger", ("presente", "yo"), "cojo"),
        ("distinguir", ("presente", "yo"), "distingo"),
        ("delinquir", ("presente", "yo"), "delinco"),
        ("coger", ("subjuntivo_presente", "vos"), "cojáis"),
        ("coger", ("presente", "tu"), "coges"),
    ],
)
def test_regular_forms_respells_the_stem(infinitive, cell, expected):
    pattern = patterns_for(infinitive)[0]
    assert regular_forms(infinitive, pattern)[cell] == (expected,)


def test_gu_is_tried_before_g():
    """Otherwise averiguar would give "averigué", which is a different verb's
    form — and distinguir would give "distinjo"."""
    assert spelling_change("averiguar").new == "gü"
    assert spelling_change("llegar").new == "gu"
    assert spelling_change("distinguir").new == "g"


def test_a_verb_needing_no_respelling_reports_none():
    assert spelling_change("hablar") is None
    assert spelling_change("comer") is None
    assert spelling_change("mesa") is None


# ---- what the table covers -----------------------------------------------

def test_the_table_holds_only_simple_tenses():
    """A compound tense is haber plus the participle. haber is the same for
    every verb, so a regular participle makes six regular compound tenses, and
    an ending table describing stems has nothing to say about them."""
    compound = {
        "perfecto",
        "pluscuamperfecto",
        "futuro_perfecto",
        "condicional_perfecto",
        "subjuntivo_perfecto",
        "subjuntivo_pluscuamperfecto",
    }
    assert compound <= set(catalogue.TENSE_KEYS)          # drilled
    assert not compound & {tense for tense, _ in ENDINGS}  # but not classified


def test_classifying_ignores_the_cells_the_table_does_not_cover():
    """The paradigm has more cells than the table has entries, and that must not
    by itself make every verb irregular."""
    cells = paradigm("hablar").cells
    assert len(cells) > len(ENDINGS)
    assert is_regular(paradigm("hablar"))


def test_the_imperfect_subjunctive_accepts_both_forms():
    """-ra and -se are equally regular. Treating either as an irregularity would
    call every Spanish verb irregular."""
    assert ENDINGS[("subjuntivo_imperfecto", "yo")][0] == ("ara", "ase")
    assert regular_forms("hablar", "ar")[("subjuntivo_imperfecto", "yo")] == (
        "hablara",
        "hablase",
    )


def test_every_pattern_has_a_column_in_every_row():
    assert ENDINGS
    assert all(len(row) == len(PATTERNS) for row in ENDINGS.values())


def test_regular_forms_declines_a_pattern_that_does_not_apply():
    assert regular_forms("hablar", "er") is None
    assert regular_forms("mesa", "ar") is None
