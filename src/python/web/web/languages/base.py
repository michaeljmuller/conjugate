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


class UnknownWord(LookupError):
    """The source has no entry for this word."""


class NotAVerb(LookupError):
    """The word exists but is not a verb."""


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


@runtime_checkable
class LanguageAdapter(Protocol):
    """One per language. Owns the tense catalogue and the paradigm source."""

    code: str  # e.g. "pt-PT"

    @property
    def tenses(self) -> list[dict]:
        """Ordered tense catalogue, as ``conjugation.TENSES`` shapes it."""

    @property
    def drill_persons(self) -> list[str]:
        """Person keys to render, in row order."""

    def person_label(self, tense: str, person: str) -> str:
        """Row label for a cell, e.g. ``que eu``, ``não tu``, ``ter / haver``."""

    async def paradigm(self, infinitive: str) -> Paradigm:
        """Look the verb up.

        Raises ``UnknownWord``, ``NotAVerb`` or ``SourceUnavailable``.
        """
