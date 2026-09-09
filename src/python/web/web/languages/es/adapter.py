"""Spanish.

Paradigms come from Reverso, which publishes twenty-four blocks per verb.
Sixteen are drilled; ``BLOCK_TENSES`` below is the whole of the selection, and a
block absent from it is never read. See ``catalogue`` for what is dropped and
why.

The RAE would be the normative source here — the Spanish counterpart to the
vocabulary cplp.org publishes for Portuguese — but dle.rae.es sits behind a
Cloudflare browser challenge and answers 403 to any server-side fetch. Reverso
is a commercial aggregator with good tables and no standing, so nothing
downstream should treat it the way the ``pt`` path reasonably treats cplp.org.

Three shapes need work that Italian's use of the same source did not:

**Two blocks make one cell.** Reverso publishes the imperfect subjunctive twice
— ``hablara`` and ``hablase`` — and likewise the pluperfect subjunctive. They
are alternatives in one cell rather than two tenses, which is exactly what
``Cell.forms`` is for. The ``-ra`` block is mapped first because it is the form
US textbooks teach and ``forms[0]`` is what the drill displays; ``-se`` grades
as correct and is reported afterwards.

**Reflexive verbs hide the person.** ``levantarse`` prints ``me levanto`` with
the clitic in ``particletxt`` and no pronoun at all, so the person is
positional — see ``catalogue.positional_persons``. The clitic is kept in the
answer, because ``levanto`` on its own is not the verb.

**No negative imperative**, as in Italian: Reverso does not publish one and this
project does not derive forms. Little is lost — Spanish's negative imperative is
the present subjunctive, which is drilled in its own right.
"""

from __future__ import annotations

from .. import reverso
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
from . import prompts
from .catalogue import (
    ACCENTS,
    DRILL_PERSONS,
    GERUND_TENSE,
    NAME,
    NOT_FOUND_HINT,
    PAST_PARTICIPLE_TENSE,
    PERSONS,
    SOURCE_NAME,
    TENSE_KEYS,
    TENSES,
    person_key,
    positional_persons,
)
from .catalogue import person_label as _es_person_label
from .regular import classify

CODE = "es"

# What Reverso's Spanish edition looks like. ``particletxt`` holds a reflexive
# verb's clitic, which belongs to the answer — the opposite of Italian, where
# the same element holds the subjunctive's ``che`` and is dropped.
SITE = reverso.Site(
    language="spanish",
    personless_titles=("Gerundio", "Participio", "Infinitivo"),
    positional_persons=positional_persons,
    particle_in_form=True,
)

# Reverso's ``mobile-title`` -> this project's tense key. Two titles may share a
# key; insertion order decides which form the drill displays, so the ``-ra``
# blocks come first.
BLOCK_TENSES: dict[str, str] = {
    "Indicativo Presente": "presente",
    "Indicativo Pretérito imperfecto": "imperfecto",
    "Indicativo Pretérito perfecto simple": "preterito",
    "Indicativo Futuro": "futuro",
    "Indicativo Condicional": "condicional",
    "Subjuntivo Presente": "subjuntivo_presente",
    "Subjuntivo Pretérito imperfecto": "subjuntivo_imperfecto",
    "Subjuntivo Pretérito imperfecto (2)": "subjuntivo_imperfecto",
    "Imperativo": "imperativo",
    "Indicativo Pretérito perfecto compuesto": "perfecto",
    "Indicativo Pretérito pluscuamperfecto": "pluscuamperfecto",
    "Indicativo Futuro perfecto": "futuro_perfecto",
    "Indicativo Condicional perfecto": "condicional_perfecto",
    "Subjuntivo Pretérito perfecto": "subjuntivo_perfecto",
    "Subjuntivo Pretérito pluscuamperfecto": "subjuntivo_pluscuamperfecto",
    "Subjuntivo Pretérito pluscuamperfecto (2)": "subjuntivo_pluscuamperfecto",
    "Gerundio": GERUND_TENSE,
    "Participio Pasado": PAST_PARTICIPLE_TENSE,
}

# Blocks whose single row has no person at all.
_PERSONLESS_TENSES = frozenset({GERUND_TENSE, PAST_PARTICIPLE_TENSE})

# A Spanish infinitive ends in -ar, -er or -ir, so one ending in -se can only be
# an infinitive with the reflexive clitic stuck on it. "ír" covers reírse and
# sonreírse.
_INFINITIVE_ENDINGS = ("ar", "er", "ir", "ír")


def plain_infinitive(infinitive: str) -> str | None:
    """``levantarse`` -> ``levantar``; ``None`` if it isn't a reflexive infinitive."""
    if not infinitive.endswith("se"):
        return None
    stem = infinitive[:-2]
    # ``ir`` is the shortest real Spanish infinitive, so two letters is the
    # floor rather than something to guard against: ``irse`` is a real verb.
    return stem if len(stem) >= 2 and stem.endswith(_INFINITIVE_ENDINGS) else None


def to_paradigm(raw: reverso.RawParadigm) -> Paradigm:
    """Keep the drilled blocks, key them by tense, drop the rest.

    Merges rather than assigns: two blocks share a tense key for each of the
    imperfect and pluperfect subjunctives, and a cell that already exists gains
    the second block's forms as alternatives. Duplicates are dropped — the two
    blocks coincide where a verb has only one form — and order is preserved, so
    the ``-ra`` form stays first.
    """
    paradigm = Paradigm(infinitive=raw.infinitive)
    # Iterated in ``BLOCK_TENSES`` order rather than the page's. Reverso
    # happens to print the ``-ra`` blocks first today, so the two orders agree,
    # but which form leads is a teaching decision and should not be one page
    # re-layout away from flipping.
    for title, tense in BLOCK_TENSES.items():
        for person in (*PERSONS, ""):
            forms = raw.cells.get((title, person))
            if not forms:
                continue
            if tense in _PERSONLESS_TENSES:
                person = INVARIABLE_PERSON
            elif not person:
                continue
            existing = paradigm.cells.get((tense, person))
            merged = list(existing.forms) if existing else []
            merged += [f for f in forms if f not in merged]
            paradigm.cells[(tense, person)] = Cell(forms=tuple(merged))
    return paradigm


class SpanishAdapter:
    """The ``es`` implementation of ``LanguageAdapter``."""

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
    def contrastive_rows(self) -> list[tuple[str, str, str]]:
        return []  # Spanish has one participle, so no row mirrors another.

    @property
    def drill_persons(self) -> list[str]:
        return DRILL_PERSONS

    @property
    def past_participle_tense(self) -> str:
        return PAST_PARTICIPLE_TENSE

    @property
    def present_participle_tense(self) -> str:
        # Spanish's gerund fills the slot pt-PT calls the present participle.
        return GERUND_TENSE

    def person_label(self, tense: str, person: str) -> str:
        return _es_person_label(tense, person)

    def substitute(self, infinitive: str) -> tuple[str, str] | None:
        """Add the plain verb when a reflexive infinitive is typed.

        A reflexive adds no conjugation. Measured against ``levantar``, the 85
        cells of ``levantarse`` are one identical (the participle takes no
        clitic), 78 that are the same conjugated form with a fixed pronoun in
        front, and 6 where the pronoun fuses onto the end. Even those six leave
        the conjugation alone — ``levanta``, ``levantemos``, ``levantad`` — and
        differ only in how the fused word is spelled. So drilling one asks for
        the same six-item pronoun list eighty times and teaches nothing a
        conjugation drill exists to teach.

        The pronoun is a separate axis, not part of the verb: ``te levanto``
        ("I get you up") is equally good Spanish. Drilling the reflexive would
        cover only the slice of that axis where the object is the subject.

        Nothing is lost by substituting. The reflexive *sense* still reaches the
        learner through the example sentences, which are told to mix it with the
        plain one — see ``guidance.json``.

        Idempotent, because ``plain_infinitive`` returns ``None`` for a verb
        that does not end in a clitic, and the value it returns never does.

        For a reflexive-only verb such as ``quejarse`` the named plain verb is
        not current Spanish on its own, but this claims only that it conjugates
        identically, which is true — and Reverso publishes it.
        """
        plain = plain_infinitive(infinitive)
        if plain is None:
            return None
        return plain, (
            f'"{infinitive}" is reflexive, and the pronoun (me/te/se/nos/os) is '
            f"the same for every verb rather than part of the conjugation — so "
            f'"{plain}" is what gets drilled, and its example sentences use both '
            f"senses."
        )

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
            async with reverso.ReversoClient(SITE) as client:
                raw = await client.paradigm(verb, person_key)
        except reverso.WordNotFound as exc:
            # Reverso cannot tell a noun from a typo, so this is the only
            # lookup failure it can report; NotAVerb is never raised here.
            raise UnknownWord(verb) from exc
        except reverso.SourceUnavailable as exc:
            raise SourceUnavailable(str(exc)) from exc
        return to_paradigm(raw)
