"""What a language has to provide to be drillable.

The drill itself knows nothing about Portuguese: it renders tense blocks of
person rows, grades typed answers, and stores what it is given. Everything
language-specific — which tenses exist, how a row is labelled, where paradigms
come from, and which of several legitimate forms to display — lives behind
``LanguageAdapter``.

Adding a language is therefore a new adapter plus a source for it; ``jobs.py``,
``api.py`` and the front end never learn that more than one exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# Placeholder person for forms that have none — participles, gerunds. Every
# language has some, so the key is shared vocabulary rather than one language's
# invention; real conjugations never use it, so a ``(tense, INVARIABLE_PERSON)``
# lookup only ever matches a personless row.
#
# ``inv`` is a poor name now that pt-PT drills two participle rows under it, but
# it is what the existing rows are keyed on and renaming it would need a data
# migration for no benefit.
INVARIABLE_PERSON = "inv"


class UnknownWord(LookupError):
    """The source has no entry for this word."""


class NotAVerb(LookupError):
    """The word exists but is not a verb.

    Only raised by sources that publish a part of speech. Reverso, for
    instance, answers 404 identically for a noun and for nonsense, so the
    Italian adapter can only ever raise ``UnknownWord``.
    """


class SourceUnavailable(RuntimeError):
    """The source could not be reached."""


@dataclass(frozen=True)
class Cell:
    """One drillable answer, which may legitimately have alternatives.

    ``forms[0]`` is what the drill displays and what ``Form.form_text`` holds;
    every member grades as correct. A cell with alternatives is not a defect in
    the data — ``oiço``/``ouço`` are both current European Portuguese — so the
    drill accepts them all and tells the learner about the ones they didn't use.
    """

    forms: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.forms:
            raise ValueError("a cell needs at least one form")

    @property
    def answer(self) -> str:
        return self.forms[0]

    @property
    def alternatives(self) -> tuple[str, ...]:
        return self.forms[1:]


@dataclass
class Paradigm:
    """A verb's full set of drillable cells, keyed by ``(tense, person)``."""

    infinitive: str
    cells: dict[tuple[str, str], Cell] = field(default_factory=dict)
    translation: str | None = None

    def cell(self, tense: str, person: str) -> Cell | None:
        return self.cells.get((tense, person))

    @property
    def form_count(self) -> int:
        return len(self.cells)

    @property
    def tenses_present(self) -> set[str]:
        return {tense for tense, _ in self.cells}


def resolve_tense_prefs(saved: list[dict], tenses: list[dict]) -> list[dict]:
    """Reconcile a (possibly stale) saved tense-preference list against ``tenses``.

    ``saved`` is ``[{"key", "enabled"}, …]`` in the user's chosen order. Unknown
    or duplicate keys are dropped; valid keys keep their order and ``enabled``
    flag; any canonical tense missing from ``saved`` is appended at the end as
    enabled — so newly-added tenses show up by default rather than vanishing for
    users who saved settings before the tense existed. An empty ``saved`` yields
    every tense enabled in canonical order (the default, no-settings behavior).

    Language-neutral: the catalogue is a parameter, so each adapter reconciles
    against its own tenses. Returns ``[{"key", "label", "mood", …, "enabled"}]``
    ready for the UI.
    """
    by_key = {t["key"]: t for t in tenses}
    resolved: list[dict] = []
    seen: set[str] = set()
    for item in saved:
        key = item.get("key")
        if key in by_key and key not in seen:
            seen.add(key)
            resolved.append({**by_key[key], "enabled": bool(item.get("enabled", True))})
    for tense in tenses:
        if tense["key"] not in seen:
            resolved.append({**tense, "enabled": True})
    return resolved


@runtime_checkable
class LanguageAdapter(Protocol):
    """One per language. Owns the tense catalogue and the paradigm source.

    Everything the drill needs to know about a language reaches it through
    here: which tenses exist and in what order, which persons are asked, how a
    row is labelled, and where paradigms come from.
    """

    code: str  # e.g. "pt-PT"

    @property
    def tenses(self) -> list[dict]:
        """Ordered tense catalogue.

        Each entry is ``{"key", "label", "mood", "label_pt", "mood_pt"}`` —
        English and native names for the same tense, which the UI's Interface
        setting picks between.
        """

    @property
    def tense_keys(self) -> list[str]:
        """Just the keys of ``tenses``, in the same order."""

    @property
    def drill_persons(self) -> list[str]:
        """Person keys to render, in row order.

        Not every stored person is drilled — pt-PT stores ``vós`` but never
        asks for it — so this is a subset of what a paradigm may hold.
        """

    @property
    def past_participle_tense(self) -> str | None:
        """Tense key of the past participle, or ``None`` if the language has none.

        Only needed to fill ``Verb.past_participle``; the drill itself treats
        participles as ordinary personless cells.
        """

    @property
    def present_participle_tense(self) -> str | None:
        """Tense key of the gerund/present participle, or ``None``."""

    def person_label(self, tense: str, person: str) -> str:
        """Row label for a cell, e.g. ``que eu``, ``não tu``, ``ter / haver``."""

    def resolve_tense_prefs(self, saved: list[dict]) -> list[dict]:
        """``resolve_tense_prefs(saved, self.tenses)``."""

    async def paradigm(self, infinitive: str) -> Paradigm:
        """Look the verb up.

        Raises ``UnknownWord``, ``NotAVerb`` or ``SourceUnavailable``.
        """
