"""Italian.

Paradigms come from Reverso, which publishes twenty blocks per verb. Ten are
drilled; the mapping below is the whole of the selection, and a block absent
from it is simply never read. That is where the compound tenses go — see
``catalogue`` for why they are out.

Two shapes need work that Portuguese's source did not:

**The imperative has no pronouns.** Reverso prints five bare forms, which the
parser fills in positionally (tu, Lei, noi, voi, Loro). It publishes no negative
imperative at all; Italian's rule for one is mechanical (``non`` + infinitive
for ``tu``, ``non`` + the affirmative form otherwise) but deriving forms is
exactly what this project does not do — the source is taken as given — so the
negative imperative is not drilled.

**The subjunctive's ``che`` is part of the pronoun.** ``che io`` is a cue word
plus a person, and the stored answer is the bare verb form, so the ``che`` is
stripped on the way in and re-added as a row label on the way out.
"""

from __future__ import annotations

from ..base import (
    INVARIABLE_PERSON,
    Cell,
    NotAVerb,  # noqa: F401 - part of the adapter contract, never raised here
    Paradigm,
    PromptMaterial,
    SourceUnavailable,
    UnknownWord,
    resolve_tense_prefs,
)
from . import prompts, reverso
from .catalogue import (
    ACCENTS,
    DRILL_PERSONS,
    GERUND_TENSE,
    NAME,
    NOT_FOUND_HINT,
    PAST_PARTICIPLE_TENSE,
    SOURCE_NAME,
    TENSE_KEYS,
    TENSES,
    person_key,
)
from .catalogue import person_label as _it_person_label
from .regular import classify

CODE = "it"

# Reverso's ``mobile-title`` -> this project's tense key. The ten drilled
# tenses, all simple. Everything else Reverso publishes — the eight compound
# tenses, ``Infinito Presente``, ``Participio Presente`` — is absent on purpose
# and is dropped without comment.
BLOCK_TENSES: dict[str, str] = {
    "Indicativo Presente": "presente",
    "Indicativo Imperfetto": "imperfetto",
    "Indicativo Passato remoto": "passato_remoto",
    "Indicativo Futuro semplice": "futuro_semplice",
    "Congiuntivo Presente": "congiuntivo_presente",
    "Congiuntivo Imperfetto": "congiuntivo_imperfetto",
    "Condizionale Presente": "condizionale_presente",
    "Imperativo Presente": "imperativo",
    "Gerundio Presente": GERUND_TENSE,
    "Participio Passato": PAST_PARTICIPLE_TENSE,
}

# Blocks whose single row has no person at all.
_PERSONLESS_TENSES = frozenset({GERUND_TENSE, PAST_PARTICIPLE_TENSE})


def to_paradigm(raw: reverso.RawParadigm) -> Paradigm:
    """Keep the drilled blocks, key them by tense, drop the rest."""
    paradigm = Paradigm(infinitive=raw.infinitive)
    for (title, person), forms in raw.cells.items():
        tense = BLOCK_TENSES.get(title)
        if tense is None or not forms:
            continue
        if tense in _PERSONLESS_TENSES:
            person = INVARIABLE_PERSON
        elif not person:
            continue
        paradigm.cells[(tense, person)] = Cell(forms=tuple(forms))
    return paradigm


class ItalianAdapter:
    """The ``it`` implementation of ``LanguageAdapter``."""

    code = CODE

    @property
    def name(self) -> str:
        return NAME

    @property
    def source_name(self) -> str:
        return SOURCE_NAME

    @property
    def not_found_hint(self) -> str:
        return NOT_FOUND_HINT

    @property
    def accents(self) -> list[str]:
        return ACCENTS

    @property
    def tenses(self) -> list[dict]:
        return TENSES

    @property
    def tense_keys(self) -> list[str]:
        return TENSE_KEYS

    @property
    def drill_persons(self) -> list[str]:
        return DRILL_PERSONS

    @property
    def past_participle_tense(self) -> str:
        return PAST_PARTICIPLE_TENSE

    @property
    def present_participle_tense(self) -> str:
        # Italian's gerund fills the slot pt-PT calls the present participle.
        # (Reverso's own "Participio presente" — parlante — is adjectival and
        # is not drilled.)
        return GERUND_TENSE

    def person_label(self, tense: str, person: str) -> str:
        return _it_person_label(tense, person)

    def resolve_tense_prefs(self, saved: list[dict]) -> list[dict]:
        return resolve_tense_prefs(saved, TENSES)

    def describe(self, paradigm: Paradigm) -> str:
        return classify(paradigm).describe()

    def prompt_material(self) -> PromptMaterial:
        return prompts.prompt_material()

    async def paradigm(self, infinitive: str) -> Paradigm:
        verb = " ".join(infinitive.split()).strip().lower()
        if not verb:
            raise UnknownWord(infinitive)
        try:
            async with reverso.ReversoClient() as client:
                raw = await client.paradigm(verb, person_key)
        except reverso.WordNotFound as exc:
            # Reverso cannot tell a noun from a typo, so this is the only
            # lookup failure it can report; NotAVerb is never raised here.
            raise UnknownWord(verb) from exc
        except reverso.SourceUnavailable as exc:
            raise SourceUnavailable(str(exc)) from exc
        return to_paradigm(raw)
