"""Is this verb entirely predictable from its infinitive?

A regular verb teaches nothing a learner doesn't already know from the model
verb, so the drill warns before adding one. "Regular" here means the strongest
possible claim: *every* cell the source publishes is exactly what the ending
table below produces from the infinitive. Anything else — an odd stem, a second
participle, a cell with alternatives — makes the verb irregular and worth
drilling.

The table is not typed from memory. ``tools/regular_endings.py`` regenerates it
by fetching cplp.org's own ``falar`` / ``comer`` / ``partir`` and subtracting
the stem, so the endings come from the same normative source as the verbs they
are compared against, and the pt-PT ``-ámos`` selection is already applied.

Errors here are one-sided by construction. A missing spelling rule makes a
regular verb look irregular, which merely skips the warning; the reverse —
calling an irregular verb regular — would need the table to reproduce an
irregular paradigm exactly, which it cannot.
"""

from __future__ import annotations

from .base import Paradigm

# Ending per conjugation, in this order.
CONJUGATIONS = ("ar", "er", "ir")

# (tense, person) -> the -ar, -er, -ir ending. Generated; see the module
# docstring before editing by hand.
ENDINGS: dict[tuple[str, str], tuple[str, str, str]] = {
    ("conditional", "eu"): ("aria", "eria", "iria"),
    ("conditional", "tu"): ("arias", "erias", "irias"),
    ("conditional", "ele"): ("aria", "eria", "iria"),
    ("conditional", "nos"): ("aríamos", "eríamos", "iríamos"),
    ("conditional", "vos"): ("aríeis", "eríeis", "iríeis"),
    ("conditional", "eles"): ("ariam", "eriam", "iriam"),
    ("future_indicative", "eu"): ("arei", "erei", "irei"),
    ("future_indicative", "tu"): ("arás", "erás", "irás"),
    ("future_indicative", "ele"): ("ará", "erá", "irá"),
    ("future_indicative", "nos"): ("aremos", "eremos", "iremos"),
    ("future_indicative", "vos"): ("areis", "ereis", "ireis"),
    ("future_indicative", "eles"): ("arão", "erão", "irão"),
    ("future_subjunctive", "eu"): ("ar", "er", "ir"),
    ("future_subjunctive", "tu"): ("ares", "eres", "ires"),
    ("future_subjunctive", "ele"): ("ar", "er", "ir"),
    ("future_subjunctive", "nos"): ("armos", "ermos", "irmos"),
    ("future_subjunctive", "vos"): ("ardes", "erdes", "irdes"),
    ("future_subjunctive", "eles"): ("arem", "erem", "irem"),
    ("imperative_affirmative", "tu"): ("a", "e", "e"),
    ("imperative_affirmative", "ele"): ("e", "a", "a"),
    ("imperative_affirmative", "nos"): ("emos", "amos", "amos"),
    ("imperative_affirmative", "vos"): ("ai", "ei", "i"),
    ("imperative_affirmative", "eles"): ("em", "am", "am"),
    ("imperative_negative", "tu"): ("es", "as", "as"),
    ("imperative_negative", "ele"): ("e", "a", "a"),
    ("imperative_negative", "nos"): ("emos", "amos", "amos"),
    ("imperative_negative", "vos"): ("eis", "ais", "ais"),
    ("imperative_negative", "eles"): ("em", "am", "am"),
    ("past_imperfect_indicative", "eu"): ("ava", "ia", "ia"),
    ("past_imperfect_indicative", "tu"): ("avas", "ias", "ias"),
    ("past_imperfect_indicative", "ele"): ("ava", "ia", "ia"),
    ("past_imperfect_indicative", "nos"): ("ávamos", "íamos", "íamos"),
    ("past_imperfect_indicative", "vos"): ("áveis", "íeis", "íeis"),
    ("past_imperfect_indicative", "eles"): ("avam", "iam", "iam"),
    ("past_imperfect_subjunctive", "eu"): ("asse", "esse", "isse"),
    ("past_imperfect_subjunctive", "tu"): ("asses", "esses", "isses"),
    ("past_imperfect_subjunctive", "ele"): ("asse", "esse", "isse"),
    ("past_imperfect_subjunctive", "nos"): ("ássemos", "êssemos", "íssemos"),
    ("past_imperfect_subjunctive", "vos"): ("ásseis", "êsseis", "ísseis"),
    ("past_imperfect_subjunctive", "eles"): ("assem", "essem", "issem"),
    ("past_participle", "inv"): ("ado", "ido", "ido"),
    ("past_participle", "short"): ("ado", "ido", "ido"),
    ("past_pluperfect", "eu"): ("ara", "era", "ira"),
    ("past_pluperfect", "tu"): ("aras", "eras", "iras"),
    ("past_pluperfect", "ele"): ("ara", "era", "ira"),
    ("past_pluperfect", "nos"): ("áramos", "êramos", "íramos"),
    ("past_pluperfect", "vos"): ("áreis", "êreis", "íreis"),
    ("past_pluperfect", "eles"): ("aram", "eram", "iram"),
    ("personal_infinitive", "eu"): ("ar", "er", "ir"),
    ("personal_infinitive", "tu"): ("ares", "eres", "ires"),
    ("personal_infinitive", "ele"): ("ar", "er", "ir"),
    ("personal_infinitive", "nos"): ("armos", "ermos", "irmos"),
    ("personal_infinitive", "vos"): ("ardes", "erdes", "irdes"),
    ("personal_infinitive", "eles"): ("arem", "erem", "irem"),
    ("present_indicative", "eu"): ("o", "o", "o"),
    ("present_indicative", "tu"): ("as", "es", "es"),
    ("present_indicative", "ele"): ("a", "e", "e"),
    ("present_indicative", "nos"): ("amos", "emos", "imos"),
    ("present_indicative", "vos"): ("ais", "eis", "is"),
    ("present_indicative", "eles"): ("am", "em", "em"),
    ("present_participle", "inv"): ("ando", "endo", "indo"),
    ("present_subjunctive", "eu"): ("e", "a", "a"),
    ("present_subjunctive", "tu"): ("es", "as", "as"),
    ("present_subjunctive", "ele"): ("e", "a", "a"),
    ("present_subjunctive", "nos"): ("emos", "amos", "amos"),
    ("present_subjunctive", "vos"): ("eis", "ais", "ais"),
    ("present_subjunctive", "eles"): ("em", "am", "am"),
    ("preterite", "eu"): ("ei", "i", "i"),
    ("preterite", "tu"): ("aste", "este", "iste"),
    ("preterite", "ele"): ("ou", "eu", "iu"),
    ("preterite", "nos"): ("ámos", "emos", "imos"),
    ("preterite", "vos"): ("astes", "estes", "istes"),
    ("preterite", "eles"): ("aram", "eram", "iram"),
}

# Spelling changes that keep the stem's final consonant *sounding* the same when
# the ending flips the following vowel between front (e/i) and back (a/o/u).
# "jogar" -> "jogue", not "joge"; "conhecer" -> "conheço", not "conheco". These
# are spelling, not conjugation: a verb needing them is still regular, which is
# exactly why the comparison has to know about them.
_BEFORE_FRONT_VOWEL = (("ç", "c"), ("qu", "qu"), ("gu", "gu"), ("c", "qu"), ("g", "gu"))
_BEFORE_BACK_VOWEL = (("gu", "g"), ("qu", "c"), ("c", "ç"), ("g", "j"))

_FRONT_VOWELS = frozenset("ei")
_BACK_VOWELS = frozenset("aou")


def _join(stem: str, ending: str, conjugation: str) -> str:
    """Stem + ending, respelling the stem where the ending's vowel would
    otherwise change how its final consonant sounds.

    Only one direction can arise per conjugation, and getting that wrong invents
    forms: an ``-ar`` stem is already written against a back vowel (``fic-`` in
    ``ficar``), so only a front-vowel ending disturbs it (``fique``) and
    ``ficaria`` must be left alone. ``-er``/``-ir`` stems are the mirror image —
    ``conhec-`` is written against a front vowel, so only a back-vowel ending
    moves it (``conheço``), and ``conheceria`` stands.
    """
    rules, trigger = (
        (_BEFORE_FRONT_VOWEL, _FRONT_VOWELS)
        if conjugation == "ar"
        else (_BEFORE_BACK_VOWEL, _BACK_VOWELS)
    )
    if not ending or ending[0] not in trigger:
        return stem + ending
    for old, new in rules:
        if stem.endswith(old):
            return stem[: len(stem) - len(old)] + new + ending
    return stem + ending


def regular_forms(infinitive: str) -> dict[tuple[str, str], str] | None:
    """Every cell a fully regular verb of this shape would have.

    ``None`` for an infinitive outside the three conjugations (``pôr`` and its
    compounds), which is a closed class of irregular verbs anyway.
    """
    for index, conjugation in enumerate(CONJUGATIONS):
        if infinitive.endswith(conjugation) and len(infinitive) > len(conjugation):
            stem = infinitive[: -len(conjugation)]
            return {
                key: _join(stem, endings[index], conjugation)
                for key, endings in ENDINGS.items()
            }
    return None


def is_regular(paradigm: Paradigm) -> bool:
    """True when the paradigm holds nothing the ending table doesn't predict.

    Deliberately strict: the cells must match exactly, so a verb carrying an
    extra accepted form (``aceitar``'s short participle ``aceite``) counts as
    irregular and is added without a warning. That form is the whole reason to
    drill it.
    """
    expected = regular_forms(paradigm.infinitive)
    if expected is None or set(paradigm.cells) != set(expected):
        return False
    return all(cell.forms == (expected[key],) for key, cell in paradigm.cells.items())
