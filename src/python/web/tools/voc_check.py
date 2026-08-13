#!/usr/bin/env python3
"""Check the seeded verbs against cplp.org — the regression gate for the source.

`verbs_seed.json` was curated by hand and verified form by form; cplp.org
publishes the vocabulary the Acordo Ortográfico mandates. Neither is derived
from the other, so agreement between them is real evidence, and this script is
what proves the parser and the pt-PT selection rules still produce it.

Measured 2026-08-13: 700 of 700 cells agree.

Usage (from src/python/web, in a container):
    python tools/voc_check.py                # every seeded verb
    python tools/voc_check.py partir pôr     # named verbs
    python tools/voc_check.py --dump pôr     # print the parsed paradigm

Exits non-zero on a mismatch, so it can be a CI step. It sleeps between verbs;
this is somebody's public reference, not an API.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.conjugation import (  # noqa: E402
    INVARIABLE_PERSON,
    PAST_PARTICIPLE_TENSE,
    PRESENT_PARTICIPLE_TENSE,
)
from web.languages import get_adapter  # noqa: E402
from web.seed import SEED_FILE  # noqa: E402

PAUSE = 1.5


async def check(entry: dict) -> tuple[int, list[str]]:
    """``(cells checked, problems)`` for one seeded verb."""
    paradigm = await get_adapter().paradigm(entry["infinitive"])
    checked = 0
    problems: list[str] = []

    wanted = [(t, p, w) for t, ps in entry["forms"].items() for p, w in ps.items()]
    wanted += [
        (PAST_PARTICIPLE_TENSE, INVARIABLE_PERSON, entry.get("past_participle")),
        (PRESENT_PARTICIPLE_TENSE, INVARIABLE_PERSON, entry.get("present_participle")),
    ]

    for tense, person, want in wanted:
        if not want:
            continue
        checked += 1
        cell = paradigm.cell(tense, person)
        if cell is None:
            problems.append(f"  {tense}.{person}: ours={want!r} cplp=(absent)")
        elif want == cell.answer:
            continue
        elif want in cell.forms:
            # Both are valid; we display a different one. Worth seeing, not a failure.
            problems.append(f"  {tense}.{person}: variant — cplp also lists {cell.forms}")
        else:
            problems.append(
                f"  {tense}.{person}: ours={want!r} cplp={cell.forms}  <-- MISMATCH"
            )
    return checked, problems


async def main(argv: list[str]) -> int:
    if "--dump" in argv:
        adapter = get_adapter()
        for verb in [a for a in argv if a != "--dump"]:
            paradigm = await adapter.paradigm(verb)
            print(f"== {verb}")
            for (tense, person), cell in sorted(paradigm.cells.items()):
                print(f"   {tense:28s} {person:6s} {list(cell.forms)}")
        return 0

    seed = {v["infinitive"]: v for v in json.loads(SEED_FILE.read_text(encoding="utf-8"))}
    names = argv or list(seed)
    mismatches = 0

    for name in names:
        entry = seed.get(name)
        if entry is None:
            print(f"{name}: not in verbs_seed.json — use --dump to see cplp.org's paradigm")
            continue
        checked, problems = await check(entry)
        bad = sum(1 for p in problems if "MISMATCH" in p or "absent" in p)
        mismatches += bad
        print(f"{name:9s} {checked - len(problems)}/{checked} exact" + (f"  ({bad} mismatch)" if bad else ""))
        for problem in problems:
            print(problem)
        await asyncio.sleep(PAUSE)

    print(f"\ntotal mismatches against cplp.org: {mismatches}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
