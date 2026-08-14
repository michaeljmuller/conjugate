"""Parsing Reverso and turning it into an Italian paradigm.

Runs against saved pages — no network. The fixtures were chosen for what they
break: `capire` takes the `-isc-` infix, `andare` puts alternatives in the
imperative (`va'/vai`), `credere` has the two-way regular passato remoto,
`arrivare` and `correre` publish essere-auxiliary compounds with eight and
fourteen rows, and `tavolo` is Reverso's 404 for a word that is a real noun.
"""

import asyncio
import re
from pathlib import Path

import pytest

from web.languages import get_adapter
from web.languages.base import INVARIABLE_PERSON, UnknownWord
from web.languages.it import catalogue, reverso
from web.languages.it.adapter import BLOCK_TENSES, to_paradigm

FIXTURES = Path(__file__).parent / "fixtures" / "reverso"


def page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def raw(verb: str) -> reverso.RawParadigm:
    return reverso.parse_paradigm(page(f"verb-{verb}.html"), verb, catalogue.person_key)


def paradigm(verb: str):
    return to_paradigm(raw(verb))


# ---- the source's shape --------------------------------------------------

def test_every_published_block_is_parsed():
    """Reverso publishes twenty; the adapter drills ten and drops the rest."""
    titles = {title for title, _ in raw("parlare").cells}
    assert len(titles) == 20
    assert "Indicativo Passato prossimo" in titles      # compound, published
    assert set(BLOCK_TENSES) <= titles                  # every drilled one present


def test_compound_tenses_never_reach_the_paradigm():
    """The row count of a compound tense depends on the verb, so none are
    drilled — see the catalogue docstring."""
    assert set(paradigm("parlare").tenses_present) == set(catalogue.TENSE_KEYS)
    for verb in ("parlare", "arrivare", "correre"):
        cells = paradigm(verb).cells
        assert all(" " not in cell.answer for cell in cells.values()), verb


def test_a_compound_tense_carries_its_auxiliary_if_ever_read():
    """Not drilled, but the parser keeps auxiliary + participle together so a
    future reader gets "ho parlato" rather than a bare "parlato"."""
    assert raw("parlare").cells[("Indicativo Passato prossimo", "io")] == ["ho parlato"]


def _published_rows(verb: str, title: str) -> int:
    """How many <li> rows the source prints under one block heading.

    Counted from the HTML rather than from a parsed paradigm: the point being
    measured is that the rows outnumber the persons, which a dict keyed by
    person cannot show.
    """
    html = page(f"verb-{verb}.html")
    starts = [m.start() for m in re.finditer(r'<div[^>]*blue-box-wrap', html)]
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(html)
        block = html[start:end]
        if f'mobile-title="{title}"' in block:
            return len(re.findall(r"<li\b", block))
    raise AssertionError(f"no {title} block in {verb}")


@pytest.mark.parametrize(
    "verb,rows",
    [("parlare", 6), ("arrivare", 8), ("correre", 14)],
)
def test_essere_agreement_is_why_compounds_are_out(verb, rows):
    """One compound tense, three different row counts.

    avere gives six. essere gives eight, because the participle agrees in
    gender and number. A verb taking both auxiliaries in different senses
    gives fourteen. A single answer per (tense, person) cannot hold that, which
    is the whole reason these tenses are not drilled.
    """
    assert _published_rows(verb, "Indicativo Passato prossimo") == rows
    # Six persons, whichever it is — so the extra rows have nowhere to go.
    assert len(catalogue.PERSONS) == 6


# ---- persons -------------------------------------------------------------

def test_voi_is_drilled_unlike_portuguese_vos():
    cells = paradigm("parlare").cells
    assert cells[("presente", "voi")].answer == "parlate"
    assert "voi" in get_adapter("it").drill_persons


def test_the_subjunctive_che_is_stripped_and_shown_as_a_label():
    """Reverso prints "che io"; the stored answer is the bare form and the cue
    comes back as a row label."""
    cells = paradigm("parlare").cells
    assert cells[("congiuntivo_presente", "io")].answer == "parli"
    assert catalogue.person_label("congiuntivo_presente", "io") == "che io"


def test_the_imperative_rows_are_positional_and_labelled_politely():
    """Reverso prints no pronouns for the imperative. The five rows are
    tu/Lei/noi/voi/Loro — the 3rd-person ones are the polite forms, so they
    must not be labelled "lui/lei"."""
    cells = paradigm("parlare").cells
    assert cells[("imperativo", "tu")].answer == "parla"
    assert cells[("imperativo", "lui")].answer == "parli"
    assert cells[("imperativo", "loro")].answer == "parlino"
    assert ("imperativo", "io") not in cells        # Italian has none
    assert catalogue.person_label("imperativo", "lui") == "Lei"
    assert catalogue.person_label("presente", "lui") == "lui/lei"


def test_personless_forms_land_on_the_invariable_person():
    cells = paradigm("parlare").cells
    assert cells[("gerundio", INVARIABLE_PERSON)].answer == "parlando"
    assert cells[("participio_passato", INVARIABLE_PERSON)].answer == "parlato"
    assert catalogue.person_label("gerundio", INVARIABLE_PERSON) == ""


# ---- alternatives --------------------------------------------------------

def test_a_cell_with_alternatives_keeps_them_all():
    """andare's imperative offers va' and vai, both current."""
    cell = paradigm("andare").cells[("imperativo", "tu")]
    assert cell.forms == ("va'", "vai")
    assert cell.answer == "va'"
    assert cell.alternatives == ("vai",)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("va'/vai", ["va'", "vai"]),
        ("parlo", ["parlo"]),
        ("a  /  b", ["a", "b"]),   # cplp.org's spacing, harmlessly accepted
        ("", []),
    ],
)
def test_split_forms(text, expected):
    assert reverso.split_forms(text) == expected


# ---- failure -------------------------------------------------------------

def test_a_page_with_no_paradigm_is_not_found():
    with pytest.raises(reverso.WordNotFound):
        reverso.parse_paradigm(page("notfound-tavolo.html"), "tavolo", catalogue.person_key)


def test_a_noun_is_only_ever_unknown_never_not_a_verb():
    """Reverso answers 404 identically for a noun and for nonsense, so the
    adapter cannot raise NotAVerb — only UnknownWord."""
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def paradigm(self, word, person_key):
            raise reverso.WordNotFound(word)

    adapter = get_adapter("it")
    import web.languages.it.adapter as mod

    original, mod.reverso.ReversoClient = mod.reverso.ReversoClient, lambda: _Client()
    try:
        with pytest.raises(UnknownWord):
            asyncio.run(adapter.paradigm("tavolo"))
    finally:
        mod.reverso.ReversoClient = original
