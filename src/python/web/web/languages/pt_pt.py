"""European Portuguese.

Paradigms come from cplp.org's Portugal edition, which publishes the vocabulary
the Acordo Ortográfico mandates. That source is normative but *pan-lusophone*:
its tables are identical under the Portugal and Brazil editions, so it certifies
that a form is legitimate somewhere in the language without saying which form
Portugal uses. Two consequences shape this module.

**One selection rule.** Exactly one variety split is decidable mechanically —
the 1st person plural preterite of ``-ar`` verbs, where pt-PT writes the accent
(``falámos``) and pt-BR does not. Everything else the source offers in a cell is
kept: ``oiço``/``ouço`` are both current European Portuguese, and no rule in the
Acordo distinguishes them.

**The participle split.** The source publishes the past participle as one
unlabelled set — ``aceitar`` gives ``aceitado / aceite / aceito`` — but the two
forms are used differently, the regular one with *ter*/*haver* and the short one
with *ser*/*estar*. Which is which is recoverable by deriving the regular form
from the infinitive, so the drill can ask for both.
"""

from __future__ import annotations

from ..conjugation import (
    DRILL_PERSONS,
    INVARIABLE_PERSON,
    PAST_PARTICIPLE_TENSE,
    PRESENT_PARTICIPLE_TENSE,
    SHORT_PERSON,
    TENSES,
)
from ..conjugation import person_label as _pt_person_label
from . import cplp
from .base import Cell, NotAVerb, Paradigm, SourceUnavailable, UnknownWord

CODE = "pt-PT"

# Tenses whose 1st person plural takes the pt-PT acute. Only the preterite is
# affected; the present indicative "falamos" is unaccented and unambiguous.
_ACCENTED_PRETERITE_TENSE = "preterite"


def select_preterite_nos(infinitive: str, forms: list[str]) -> list[str]:
    """Resolve ``falámos / falamos`` for an ``-ar`` verb to the pt-PT form.

    AO90 Base IX calls the accent *facultativo*, but ties it to the stressed
    vowel being open *"em certas variantes do português"* — European Portuguese
    is that variant, and there the accent is what distinguishes the preterite
    from the present (``falamos``). So for a pt-PT drill the accented form is
    the answer and the bare one is not an alternative.

    Chosen by rule rather than by position: the source's ordering is not a
    preference signal (``falar`` lists the accented form first, ``aceitar`` the
    unaccented one).
    """
    if not infinitive.endswith("ar") or len(forms) < 2:
        return forms
    accented = [f for f in forms if f.endswith("ámos")]
    return accented[:1] if accented else forms


def derive_regular_participle(infinitive: str) -> str | None:
    """The predictable participle: stem + ``-ado`` / ``-ido``.

    Used to tell the regular participle apart from the short one inside the
    single set the source publishes. Returns ``None`` for an infinitive that
    isn't one of the three conjugations (``pôr`` and its compounds).
    """
    for ending, suffix in (("ar", "ado"), ("er", "ido"), ("ir", "ido")):
        if infinitive.endswith(ending):
            return infinitive[: -len(ending)] + suffix
    return None


def split_participles(infinitive: str, forms: list[str]) -> tuple[list[str], list[str]]:
    """``(with ter/haver, with ser/estar)`` from the source's single set.

    - one form → both rows get it, which is the common case
    - regular form present → it takes ter/haver, the rest take ser/estar
    - regular form absent → both rows get what there is. This is ``abrir`` →
      ``aberto``, ``escrever`` → ``escrito``: no regular participle exists and
      *tinha aberto* is correct.
    """
    if not forms:
        return [], []
    regular = derive_regular_participle(infinitive)
    if regular is None or regular not in forms:
        return list(forms), list(forms)
    short = [f for f in forms if f != regular]
    return [regular], short or [regular]


def _to_paradigm(raw: cplp.RawParadigm) -> Paradigm:
    paradigm = Paradigm(infinitive=raw.infinitive)

    for (tense, person), forms in raw.cells.items():
        if person not in DRILL_PERSONS and person != "vos":
            continue
        if tense == _ACCENTED_PRETERITE_TENSE and person == "nos":
            forms = select_preterite_nos(raw.infinitive, forms)
        if forms:
            paradigm.cells[(tense, person)] = Cell(forms=tuple(forms))

    regular, short = split_participles(raw.infinitive, raw.past_participle)
    if regular:
        paradigm.cells[(PAST_PARTICIPLE_TENSE, INVARIABLE_PERSON)] = Cell(tuple(regular))
    if short:
        paradigm.cells[(PAST_PARTICIPLE_TENSE, SHORT_PERSON)] = Cell(tuple(short))
    if raw.present_participle:
        paradigm.cells[(PRESENT_PARTICIPLE_TENSE, INVARIABLE_PERSON)] = Cell(
            tuple(raw.present_participle)
        )
    return paradigm


class PortugueseAdapter:
    """The ``pt-PT`` implementation of ``LanguageAdapter``."""

    code = CODE

    @property
    def tenses(self) -> list[dict]:
        return TENSES

    @property
    def drill_persons(self) -> list[str]:
        return DRILL_PERSONS

    def person_label(self, tense: str, person: str) -> str:
        return _pt_person_label(tense, person)

    async def paradigm(self, infinitive: str) -> Paradigm:
        verb = " ".join(infinitive.split()).strip().lower()
        if not verb:
            raise UnknownWord(infinitive)
        try:
            async with cplp.CplpClient(edition="pt") as client:
                raw = await client.paradigm(verb)
        except cplp.NotAVerb as exc:
            raise NotAVerb(verb) from exc
        except cplp.WordNotFound as exc:
            raise UnknownWord(verb) from exc
        except cplp.SourceUnavailable as exc:
            raise SourceUnavailable(str(exc)) from exc
        return _to_paradigm(raw)
