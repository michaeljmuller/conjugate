#!/usr/bin/env python3
"""Regenerate the ending table in `web/languages/regular.py` from the source.

The table says what a fully regular -ar/-er/-ir verb looks like, and is used to
decide whether a verb is predictable enough to warn about before adding it.
Rather than type the endings from memory, derive them: fetch cplp.org's own
`falar`, `comer` and `partir`, subtract the stem, and print what's left. The
endings then come from the same normative source as the verbs they will be
compared against, and the pt-PT selection rules (the `-ámos` preterite) are
already baked in by the adapter.

Usage (from src/python/web, in a container):
    python tools/regular_endings.py          # print the table
    python tools/regular_endings.py --check  # compare with what's committed

Exits non-zero under --check if the source has moved, so it can be a CI step.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.conjugation import PERSONS, TENSE_KEYS  # noqa: E402
from web.languages import get_adapter  # noqa: E402
from web.languages.regular import CONJUGATIONS, ENDINGS  # noqa: E402

# One entirely predictable verb per conjugation.
MODELS = dict(zip(CONJUGATIONS, ("falar", "comer", "partir")))

PAUSE = 1.5


def _order(key: tuple[str, str]) -> tuple[int, int]:
    """Sort as the drill does: by tense, then by person."""
    tense, person = key
    persons = [*PERSONS, "inv", "short"]
    return (TENSE_KEYS.index(tense), persons.index(person))


async def derive() -> dict[tuple[str, str], tuple[str, ...]]:
    adapter = get_adapter()
    table: dict[tuple[str, str], dict[str, str]] = {}
    for conjugation, verb in MODELS.items():
        paradigm = await adapter.paradigm(verb)
        stem = verb[: -len(conjugation)]
        for key, cell in paradigm.cells.items():
            if len(cell.forms) != 1:
                raise SystemExit(f"{verb} {key} has alternatives {cell.forms} — not a model verb")
            if not cell.answer.startswith(stem):
                raise SystemExit(f"{verb} {key} = {cell.answer!r} does not start with {stem!r}")
            table.setdefault(key, {})[conjugation] = cell.answer[len(stem) :]
        await asyncio.sleep(PAUSE)

    missing = [k for k, v in table.items() if len(v) != len(CONJUGATIONS)]
    if missing:
        raise SystemExit(f"cells present for only some conjugations: {sorted(missing)}")
    return {k: tuple(v[c] for c in CONJUGATIONS) for k, v in table.items()}


def render(table: dict[tuple[str, str], tuple[str, ...]]) -> str:
    lines = ["ENDINGS: dict[tuple[str, str], tuple[str, str, str]] = {"]
    for key in sorted(table, key=_order):
        tense, person = key
        forms = ", ".join(repr(f) for f in table[key])
        lines.append(f'    ("{tense}", "{person}"): ({forms}),')
    lines.append("}")
    return "\n".join(lines)


async def main() -> int:
    table = await derive()
    if "--check" not in sys.argv:
        print(render(table))
        return 0

    if table == ENDINGS:
        print(f"ok — {len(table)} endings match web/languages/regular.py")
        return 0
    for key in sorted(set(table) | set(ENDINGS), key=_order):
        if table.get(key) != ENDINGS.get(key):
            print(f"{key}: source={table.get(key)} committed={ENDINGS.get(key)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
