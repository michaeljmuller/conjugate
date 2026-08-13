"""Type-and-check grading: an exact match (case- and whitespace-insensitive) is
correct; anything else is wrong.

Accents are part of the answer — ``corri`` and ``corrí`` are different, and a
missing diacritic is wrong, because the accent is what the drill is teaching.

A cell may have more than one correct form. Portuguese offers genuine
alternatives in places (``oiço``/``ouço``; the regular and short past
participles), so grading takes every accepted form and any of them counts. The
drill displays one and tells the learner afterwards which others it would have
taken.

There is no automatic near-miss detection. A wrong attempt can be reclassified as
a typo by the user via the API (``verdict`` -> ``typo``) so later "hardest
conjugations" stats can separate real errors from slips.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


def _norm(text: str) -> str:
    """Trim + casefold, collapse internal whitespace."""
    return " ".join(text.strip().casefold().split())


@dataclass(frozen=True)
class Verdict:
    is_correct: bool
    verdict: str  # "correct" | "wrong"
    correct_answer: str  # the displayed form, whichever variant was typed
    matched: str | None = None  # the accepted form the answer matched, if any


def grade(submitted: str, answer: str, variants: Iterable[str] = ()) -> Verdict:
    """Grade ``submitted`` against the displayed ``answer`` and its ``variants``."""
    typed = _norm(submitted)
    for candidate in (answer, *variants):
        if typed == _norm(candidate):
            return Verdict(True, "correct", answer, candidate)
    return Verdict(False, "wrong", answer)
