"""The model passes: the mechanical example checks, applying form corrections,
and the draft -> check -> rewrite loop.

No network: the loop is driven against a stub client that answers by the
requested output schema.
"""

import asyncio

import pytest

from web import llm
from web.languages.base import Cell, Paradigm
from web.llm import (
    ExampleCritique,
    ExampleDraft,
    ExamplePair,
    SlotProblem,
    contains_form,
    generate_examples,
    mechanical_problems,
    slots_for,
)

ENTRY = Paradigm(
    infinitive="correr",
    cells={
        ("present_indicative", "eu"): Cell(("corro",)),
        ("present_indicative", "tu"): Cell(("corres",)),
        ("present_indicative", "vos"): Cell(("correis",)),
        ("preterite", "eu"): Cell(("corri",)),
        ("past_participle", "inv"): Cell(("corrido",)),
        ("past_participle", "short"): Cell(("corrido",)),
        ("present_participle", "inv"): Cell(("correndo",)),
    },
)


# ---- contains_form -------------------------------------------------------

@pytest.mark.parametrize(
    "sentence,form,expected",
    [
        ("Corro pela minha saúde.", "corro", True),      # capitalised at sentence start
        ("Ele corre todos os dias.", "corre", True),
        ("Ele corres?", "corro", False),                 # different form
        ("Nós corremos ontem.", "corre", False),         # substring, not a whole word
        ("Corri 5 km.", "corrí", False),                 # accents are part of the answer
        ("", "corro", False),
    ],
)
def test_contains_form(sentence, form, expected):
    assert contains_form(sentence, form) is expected


# ---- slots ---------------------------------------------------------------

def test_slots_skip_vos_and_include_participles():
    slots = slots_for(ENTRY)
    keys = {(s.tense, s.person) for s in slots}

    assert ("present_indicative", "eu") in keys
    # vós is stored but never drilled, so it gets no example sentence.
    assert ("present_indicative", "vos") not in keys
    assert ("past_participle", "inv") in keys
    assert ("present_participle", "inv") in keys


# ---- mechanical checks ---------------------------------------------------

def test_mechanical_problems_flags_missing_form_and_gaps():
    slots = slots_for(ENTRY)
    pairs = {
        s.key: ExamplePair(
            tense=s.tense,
            person=s.person,
            example_en="I run.",
            # Deliberately wrong for the preterite: the sentence omits "corri".
            example_pt="Corro pela saúde." if s.tense != "preterite" else "Fui ao parque.",
        )
        for s in slots
        if s.tense != "past_participle"  # leave one slot missing entirely
    }
    problems = {(p.tense, p.person): p.reason for p in mechanical_problems(pairs, slots)}

    assert ("preterite", "eu") in problems
    assert "corri" in problems[("preterite", "eu")]
    assert problems[("past_participle", "inv")] == "missing"
    assert ("present_indicative", "eu") not in problems


# ---- the draft / check / rewrite loop ------------------------------------

class _StubClient:
    """Answers by requested schema, recording what it was asked to rewrite."""

    def __init__(self, *, bad_slots, critique_rounds=0):
        self.bad_slots = set(bad_slots)
        self.critique_rounds = critique_rounds
        self.rewrite_requests: list[list[tuple[str, str]]] = []
        self.calls = {"draft": 0, "critique": 0}
        self.messages = self

    async def parse(self, **kw):
        fmt = kw["output_format"]
        content = kw["messages"][0]["content"]
        if fmt is ExampleCritique:
            self.calls["critique"] += 1
            problems = []
            if self.calls["critique"] <= self.critique_rounds:
                problems = [SlotProblem(tense="preterite", person="eu", reason="bland")]
            return _Parsed(ExampleCritique(problems=problems))

        rewriting = "rejected" in content
        if rewriting:
            # Record which slots were asked for, then answer them all correctly.
            import json as _json

            payload = _json.loads(content[content.index("[") :])
            self.rewrite_requests.append([(p["tense"], p["person"]) for p in payload])
            return _Parsed(
                ExampleDraft(
                    translation="",
                    examples=[
                        ExamplePair(
                            tense=p["tense"], person=p["person"],
                            example_en="Fixed.", example_pt=f"Frase com {p['form']}.",
                        )
                        for p in payload
                    ],
                )
            )

        self.calls["draft"] += 1
        return _Parsed(
            ExampleDraft(
                translation="to run",
                examples=[
                    ExamplePair(
                        tense=s.tense, person=s.person, example_en="I run.",
                        # Bad slots get a sentence that omits the form.
                        example_pt=("Nada aqui."
                                    if (s.tense, s.person) in self.bad_slots
                                    else f"Frase com {s.form}."),
                    )
                    for s in slots_for(ENTRY)
                ],
            )
        )


class _Parsed:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output


def test_loop_rewrites_only_flagged_slots_and_then_stops():
    client = _StubClient(bad_slots=[("preterite", "eu")])
    result = asyncio.run(generate_examples(ENTRY, client=client, max_rounds=2))

    # Exactly the failing slot was re-requested, and only once.
    assert client.rewrite_requests == [[("preterite", "eu")]]
    assert result.unresolved == []
    assert result.translation == "to run"
    # The rewrite replaced the bad pair; the good ones were left alone.
    assert "corri" in result.pairs[("preterite", "eu")].example_pt
    assert result.pairs[("present_indicative", "eu")].example_en == "I run."


def test_loop_gives_up_after_max_rounds_and_reports_what_is_left():
    """A slot the model keeps flagging is saved anyway, but surfaced."""
    client = _StubClient(bad_slots=[], critique_rounds=99)
    result = asyncio.run(generate_examples(ENTRY, client=client, max_rounds=2))

    assert len(client.rewrite_requests) == 2  # capped, not looping forever
    assert [(p.tense, p.person) for p in result.unresolved] == [("preterite", "eu")]
    assert result.rounds == 2
    # Nothing was dropped just because it stayed flagged.
    assert len(result.pairs) == len(slots_for(ENTRY))


def test_example_slots_flattens_for_the_seeder():
    client = _StubClient(bad_slots=[])
    result = asyncio.run(generate_examples(ENTRY, client=client, max_rounds=1))
    rows = llm.example_slots(result)

    assert len(rows) == len(slots_for(ENTRY))
    assert {"tense", "person", "example_en", "example_pt"} == set(rows[0])
