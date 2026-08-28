"""The model passes: the mechanical example checks, applying form corrections,
and the draft -> check -> rewrite loop.

No network: the loop is driven against a stub client that answers by the
requested output schema.
"""

import asyncio

import pytest

import json

from web import llm
from web.languages import get_adapter, languages
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

# ENTRY is a pt-PT paradigm, so the real pt adapter is what orders its slots.
ADAPTER = get_adapter()


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
    slots = slots_for(ENTRY, ADAPTER)
    keys = {(s.tense, s.person) for s in slots}

    assert ("present_indicative", "eu") in keys
    # vós is stored but never drilled, so it gets no example sentence.
    assert ("present_indicative", "vos") not in keys
    assert ("past_participle", "inv") in keys
    assert ("present_participle", "inv") in keys


# ---- mechanical checks ---------------------------------------------------

def test_mechanical_problems_flags_missing_form_and_gaps():
    slots = slots_for(ENTRY, ADAPTER)
    pairs = {
        s.key: ExamplePair(
            tense=s.tense,
            person=s.person,
            example_en="I run.",
            # Deliberately wrong for the preterite: the sentence omits "corri".
            example_native="Corro pela saúde." if s.tense != "preterite" else "Fui ao parque.",
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
                            example_en="Fixed.", example_native=f"Frase com {p['form']}.",
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
                        example_native=("Nada aqui."
                                    if (s.tense, s.person) in self.bad_slots
                                    else f"Frase com {s.form}."),
                    )
                    for s in slots_for(ENTRY, ADAPTER)
                ],
            )
        )


class _Parsed:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output


def test_loop_rewrites_only_flagged_slots_and_then_stops():
    client = _StubClient(bad_slots=[("preterite", "eu")])
    result = asyncio.run(generate_examples(ENTRY, ADAPTER, client=client, max_rounds=2))

    # Exactly the failing slot was re-requested, and only once.
    assert client.rewrite_requests == [[("preterite", "eu")]]
    assert result.unresolved == []
    assert result.translation == "to run"
    # The rewrite replaced the bad pair; the good ones were left alone.
    assert "corri" in result.pairs[("preterite", "eu")].example_native
    assert result.pairs[("present_indicative", "eu")].example_en == "I run."


def test_loop_gives_up_after_max_rounds_and_reports_what_is_left():
    """A slot the model keeps flagging is saved anyway, but surfaced."""
    client = _StubClient(bad_slots=[], critique_rounds=99)
    result = asyncio.run(generate_examples(ENTRY, ADAPTER, client=client, max_rounds=2))

    assert len(client.rewrite_requests) == 2  # capped, not looping forever
    assert [(p.tense, p.person) for p in result.unresolved] == [("preterite", "eu")]
    assert result.rounds == 2
    # Nothing was dropped just because it stayed flagged.
    assert len(result.pairs) == len(slots_for(ENTRY, ADAPTER))


def test_example_slots_flattens_for_the_seeder():
    client = _StubClient(bad_slots=[])
    result = asyncio.run(generate_examples(ENTRY, ADAPTER, client=client, max_rounds=1))
    rows = llm.example_slots(result)

    assert len(rows) == len(slots_for(ENTRY, ADAPTER))
    assert {"tense", "person", "example_en", "example_pt"} == set(rows[0])


# ---- every language's prompt material ------------------------------------
#
# The loop below is the only thing that executes an adapter's prompt material
# outside a real add-a-verb run: generate_examples is stubbed everywhere else,
# so without this a malformed guidance file would sit green in CI and only fail
# when someone actually added a verb -- after the lookup, and after paying for
# it in wall-clock time.

@pytest.mark.parametrize("code", languages())
def test_every_language_can_build_its_prompts(code):
    m = get_adapter(code).prompt_material()

    assert m.name, code
    assert m.variety_rule.strip(), code
    assert m.guidance.strip(), code

    # The guidance ships as a JSON file; a syntax error in it raises here.
    parsed = json.loads(m.guidance)
    assert parsed["instructions"].strip(), code
    guidance = parsed["guidance"]
    assert guidance.get("persons"), code
    assert guidance.get("tense_usage"), code
    assert guidance.get("style_examples"), code


@pytest.mark.parametrize("code", languages())
def test_every_language_composes_both_system_prompts(code):
    adapter = get_adapter(code)
    m = adapter.prompt_material()

    for prompt in (llm._draft_system(m), llm._critique_system(m)):
        assert m.name in prompt, code
        assert m.variety_rule.strip() in prompt, code
        assert m.guidance in prompt, code
        # Nothing left unfilled by the f-string.
        assert "{" not in prompt.replace(m.guidance, ""), code

    # The critique's extra grounds are appended to the shared list, not lost.
    assert m.critique_rules.strip() in llm._critique_system(m), code


@pytest.mark.parametrize("code", languages())
def test_a_languages_guidance_covers_every_tense_it_drills(code):
    """A tense with no usage note is a tense the model has to guess at."""
    adapter = get_adapter(code)
    notes = json.loads(adapter.prompt_material().guidance)["guidance"]["tense_usage"]
    assert set(adapter.tense_keys) == set(notes), code


@pytest.mark.parametrize("code", languages())
def test_a_languages_guidance_glosses_every_person_it_drills(code):
    adapter = get_adapter(code)
    persons = json.loads(adapter.prompt_material().guidance)["guidance"]["persons"]
    missing = set(adapter.drill_persons) - set(persons)
    assert not missing, f"{code}: no gloss for {sorted(missing)}"


# ---- revise_examples -----------------------------------------------------

class _ReviseStub:
    """Answers a revision, recording the reasons it was asked to fix.

    ``critique_finds`` are the slots a batch comment is told to apply to;
    ``breaks`` are slots whose rewrite comes back without the drilled form, to
    exercise the corrective pass.
    """

    def __init__(self, *, critique_finds=(), breaks=(), echo_unchanged=()):
        self.critique_finds = list(critique_finds)
        self.breaks = set(breaks)
        self.echo_unchanged = set(echo_unchanged)
        self.rewrite_requests: list[list[dict]] = []
        self.critique_systems: list[str] = []
        self.calls = {"critique": 0, "rewrite": 0}
        self.messages = self

    async def parse(self, **kw):
        content = kw["messages"][0]["content"]
        if kw["output_format"] is ExampleCritique:
            self.calls["critique"] += 1
            self.critique_systems.append(kw["system"])
            return _Parsed(ExampleCritique(problems=[
                SlotProblem(tense=t, person=p, reason="fails the batch test")
                for t, p in self.critique_finds
            ]))

        self.calls["rewrite"] += 1
        payload = json.loads(content[content.index("[") :])
        self.rewrite_requests.append(payload)
        out = []
        for entry in payload:
            key = (entry["tense"], entry["person"])
            if key in self.echo_unchanged:
                native, english = entry["previous_native"], entry["previous_en"]
            elif key in self.breaks and self.calls["rewrite"] == 1:
                native, english = "Sem a forma.", "Broken."   # form is missing
            else:
                native, english = f"Ontem, frase com {entry['form']}.", "Yesterday, fixed."
            out.append(ExamplePair(
                tense=entry["tense"], person=entry["person"],
                example_en=english, example_native=native,
            ))
        return _Parsed(ExampleDraft(translation="", examples=out))


def _current(*keys):
    """Existing sentences for the given slots, keyed as revise_examples wants."""
    by_key = {s.key: s for s in slots_for(ENTRY, ADAPTER)}
    return {
        k: ExamplePair(tense=k[0], person=k[1], example_en="I run.",
                       example_native=f"Frase com {by_key[k].form}.")
        for k in keys
    }


def test_comment_on_one_slot_costs_no_critique_call():
    """A comment names its own slot, so there is nothing to identify."""
    key = ("preterite", "eu")
    stub = _ReviseStub()
    result = asyncio.run(llm.revise_examples(
        ENTRY, ADAPTER, current=_current(key),
        comments={key: "this could be present or past; add 'yesterday'"},
        client=stub,
    ))

    assert stub.calls == {"critique": 0, "rewrite": 1}
    # The comment reaches the rewrite verbatim as the problem to fix.
    assert stub.rewrite_requests[0][0]["problem"].startswith("this could be present")
    assert [(p.tense, p.person) for p in result.proposals] == [key]
    assert result.proposals[0].before_native == "Frase com corri."
    assert result.proposals[0].after_native == "Ontem, frase com corri."


def test_batch_comment_identifies_then_rewrites_in_two_calls():
    """One call to find the slots, one to fix them all together — not one each."""
    finds = [("preterite", "eu"), ("present_indicative", "tu")]
    stub = _ReviseStub(critique_finds=finds)
    result = asyncio.run(llm.revise_examples(
        ENTRY, ADAPTER, current=_current(*finds),
        batch_comment="ensure every sentence only fits the tense it illustrates",
        client=stub,
    ))

    assert stub.calls == {"critique": 1, "rewrite": 1}
    assert len(stub.rewrite_requests[0]) == 2          # both slots, one call
    assert {(p.tense, p.person) for p in result.proposals} == set(finds)
    # The batch comment is put to the model as its own ground for rejection.
    assert "only fits the tense it illustrates" in stub.critique_systems[0]


def test_a_slot_comment_overrides_the_batch_critique():
    """The reader's own words win: they are more specific than the model's."""
    key = ("preterite", "eu")
    stub = _ReviseStub(critique_finds=[key])
    asyncio.run(llm.revise_examples(
        ENTRY, ADAPTER, current=_current(key),
        comments={key: "use a different subject"},
        batch_comment="check the tenses",
        client=stub,
    ))

    asked = stub.rewrite_requests[0]
    assert len(asked) == 1                              # not queued twice
    assert asked[0]["problem"] == "use a different subject"


def test_a_rewrite_that_drops_the_form_gets_one_more_try():
    """A sentence without the drilled form is unusable however well it reads."""
    key = ("preterite", "eu")
    stub = _ReviseStub(breaks=[key])
    result = asyncio.run(llm.revise_examples(
        ENTRY, ADAPTER, current=_current(key), comments={key: "fix it"}, client=stub,
    ))

    assert stub.calls["rewrite"] == 2                   # the corrective pass ran
    assert result.proposals[0].after_native == "Ontem, frase com corri."
    assert result.unresolved == []


def test_an_unchanged_rewrite_is_not_offered_as_a_change():
    """Nothing to accept, so it is reported instead of wasting a click."""
    key = ("preterite", "eu")
    stub = _ReviseStub(echo_unchanged=[key])
    result = asyncio.run(llm.revise_examples(
        ENTRY, ADAPTER, current=_current(key), comments={key: "fix it"}, client=stub,
    ))

    assert result.proposals == []
    assert [p.tense for p in result.unresolved] == ["preterite"]


def test_nothing_to_do_makes_no_rewrite_call():
    """A batch comment the critique finds nothing for stops there."""
    stub = _ReviseStub(critique_finds=[])
    result = asyncio.run(llm.revise_examples(
        ENTRY, ADAPTER, current=_current(("preterite", "eu")),
        batch_comment="check the tenses", client=stub,
    ))

    assert stub.calls == {"critique": 1, "rewrite": 0}
    assert result.proposals == []
