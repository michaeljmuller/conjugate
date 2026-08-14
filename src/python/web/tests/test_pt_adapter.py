"""Parsing cplp.org and turning it into a European-Portuguese paradigm.

Runs against saved pages — no network. The fixtures were chosen for what they
break: `aceitar` has three past participles and a variant preterite, `abrir` has
no regular participle at all, `ouvir` has fifteen cells with alternatives, and
`trazer`'s imperative puts variants either side of the negative's parentheses.
"""

import json
from pathlib import Path

import pytest

from web.languages.pt.catalogue import (
    INVARIABLE_PERSON,
    PAST_PARTICIPLE_TENSE,
    PRESENT_PARTICIPLE_TENSE,
    SHORT_PERSON,
    person_label,
)
from web.languages.pt import cplp
from web.languages.pt.adapter import (
    _to_paradigm,
    derive_regular_participle,
    select_preterite_nos,
    split_participles,
)
from web.seed import SEED_FILE

FIXTURES = Path(__file__).parent / "fixtures" / "cplp"


def lemma_page(verb: str) -> str:
    return (FIXTURES / f"lemma-{verb}.html").read_text(encoding="utf-8")


def search_page(verb: str) -> str:
    return (FIXTURES / f"search-{verb}.html").read_text(encoding="utf-8")


def paradigm(verb: str):
    return _to_paradigm(cplp.parse_paradigm(lemma_page(verb), verb))


# ---- the source's `A / B` notation --------------------------------------

def test_cells_carry_every_published_form():
    raw = cplp.parse_paradigm(lemma_page("ouvir"), "ouvir")
    assert raw.cells[("present_indicative", "eu")] == ["oiço", "ouço"]
    assert raw.cells[("present_indicative", "tu")] == ["ouves"]


@pytest.mark.parametrize(
    "cell,affirmative,negative",
    [
        ("vê (vejas)", ["vê"], ["vejas"]),
        # The bug this replaced: a regex anchored on \S+ swallowed the variants
        # and never separated trazer's negative.
        ("traz  /  traze (tragas)", ["traz", "traze"], ["tragas"]),
        ("veja", ["veja"], ["veja"]),  # no parentheses: same form both ways
    ],
)
def test_split_imperative(cell, affirmative, negative):
    assert cplp.split_imperative(cell) == (affirmative, negative)


def test_trazer_imperative_survives_the_round_trip():
    p = paradigm("trazer")
    assert p.cell("imperative_affirmative", "tu").forms == ("traz", "traze")
    assert p.cell("imperative_negative", "tu").forms == ("tragas",)


# ---- lemma resolution ----------------------------------------------------

def test_picks_the_verb_sense_when_a_word_is_ambiguous():
    # falar lists its *noun* sense first, so taking the first entry is wrong.
    lemmas = cplp.parse_lemmas(search_page("falar"))
    assert [l.senses for l in lemmas] == [("masculino",), ("verbo",)]
    assert [l for l in lemmas if l.is_verb][0].id == "38556"


def test_a_word_with_no_verb_sense_is_not_a_verb():
    lemmas = cplp.parse_lemmas(search_page("mesa"))
    assert lemmas and not any(l.is_verb for l in lemmas)


def test_a_page_without_a_paradigm_is_not_found():
    with pytest.raises(cplp.WordNotFound):
        cplp.parse_paradigm("<html><body><p>nothing</p></body></html>", "zzz")


# ---- the one selection rule ---------------------------------------------

@pytest.mark.parametrize(
    "infinitive,forms,expected",
    [
        # pt-PT takes the acute; the source's ordering is not a signal, so both
        # orderings have to resolve the same way.
        ("falar", ["falámos", "falamos"], ["falámos"]),
        ("aceitar", ["aceitamos", "aceitámos"], ["aceitámos"]),
        # -er and -ir verbs have no such split.
        ("correr", ["corremos"], ["corremos"]),
        ("partir", ["partimos"], ["partimos"]),
    ],
)
def test_preterite_nos_prefers_the_accented_form(infinitive, forms, expected):
    assert select_preterite_nos(infinitive, forms) == expected


def test_the_rule_is_applied_to_the_paradigm():
    assert paradigm("falar").cell("preterite", "nos").forms == ("falámos",)
    assert paradigm("aceitar").cell("preterite", "nos").forms == ("aceitámos",)


def test_unaccented_preterite_is_not_offered_as_an_alternative():
    """The stripped form is wrong for pt-PT, not merely undisplayed."""
    assert paradigm("falar").cell("preterite", "nos").alternatives == ()


# ---- participles ---------------------------------------------------------

@pytest.mark.parametrize(
    "infinitive,expected",
    [("falar", "falado"), ("correr", "corrido"), ("partir", "partido"), ("pôr", None)],
)
def test_derive_regular_participle(infinitive, expected):
    assert derive_regular_participle(infinitive) == expected


@pytest.mark.parametrize(
    "infinitive,forms,ter,ser",
    [
        # Regular present: it takes ter/haver, the rest take ser/estar.
        ("aceitar", ["aceitado", "aceite", "aceito"], ["aceitado"], ["aceite", "aceito"]),
        ("eleger", ["elegido", "eleito"], ["elegido"], ["eleito"]),
        # One form: both rows get it. The common case.
        ("falar", ["falado"], ["falado"], ["falado"]),
        # No regular form exists — "tinha aberto" is correct, so both rows take
        # the irregular one.
        ("abrir", ["aberto"], ["aberto"], ["aberto"]),
    ],
)
def test_split_participles(infinitive, forms, ter, ser):
    assert split_participles(infinitive, forms) == (ter, ser)


def test_participle_rows_are_labelled_by_auxiliary():
    p = paradigm("aceitar")
    assert p.cell(PAST_PARTICIPLE_TENSE, INVARIABLE_PERSON).forms == ("aceitado",)
    assert p.cell(PAST_PARTICIPLE_TENSE, SHORT_PERSON).forms == ("aceite", "aceito")
    assert person_label(PAST_PARTICIPLE_TENSE, INVARIABLE_PERSON) == "ter / haver"
    assert person_label(PAST_PARTICIPLE_TENSE, SHORT_PERSON) == "ser / estar"
    # The gerund keeps its single unlabelled row.
    assert person_label(PRESENT_PARTICIPLE_TENSE, INVARIABLE_PERSON) == ""


def test_a_verb_with_one_participle_still_gets_both_rows():
    p = paradigm("falar")
    assert p.cell(PAST_PARTICIPLE_TENSE, INVARIABLE_PERSON).forms == ("falado",)
    assert p.cell(PAST_PARTICIPLE_TENSE, SHORT_PERSON).forms == ("falado",)


# ---- the whole paradigm --------------------------------------------------

def test_paradigm_covers_every_drilled_tense():
    p = paradigm("ver")
    expected = {
        "present_indicative", "preterite", "past_imperfect_indicative",
        "past_pluperfect", "future_indicative", "conditional",
        "present_subjunctive", "past_imperfect_subjunctive", "future_subjunctive",
        "imperative_affirmative", "imperative_negative", "personal_infinitive",
        PAST_PARTICIPLE_TENSE, PRESENT_PARTICIPLE_TENSE,
    }
    assert p.tenses_present == expected


def test_cue_words_and_pronouns_are_not_part_of_the_answer():
    """Answers are stored bare; the drill re-adds que/se/quando/não as prompts."""
    p = paradigm("ver")
    assert p.cell("present_subjunctive", "eu").forms == ("veja",)
    assert p.cell("imperative_negative", "tu").forms == ("vejas",)
    assert p.cell("personal_infinitive", "eu").forms == ("ver",)


def test_matches_the_hand_curated_seed():
    """The regression gate: the source has to agree with data verified by hand.

    A cell where the source offers alternatives passes if the seed's form is one
    of them — that is how ``falar``'s ``falámos / falamos`` is meant to resolve.
    """
    seed = {v["infinitive"]: v for v in json.loads(SEED_FILE.read_text(encoding="utf-8"))}
    for infinitive in ("ver", "falar", "partir", "ir", "poder", "ser"):
        entry = seed.get(infinitive)
        if entry is None:
            continue
        p = paradigm(infinitive)
        for tense, persons in entry["forms"].items():
            for person, want in persons.items():
                cell = p.cell(tense, person)
                assert cell is not None, f"{infinitive} {tense}.{person} missing"
                assert want in cell.forms, f"{infinitive} {tense}.{person}: {want} not in {cell.forms}"
        assert entry["past_participle"] in p.cell(PAST_PARTICIPLE_TENSE, INVARIABLE_PERSON).forms
        assert entry["present_participle"] in p.cell(PRESENT_PARTICIPLE_TENSE, INVARIABLE_PERSON).forms
