"""Claude writes and refines a new verb's example sentences.

~60 sentence pairs per verb: drafted, then checked both mechanically and by a
second model pass, then the flagged ones rewritten. That is all this module
does.

It deliberately does **not** check the conjugation. An earlier version did,
because the forms were scraped from a site with a real error rate. They now come
from cplp.org, which publishes the vocabulary the Acordo Ortográfico mandates
and which matched this project's hand-curated seed on 700 cells out of 700.
Against a normative source a model pass could only ever introduce errors, so the
verb's forms are taken as given.

Nothing here is language-specific. The shape of the request — one English
sentence per slot, a translation containing the exact form, then check and
rewrite what was flagged — is the same whichever language is being drilled;
what to tell the model *about* that language comes from
``adapter.prompt_material()``.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Callable

import anthropic
from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

from .languages.base import Paradigm, PromptMaterial

MODEL = "claude-opus-5"
MAX_TOKENS = 16000

# Rounds of "check, then rewrite what was flagged" after the initial draft.
MAX_REVISION_ROUNDS = 2

ProgressFn = Callable[..., None]


class ExamplesUnavailable(RuntimeError):
    """The example sentences could not be produced.

    Raised for a missing key, an API failure (auth, rate limit, exhausted
    credit, an outage) and for a run that finishes with slots still empty. The
    add-verb job treats any of these as fatal: a verb whose rows have no prompt
    is not worth saving, and a half-made one is harder to notice than an
    outright failure.
    """


def is_configured() -> bool:
    """Whether an API key is available."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _client() -> AsyncAnthropic:
    return AsyncAnthropic()


async def _parse(client: AsyncAnthropic, **kwargs):
    """One model call, with the SDK's failures turned into ``ExamplesUnavailable``.

    Catching the typed exceptions separately is what makes the difference
    between "Unexpected error: Error code: 400 …" and a message that says which
    thing to go and fix.
    """
    try:
        return await client.messages.parse(**kwargs)
    except anthropic.AuthenticationError:
        raise ExamplesUnavailable("ANTHROPIC_API_KEY was rejected.") from None
    except anthropic.PermissionDeniedError as exc:
        raise ExamplesUnavailable(f"The API key lacks access to {MODEL}: {exc}") from None
    except anthropic.RateLimitError:
        raise ExamplesUnavailable("Rate limited by the API. Try again shortly.") from None
    except anthropic.APIStatusError as exc:
        # Where an exhausted balance lands: a 400 whose message names it.
        detail = getattr(exc, "message", None) or str(exc)
        if "credit" in detail.lower() or "billing" in detail.lower():
            raise ExamplesUnavailable(f"The Anthropic account cannot be billed: {detail}") from None
        raise ExamplesUnavailable(f"The API returned {exc.status_code}: {detail}") from None
    except anthropic.APIConnectionError as exc:
        raise ExamplesUnavailable(f"Could not reach the API: {exc}") from None


# --- slots ----------------------------------------------------------------


@dataclass(frozen=True)
class Slot:
    """One drillable cell: the form an example sentence has to illustrate."""

    tense: str
    person: str
    form: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.tense, self.person)


def slots_for(paradigm: Paradigm, adapter) -> list[Slot]:
    """Every cell the drill will actually show, in display order.

    Mirrors ``api.verb_forms``: the adapter's drilled persons only (pt-PT
    stores ``vós`` but never asks for it). Generating examples for rows nobody
    sees would just burn tokens. Only the displayed form of a cell gets a
    sentence — the sentence has to contain the exact form, so an alternative
    would need its own.
    """
    out: list[Slot] = []
    for tense in adapter.tense_keys:
        for person in adapter.drill_persons:
            cell = paradigm.cell(tense, person)
            if cell:
                out.append(Slot(tense, person, cell.answer))
    return out


# --- example sentences ----------------------------------------------------


class ExamplePair(BaseModel):
    tense: str
    person: str
    example_en: str = Field(description="One natural everyday English sentence.")
    # The field name reaches the model as part of the output schema, so it says
    # "native" rather than naming one language. Which language is meant is
    # stated in the system prompt, and the DB column is still example_pt.
    example_native: str = Field(
        description="Faithful translation into the target language, containing the exact form."
    )


class ExampleDraft(BaseModel):
    translation: str = Field(description='Short English gloss of the verb, e.g. "to be".')
    examples: list[ExamplePair]


class SlotProblem(BaseModel):
    tense: str
    person: str
    reason: str = Field(description="One short clause on what is wrong.")


class ExampleCritique(BaseModel):
    problems: list[SlotProblem] = Field(
        description="Only pairs that need rewriting. Empty if all are good."
    )


def _draft_system(m: PromptMaterial) -> str:
    return f"""You write example sentences for a {m.name} conjugation drill.

For every slot you are given, write ONE natural everyday English sentence that
illustrates that exact verb form — it must reflect both the subject (person) and
the tense/aspect — plus a faithful {m.name} translation of that same
sentence which naturally contains the exact given form, spelled exactly as
given, accents and all.

The English sentence is the whole of the prompt the learner sees, so it has to
pin the tense down on its own. "I put the keys on the table" does not: it reads
just as easily as a present habit, and English "put" is spelled the same either
way — so the learner cannot tell which form is being asked for. Fix it with
whatever the sentence needs: "Yesterday I put the keys on the table" for the
past, "Whenever I get home I put the keys on the table" for the habit. A time
word, a subordinate clause, or an explicit contrast all work.

Before you settle on an English sentence, ask whether some other tense of the
same verb could translate it too. If it could, the sentence is not finished.

Keep both sentences short and concrete. Return one entry per slot, echoing the
slot's tense and person unchanged. Also give a short English gloss of the verb.

{m.variety_rule}
Style guide:
{m.guidance}"""


def _critique_system(m: PromptMaterial) -> str:
    return f"""You are reviewing example sentences for a {m.name} conjugation drill.

Each entry pairs a verb form with an English sentence and its {m.name}
translation. Report ONLY entries that need rewriting, and say briefly why.

Report an entry when:
- the translation does not contain the exact given form, or alters its spelling
  or accents;
- it is unnatural, or not how the sentence would actually be said;
- the sentence does not actually illustrate the given tense or aspect;
- the English would translate just as well into a different tense of the same
  verb, naming no time, habit or condition that rules the others out — the
  learner is being asked for a form the prompt does not identify ("I put the
  keys on the table" against "Yesterday I put the keys on the table");
- the subject does not match the given person;
- the English and the translation do not mean the same thing;
{m.critique_rules}

Be selective: an entry that is merely plain is fine, and an empty list is a
good answer.

{m.variety_rule}
Style guide:
{m.guidance}"""


def _slot_payload(slots: list[Slot]) -> list[dict]:
    return [{"tense": s.tense, "person": s.person, "form": s.form} for s in slots]


def contains_form(sentence: str, form: str) -> bool:
    """Does ``sentence`` contain ``form`` as a whole word?

    Case-insensitive (a form often opens the sentence, capitalised) but
    accent-sensitive — the accents *are* the answer being drilled. Lookarounds
    rather than ``\\b`` so accented letters at the edges behave.
    """
    if not sentence or not form:
        return False
    return re.search(
        rf"(?<!\w){re.escape(form)}(?!\w)", sentence, re.IGNORECASE | re.UNICODE
    ) is not None


def mechanical_problems(pairs: dict[tuple[str, str], ExamplePair], slots: list[Slot]) -> list[SlotProblem]:
    """Checks that don't need a model — and so can't be wrong about themselves.

    The load-bearing one is that the Portuguese sentence actually contains the
    form being drilled: the drill reveals that sentence as the answer's context,
    so a sentence missing the form is useless no matter how good it reads.
    """
    problems: list[SlotProblem] = []
    for slot in slots:
        pair = pairs.get(slot.key)
        if pair is None:
            problems.append(SlotProblem(tense=slot.tense, person=slot.person, reason="missing"))
            continue
        if not pair.example_en.strip() or not pair.example_native.strip():
            problems.append(SlotProblem(tense=slot.tense, person=slot.person, reason="empty sentence"))
        elif not contains_form(pair.example_native, slot.form):
            problems.append(
                SlotProblem(
                    tense=slot.tense,
                    person=slot.person,
                    reason=f'Portuguese sentence does not contain "{slot.form}"',
                )
            )
    return problems


@dataclass
class ExampleResult:
    translation: str = ""
    pairs: dict[tuple[str, str], ExamplePair] = field(default_factory=dict)
    # Slots still flagged when the revision budget ran out. Saved anyway — a
    # weak example beats a blank one — but reported so it's visible.
    unresolved: list[SlotProblem] = field(default_factory=list)
    rounds: int = 0


async def _draft(
    paradigm: Paradigm, slots: list[Slot], client: AsyncAnthropic, m: PromptMaterial
) -> ExampleDraft:
    response = await _parse(
        client,
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=_draft_system(m),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Verb: {paradigm.infinitive}\n\nSlots:\n"
                    + json.dumps(_slot_payload(slots), ensure_ascii=False, indent=2)
                ),
            }
        ],
        output_format=ExampleDraft,
    )
    return response.parsed_output or ExampleDraft(translation="", examples=[])


async def _critique(
    paradigm: Paradigm,
    slots: list[Slot],
    pairs: dict[tuple[str, str], ExamplePair],
    client: AsyncAnthropic,
    m: PromptMaterial,
) -> list[SlotProblem]:
    payload = [
        {
            "tense": s.tense,
            "person": s.person,
            "form": s.form,
            "example_en": pairs[s.key].example_en,
            "example_native": pairs[s.key].example_native,
        }
        for s in slots
        if s.key in pairs
    ]
    if not payload:
        return []
    response = await _parse(
        client,
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=_critique_system(m),
        messages=[
            {
                "role": "user",
                "content": f"Verb: {paradigm.infinitive}\n\nEntries:\n"
                + json.dumps(payload, ensure_ascii=False, indent=2),
            }
        ],
        output_format=ExampleCritique,
    )
    critique = response.parsed_output or ExampleCritique(problems=[])
    return critique.problems


async def _rewrite(
    paradigm: Paradigm,
    problems: list[SlotProblem],
    by_key: dict[tuple[str, str], Slot],
    pairs: dict[tuple[str, str], ExamplePair],
    client: AsyncAnthropic,
    m: PromptMaterial,
) -> ExampleDraft:
    """Re-draft only the flagged slots, with the criticism attached."""
    payload = []
    for p in problems:
        slot = by_key.get((p.tense, p.person))
        if slot is None:
            continue
        previous = pairs.get(slot.key)
        payload.append(
            {
                "tense": slot.tense,
                "person": slot.person,
                "form": slot.form,
                "problem": p.reason,
                "previous_en": previous.example_en if previous else "",
                "previous_native": previous.example_native if previous else "",
            }
        )
    response = await _parse(
        client,
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=_draft_system(m),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Verb: {paradigm.infinitive}\n\n"
                    "These example sentences were rejected. Write a fresh pair for each, "
                    "fixing the stated problem:\n"
                    + json.dumps(payload, ensure_ascii=False, indent=2)
                ),
            }
        ],
        output_format=ExampleDraft,
    )
    return response.parsed_output or ExampleDraft(translation="", examples=[])


async def generate_examples(
    paradigm: Paradigm,
    adapter,
    *,
    client: AsyncAnthropic | None = None,
    progress: ProgressFn | None = None,
    max_rounds: int = MAX_REVISION_ROUNDS,
) -> ExampleResult:
    """Draft example sentences, then check and rewrite until they hold up.

    Each round runs the mechanical checks and a fresh model critique, then
    rewrites only what was flagged. Slots still flagged when ``max_rounds`` is
    spent are returned in ``unresolved`` rather than dropped — a weak sentence
    is still a usable prompt.

    A *missing* one is not, so this raises ``ExamplesUnavailable`` if the run
    ends with any slot lacking a pair, as well as when the API itself fails.
    """
    # Only relevant when we're about to build a client; an injected one carries
    # its own credentials (or is a stub).
    if client is None and not is_configured():
        raise ExamplesUnavailable(
            "ANTHROPIC_API_KEY is not set, so example sentences cannot be written."
        )

    client = client or _client()
    material = adapter.prompt_material()
    slots = slots_for(paradigm, adapter)
    by_key = {s.key: s for s in slots}
    note = progress or (lambda *a, **k: None)

    note("drafting", done=0, total=len(slots))
    draft = await _draft(paradigm, slots, client, material)
    pairs = {(p.tense, p.person): p for p in draft.examples if (p.tense, p.person) in by_key}
    result = ExampleResult(translation=draft.translation.strip(), pairs=pairs)

    for round_no in range(max_rounds + 1):
        problems = mechanical_problems(pairs, slots)
        seen = {(p.tense, p.person) for p in problems}
        for p in await _critique(paradigm, slots, pairs, client, material):
            if (p.tense, p.person) in by_key and (p.tense, p.person) not in seen:
                problems.append(p)
                seen.add((p.tense, p.person))

        result.rounds = round_no
        note(
            "checked",
            round_no=round_no,
            ok=len(slots) - len(problems),
            flagged=len(problems),
            total=len(slots),
        )
        if not problems or round_no == max_rounds:
            result.unresolved = problems
            break

        note("revising", done=0, total=len(problems))
        redraft = await _rewrite(paradigm, problems, by_key, pairs, client, material)
        for p in redraft.examples:
            if (p.tense, p.person) in seen:
                pairs[(p.tense, p.person)] = p

    empty = [
        f"{s.tense}/{s.person}"
        for s in slots
        if s.key not in pairs
        or not pairs[s.key].example_en.strip()
        or not pairs[s.key].example_native.strip()
    ]
    if empty:
        raise ExamplesUnavailable(
            f"{len(empty)} form(s) ended up with no example sentence: "
            + ", ".join(empty[:8])
        )

    result.pairs = pairs
    return result


def example_slots(result: ExampleResult) -> list[dict]:
    """Flatten to the ``{tense, person, example_en, example_pt}`` rows that
    ``seed.apply_examples`` consumes."""
    return [
        {
            "tense": tense,
            "person": person,
            "example_en": pair.example_en.strip(),
            "example_pt": pair.example_native.strip(),
        }
        for (tense, person), pair in result.pairs.items()
    ]
