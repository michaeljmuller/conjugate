"""Parsing Reverso and turning it into a Spanish paradigm.

Runs against saved pages — no network. The fixtures were chosen for what they
break: `levantarse` is reflexive, so Reverso replaces the pronoun column with a
clitic and the persons have to be recovered positionally; `erguir` puts
alternatives in a cell (`yergo/irgo`); `ir` and `ser` are suppletive; `oler`
grows an h in the stem-changing forms; `buscar` and `coger` need a spelling
change in opposite directions; and `xyzzyq` is Reverso's 404.
"""

import asyncio
from pathlib import Path

import pytest

from web.languages import get_adapter, reverso
from web.languages.base import INVARIABLE_PERSON, UnknownWord
from web.languages.es import catalogue
from web.languages.es.adapter import BLOCK_TENSES, SITE, to_paradigm

FIXTURES = Path(__file__).parent / "fixtures" / "reverso"


def page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def raw(verb: str) -> reverso.RawParadigm:
    return reverso.parse_paradigm(
        page(f"es-verb-{verb}.html"), verb, catalogue.person_key, SITE
    )


def paradigm(verb: str):
    return to_paradigm(raw(verb))


# ---- the source's shape --------------------------------------------------

def test_every_published_block_is_parsed():
    """Reverso publishes twenty-four; the adapter drills sixteen of them."""
    titles = {title for title, _ in raw("hablar").cells}
    assert len(titles) == 24
    assert "Indicativo Pretérito anterior" in titles     # published, not drilled
    assert set(BLOCK_TENSES) <= titles                   # every drilled one present


def test_the_dead_tenses_are_dropped():
    """The future subjunctive and the pretérito anterior are published in full
    and drilled by nobody. pt drills its future subjunctive because Portuguese
    still uses it; Spanish is where the tense died."""
    assert set(paradigm("hablar").tenses_present) == set(catalogue.TENSE_KEYS)
    # Published in full...
    assert raw("hablar").cells[("Subjuntivo Futuro", "yo")] == ["hablare"]
    assert raw("hablar").cells[("Indicativo Pretérito anterior", "yo")] == ["hube hablado"]
    # ...and nowhere in the drill.
    forms = {f for cell in paradigm("hablar").cells.values() for f in cell.forms}
    assert "hablare" not in forms
    assert "hube hablado" not in forms


def test_compound_tenses_are_drilled_and_carry_their_auxiliary():
    """Unlike Italian's. After haber the participle never agrees, so every
    compound tense is exactly six rows and fits the schema unchanged."""
    cells = paradigm("hablar").cells
    assert cells[("perfecto", "yo")].answer == "he hablado"
    assert cells[("pluscuamperfecto", "nos")].answer == "habíamos hablado"
    assert cells[("futuro_perfecto", "ellos")].answer == "habrán hablado"
    assert cells[("condicional_perfecto", "tu")].answer == "habrías hablado"
    assert cells[("subjuntivo_perfecto", "vos")].answer == "hayáis hablado"
    for tense in ("perfecto", "pluscuamperfecto", "futuro_perfecto"):
        rows = [p for t, p in cells if t == tense]
        assert sorted(rows) == sorted(catalogue.PERSONS), tense


# ---- two blocks, one cell ------------------------------------------------

def test_the_imperfect_subjunctive_merges_its_two_blocks():
    """Reverso publishes -ra and -se as separate blocks. They are alternatives
    in one cell, and the -ra form leads because that is what is taught."""
    cell = paradigm("hablar").cells[("subjuntivo_imperfecto", "yo")]
    assert cell.forms == ("hablara", "hablase")
    assert cell.answer == "hablara"
    assert cell.alternatives == ("hablase",)


def test_the_pluperfect_subjunctive_merges_the_same_way():
    cell = paradigm("hablar").cells[("subjuntivo_pluscuamperfecto", "yo")]
    assert cell.forms == ("hubiera hablado", "hubiese hablado")


def test_the_merge_order_follows_the_map_not_the_page():
    """Reverso prints the -ra blocks first today, so the two orders agree. Which
    form leads is a teaching decision, though, and should not be one page
    re-layout away from flipping — so feed the blocks in backwards."""
    backwards = reverso.RawParadigm(infinitive="hablar")
    for key, forms in reversed(list(raw("hablar").cells.items())):
        backwards.cells[key] = forms
    cells = to_paradigm(backwards).cells
    assert cells[("subjuntivo_imperfecto", "yo")].forms == ("hablara", "hablase")
    assert cells[("subjuntivo_pluscuamperfecto", "yo")].forms == (
        "hubiera hablado",
        "hubiese hablado",
    )


def test_a_merge_does_not_duplicate_a_shared_form():
    """Where the two blocks coincide the cell keeps one form, not two."""
    for cell in paradigm("ser").cells.values():
        assert len(cell.forms) == len(set(cell.forms))


# ---- persons -------------------------------------------------------------

def test_vosotros_is_drilled_unlike_portuguese_vos():
    """The opposite of the pt-PT call: vós is archaic, vosotros is everyday
    speech in Spain and US textbooks print the row."""
    cells = paradigm("hablar").cells
    assert cells[("presente", "vos")].answer == "habláis"
    assert "vos" in get_adapter("es").drill_persons
    assert catalogue.person_label("presente", "vos") == "vosotros"


def test_the_subjunctive_que_is_a_label_not_a_stored_form():
    """Unlike Italian's "che", Reverso does not print "que" at all, so nothing
    is stripped — the cue exists only as a row label."""
    cells = paradigm("hablar").cells
    assert cells[("subjuntivo_presente", "yo")].answer == "hable"
    assert catalogue.person_label("subjuntivo_presente", "yo") == "que yo"
    assert catalogue.person_label("subjuntivo_pluscuamperfecto", "el") == "que él/ella/Ud."


def test_the_imperative_has_five_rows_labelled_politely():
    """Spanish has no first-person-singular imperative, and its 3rd-person rows
    address Ud./Uds. rather than him or her."""
    cells = paradigm("hablar").cells
    assert cells[("imperativo", "tu")].answer == "habla"
    assert cells[("imperativo", "el")].answer == "hable"
    assert cells[("imperativo", "vos")].answer == "hablad"
    assert ("imperativo", "yo") not in cells
    assert catalogue.person_label("imperativo", "el") == "Ud."
    assert catalogue.person_label("presente", "el") == "él/ella/Ud."


def test_personless_forms_land_on_the_invariable_person():
    cells = paradigm("hablar").cells
    assert cells[("gerundio", INVARIABLE_PERSON)].answer == "hablando"
    assert cells[("participio", INVARIABLE_PERSON)].answer == "hablado"
    assert catalogue.person_label("gerundio", INVARIABLE_PERSON) == ""


# ---- reflexives ----------------------------------------------------------

def test_a_reflexive_keeps_its_clitic_in_the_answer():
    """"levanto" on its own is not the verb. Reverso puts the clitic in
    particletxt, which Spanish keeps and Italian drops — the same element does
    a different job in each language."""
    cells = paradigm("levantarse").cells
    assert cells[("presente", "yo")].answer == "me levanto"
    assert cells[("presente", "vos")].answer == "os levantáis"
    # Clitic, then auxiliary, then participle — the order Reverso prints them.
    assert cells[("perfecto", "yo")].answer == "me he levantado"


def test_a_reflexive_recovers_its_persons_positionally():
    """The clitic displaces the pronoun, so there is nothing to look up: "se" is
    both third singular and third plural. The row's position is the only signal."""
    assert "se" not in {person for _, person in raw("levantarse").cells}
    cells = paradigm("levantarse").cells
    assert cells[("presente", "el")].answer == "se levanta"
    assert cells[("presente", "ellos")].answer == "se levantan"
    assert sorted({p for t, p in cells if t == "presente"}) == sorted(catalogue.PERSONS)


def test_a_reflexive_imperative_is_still_five_rows():
    """Five unlabelled rows, where the reflexive's other blocks have six — which
    is what tells positional_persons which list to use."""
    cells = paradigm("levantarse").cells
    assert cells[("imperativo", "tu")].answer == "levántate"
    assert cells[("imperativo", "vos")].answer == "levantaos"
    assert ("imperativo", "yo") not in cells


def test_a_reflexive_participle_carries_no_clitic():
    """The bare participle takes none, though the gerund does."""
    cells = paradigm("levantarse").cells
    assert cells[("participio", INVARIABLE_PERSON)].answer == "levantado"
    assert cells[("gerundio", INVARIABLE_PERSON)].answer == "levantándose"


@pytest.mark.parametrize("title,rows,expected", [
    ("Imperativo", 5, catalogue.IMPERATIVE_PERSONS),
    ("Indicativo Presente", 6, catalogue.PERSONS),
])
def test_positional_persons_chooses_by_row_count(title, rows, expected):
    assert catalogue.positional_persons(title, rows) == expected


# ---- alternatives --------------------------------------------------------

def test_a_cell_with_alternatives_keeps_them_all():
    """erguir offers yergo and irgo, both current."""
    cell = paradigm("erguir").cells[("presente", "yo")]
    assert cell.forms == ("yergo", "irgo")
    assert cell.answer == "yergo"
    assert cell.alternatives == ("irgo",)


# ---- failure -------------------------------------------------------------

def test_a_page_with_no_paradigm_is_not_found():
    with pytest.raises(reverso.WordNotFound):
        reverso.parse_paradigm(
            page("es-notfound-xyzzyq.html"), "xyzzyq", catalogue.person_key, SITE
        )


def test_a_noun_is_only_ever_unknown_never_not_a_verb():
    """Reverso answers 404 identically for a noun and for nonsense, so the
    adapter cannot raise NotAVerb — only UnknownWord. Spanish is worse than
    Italian here: a noun that happens to be an inflected verb form, such as
    "mesa", comes back 200 with the conjugation of "mesar"."""
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def paradigm(self, word, person_key):
            raise reverso.WordNotFound(word)

    adapter = get_adapter("es")
    import web.languages.es.adapter as mod

    original, mod.reverso.ReversoClient = mod.reverso.ReversoClient, lambda _site: _Client()
    try:
        with pytest.raises(UnknownWord):
            asyncio.run(adapter.paradigm("xyzzyq"))
    finally:
        mod.reverso.ReversoClient = original


# ---- the site config -----------------------------------------------------

def test_the_two_languages_read_the_same_source_differently():
    """One parser, two Sites. The particle is the interesting difference: a
    Spanish clitic is part of the answer, an Italian "che" is not."""
    import web.languages.it.adapter as it

    assert SITE.language == "spanish" and it.SITE.language == "italian"
    assert SITE.particle_in_form and not it.SITE.particle_in_form
    # Spanish writes "Infinitivo" where Italian writes "Infinito", so the
    # personless titles cannot be one shared tuple.
    assert "Infinitivo" in SITE.personless_titles
    assert "Infinito" in it.SITE.personless_titles
