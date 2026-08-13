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

The prompt guidance is not duplicated here — it is read from ``data/examples.json``,
the same tuned ``_instructions``/``_guidance`` block that produced the existing
catalogue, so verbs added through the app sound like the ones already there.
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

from .conjugation import DRILL_PERSONS, TENSE_KEYS
from .languages.base import Paradigm
from .seed import EXAMPLES_FILE

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


# --- prompt material -----------------------------------------------------

_guidance_cache: str | None = None


def prompt_guidance() -> str:
    """The pt-PT style guide from ``examples.json``, as a JSON string.

    Carries the variety rules, the person glosses, the subjunctive prefixes, a
    usage note for each tense, and worked style examples.
    """
    global _guidance_cache
    if _guidance_cache is None:
        data = json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))
        _guidance_cache = json.dumps(
            {"instructions": data.get("_instructions", ""), "guidance": data.get("_guidance", {})},
            ensure_ascii=False,
            indent=2,
        )
    return _guidance_cache


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


def slots_for(paradigm: Paradigm) -> list[Slot]:
    """Every cell the drill will actually show, in display order.

    Mirrors ``api.verb_forms``: drilled persons only (``vós`` is stored but
    never asked). Generating examples for rows nobody sees would just burn
    tokens. Only the displayed form of a cell gets a sentence — the sentence has
    to contain the exact form, so an alternative would need its own.
    """
    out: list[Slot] = []
    for tense in TENSE_KEYS:
        for person in DRILL_PERSONS:
            cell = paradigm.cell(tense, person)
            if cell:
                out.append(Slot(tense, person, cell.answer))
    return out


# --- example sentences ----------------------------------------------------


class ExamplePair(BaseModel):
    tense: str
    person: str
    example_en: str = Field(description="One natural everyday English sentence.")
    example_pt: str = Field(
        description="Faithful European-Portuguese translation, containing the exact form."
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


# Stated up front in both prompts rather than left to the appended style guide:
# the drill is specifically for the European variety, and pt-BR phrasing is the
# failure mode a model drifts into by default. The full contrast lists live in
# examples.json's _guidance.variety, which is appended after this.
_PT_PT_RULE = """LANGUAGE VARIETY — the one rule that matters most:

Write EUROPEAN Portuguese (Portugal). Not Brazilian. This is not a stylistic
preference: the learner is studying pt-PT, and a pt-BR sentence teaches them the
wrong thing even though it is perfectly good Portuguese elsewhere.

That covers grammar, vocabulary AND spelling:
- Grammar: "estou a correr", never "estou correndo". Object pronouns after the
  verb with a hyphen — "chamo-me", "dá-me o livro" — not "me chamo", "me dá"
  (they move before the verb after a negative, a question word or a
  subordinating conjunction: "não me dês"). Address one person as "tu" with real
  2nd-person endings, never "você" with a 3rd-person verb. Use "nós", not
  "a gente".
- Vocabulary: the Portuguese word wherever the varieties differ — comboio not
  trem, autocarro not ônibus, telemóvel not celular, casa de banho not banheiro,
  pequeno-almoço not café da manhã, sumo not suco, gelado not sorvete.
- Spelling: acute before a nasal — académico, género, António, not acadêmico,
  gênero, Antônio. And "falámos", not "falamos".
"""

_DRAFT_SYSTEM = f"""You write example sentences for a European-Portuguese conjugation drill.

For every slot you are given, write ONE natural everyday English sentence that
illustrates that exact verb form — it must reflect both the subject (person) and
the tense/aspect — plus a faithful European-Portuguese translation of that same
sentence which naturally contains the exact given form, spelled exactly as
given, accents and all.

Keep both sentences short and concrete. Return one entry per slot, echoing the
slot's tense and person unchanged. Also give a short English gloss of the verb.

{_PT_PT_RULE}
Style guide:
"""

_CRITIQUE_SYSTEM = f"""You are reviewing example sentences for a European-Portuguese conjugation drill.

Each entry pairs a verb form with an English sentence and its Portuguese
translation. Report ONLY entries that need rewriting, and say briefly why.

Report an entry when:
- the Portuguese does not contain the exact given form, or alters its spelling
  or accents;
- ANY part of the Portuguese is Brazilian rather than European — a pt-BR
  construction ("estou correndo", "me chamo", "você fala", "a gente vai"), a
  pt-BR word (trem, ônibus, celular, banheiro, suco, sorvete, café da manhã), or
  a pt-BR spelling (acadêmico, gênero, falamos for falámos);
- the Portuguese is unnatural or not how it would actually be said in Portugal;
- the sentence does not actually illustrate the given tense or aspect;
- the subject does not match the given person;
- the English and the Portuguese do not mean the same thing;
- a subjunctive lacks the trigger that licenses it.

Do NOT report a correct pt-PT form for looking unlike its Brazilian equivalent —
that is the point. Be selective otherwise: an entry that is merely plain is
fine, and an empty list is a good answer.

{_PT_PT_RULE}
Style guide:
"""


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
        if not pair.example_en.strip() or not pair.example_pt.strip():
            problems.append(SlotProblem(tense=slot.tense, person=slot.person, reason="empty sentence"))
        elif not contains_form(pair.example_pt, slot.form):
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
    paradigm: Paradigm, slots: list[Slot], client: AsyncAnthropic
) -> ExampleDraft:
    response = await _parse(
        client,
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=_DRAFT_SYSTEM + prompt_guidance(),
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
) -> list[SlotProblem]:
    payload = [
        {
            "tense": s.tense,
            "person": s.person,
            "form": s.form,
            "example_en": pairs[s.key].example_en,
            "example_pt": pairs[s.key].example_pt,
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
        system=_CRITIQUE_SYSTEM + prompt_guidance(),
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
                "previous_pt": previous.example_pt if previous else "",
            }
        )
    response = await _parse(
        client,
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=_DRAFT_SYSTEM + prompt_guidance(),
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
    slots = slots_for(paradigm)
    by_key = {s.key: s for s in slots}
    note = progress or (lambda *a, **k: None)

    note("drafting", done=0, total=len(slots))
    draft = await _draft(paradigm, slots, client)
    pairs = {(p.tense, p.person): p for p in draft.examples if (p.tense, p.person) in by_key}
    result = ExampleResult(translation=draft.translation.strip(), pairs=pairs)

    for round_no in range(max_rounds + 1):
        problems = mechanical_problems(pairs, slots)
        seen = {(p.tense, p.person) for p in problems}
        for p in await _critique(paradigm, slots, pairs, client):
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
        redraft = await _rewrite(paradigm, problems, by_key, pairs, client)
        for p in redraft.examples:
            if (p.tense, p.person) in seen:
                pairs[(p.tense, p.person)] = p

    empty = [
        f"{s.tense}/{s.person}"
        for s in slots
        if s.key not in pairs
        or not pairs[s.key].example_en.strip()
        or not pairs[s.key].example_pt.strip()
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
            "example_pt": pair.example_pt.strip(),
        }
        for (tense, person), pair in result.pairs.items()
    ]
