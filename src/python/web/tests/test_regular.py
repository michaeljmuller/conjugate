"""Telling a fully predictable verb from one worth drilling.

The paradigm half runs against saved cplp.org pages; the spelling half tests
``regular_forms`` directly, which needs no source at all.
"""

from pathlib import Path

import pytest

from web.languages.pt import cplp
from web.languages.base import Cell, Paradigm
from web.languages.pt.adapter import _to_paradigm
from web.languages.pt.regular import (
    ENDINGS,
    IRREGULAR,
    REGULAR,
    REGULAR_WITH_SPELLING,
    classify,
    is_regular,
    regular_forms,
    spelling_change,
)

FIXTURES = Path(__file__).parent / "fixtures" / "cplp"


def paradigm(verb: str):
    page = (FIXTURES / f"lemma-{verb}.html").read_text(encoding="utf-8")
    return _to_paradigm(cplp.parse_paradigm(page, verb))


@pytest.mark.parametrize("verb", ["falar", "partir"])
def test_a_predictable_verb_is_regular(verb):
    assert is_regular(paradigm(verb)) is True


@pytest.mark.parametrize("verb", ["ser", "ir", "ver", "poder", "trazer", "ouvir"])
def test_an_irregular_verb_is_not(verb):
    assert is_regular(paradigm(verb)) is False


def test_an_extra_participle_makes_a_verb_worth_drilling():
    """`aceitar` is regular everywhere except that it also has `aceite`, and
    `abrir` has only `aberto`. Both are exactly what the drill is for, so
    neither may be waved through as regular."""
    assert is_regular(paradigm("aceitar")) is False
    assert is_regular(paradigm("abrir")) is False


def test_a_cell_with_alternatives_is_never_regular():
    """`ouvir` matches the -ir pattern in most cells but publishes oiço/ouço."""
    p = paradigm("ouvir")
    assert p.cells[("present_indicative", "eu")].forms == ("oiço", "ouço")
    assert is_regular(p) is False


# ---- the spelling rules, which are what make jogar regular ---------------

@pytest.mark.parametrize(
    "infinitive, tense, person, expected",
    [
        # -ar: the stem shifts only before a front vowel...
        ("jogar", "present_subjunctive", "eu", "jogue"),
        ("ficar", "present_subjunctive", "eu", "fique"),
        ("ficar", "preterite", "eu", "fiquei"),
        ("começar", "present_subjunctive", "eu", "comece"),
        # ...and must be left alone before a back one.
        ("jogar", "present_indicative", "eu", "jogo"),
        ("ficar", "conditional", "eu", "ficaria"),
        ("começar", "past_imperfect_indicative", "eu", "começava"),
        # -er/-ir: the mirror image.
        ("conhecer", "present_indicative", "eu", "conheço"),
        ("conhecer", "present_subjunctive", "eu", "conheça"),
        ("conhecer", "conditional", "eu", "conheceria"),
        ("proteger", "present_indicative", "eu", "protejo"),
        ("erguer", "present_indicative", "eu", "ergo"),
        ("dirigir", "present_indicative", "eu", "dirijo"),
        ("dirigir", "present_indicative", "tu", "diriges"),
        # The pt-PT preterite accent is part of the pattern.
        ("falar", "preterite", "nos", "falámos"),
    ],
)
def test_regular_forms_spelling(infinitive, tense, person, expected):
    assert regular_forms(infinitive)[(tense, person)] == expected


def test_regular_forms_covers_every_cell_a_paradigm_has():
    """Missing keys would make every verb compare as irregular."""
    assert set(regular_forms("falar")) == set(ENDINGS)
    assert set(paradigm("falar").cells) == set(ENDINGS)


@pytest.mark.parametrize("infinitive", ["pôr", "repor", "ar", "x"])
def test_verbs_outside_the_three_conjugations_have_no_regular_pattern(infinitive):
    assert regular_forms(infinitive) is None


# ---- the three-way verdict ----------------------------------------------

def test_a_plain_verb_is_regular_with_nothing_to_report():
    verdict = classify(paradigm("falar"))
    assert verdict.kind == REGULAR
    assert verdict.spelling is None


@pytest.mark.parametrize("verb", ["ser", "ver", "ouvir", "aceitar"])
def test_anything_unpredictable_is_irregular(verb):
    verdict = classify(paradigm(verb))
    assert verdict.kind == IRREGULAR
    assert verdict.spelling is None


@pytest.mark.parametrize(
    "infinitive, described",
    [
        ("jogar", "g → gu before e (jogue, joguei)"),
        ("ficar", "c → qu before e (fique, fiquei)"),
        ("começar", "ç → c before e (comece, comecei)"),
        ("conhecer", "c → ç before a/o (conheço, conheça)"),
        ("proteger", "g → j before a/o (protejo, proteja)"),
        ("erguer", "gu → g before a/o (ergo, erga)"),
    ],
)
def test_a_spelling_change_is_described_with_its_own_examples(infinitive, described):
    assert spelling_change(infinitive).describe() == described


def test_a_respelt_verb_is_regular_but_reported_separately():
    """The whole point of the third class: predictable, yet not silently so.

    No fixture needed — a verb that is regular by definition is one whose cells
    are exactly what the table produces.
    """
    jogar = Paradigm(
        infinitive="jogar",
        cells={key: Cell((form,)) for key, form in regular_forms("jogar").items()},
    )
    verdict = classify(jogar)
    assert verdict.kind == REGULAR_WITH_SPELLING
    assert verdict.is_regular is True
    assert verdict.spelling.examples == ("jogue", "joguei")


def test_a_stem_needing_no_respelling_has_no_change_to_report():
    assert spelling_change("falar") is None
    assert spelling_change("partir") is None


def test_the_verdict_agrees_with_the_boolean():
    for verb in ["falar", "partir", "ser", "ver", "ouvir", "aceitar", "abrir"]:
        p = paradigm(verb)
        assert is_regular(p) is (classify(p).kind != IRREGULAR)
