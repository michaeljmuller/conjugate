"""Type-and-check grading: an exact match (case- and whitespace-insensitive) is
correct; anything else is wrong.

There is no automatic near-miss detection. A wrong attempt can be reclassified as
a typo by the user via the API (``verdict`` -> ``typo``) so later "hardest
conjugations" stats can separate real errors from slips.
"""

from __future__ import annotations

from dataclasses import dataclass


def _norm(text: str) -> str:
    """Trim + casefold, collapse internal whitespace."""
    return " ".join(text.strip().casefold().split())


@dataclass(frozen=True)
class Verdict:
    is_correct: bool
    verdict: str  # "correct" | "wrong"
    correct_answer: str


def grade(submitted: str, answer: str) -> Verdict:
    if _norm(submitted) == _norm(answer):
        return Verdict(True, "correct", answer)
    return Verdict(False, "wrong", answer)
