"""What Claude needs to know to write Italian example sentences.

``llm.py`` owns the shape of the request and the draft → check → rewrite loop.
This is the part only Italian can supply.

Portuguese's one rule that matters most is not drifting into Brazilian. Italian
has no comparable split, so the slot is spent on what a model actually gets
wrong here: reaching for the *passato prossimo* when the drilled tense is the
*passato remoto*, writing the polite imperative rows as if they addressed a
third person, and producing a subjunctive with no trigger in sight.

Unlike ``pt``, the guidance lives in its own file rather than doubling as a
by-hand example catalogue — there is no seeded Italian catalogue for it to
double as.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..base import PromptMaterial
from .catalogue import NAME

GUIDANCE_FILE = Path(__file__).parent / "guidance.json"

VARIETY_RULE = """WHAT MATTERS MOST HERE:

Write standard modern Italian as used in Italy, and make each sentence actually
demonstrate the tense it is drilling. The three ways this goes wrong:

- TENSE SUBSTITUTION. The form you are given is the answer the learner has to
  produce, so the sentence has to be one where THAT form is what a speaker would
  really use. The trap is the passato remoto: do not write a sentence that any
  Italian would say with the passato prossimo instead. Make it narration —
  "Dante nacque a Firenze", "Il re parlò alla folla" — not recent news.
- THE POLITE IMPERATIVE. The imperative's 3rd-person rows (Lei, Loro) are the
  POLITE forms, addressed to the person you are speaking to, not to someone
  else. "Parli più lentamente" means "Speak more slowly" to a stranger, NOT
  "he speaks". Write those as polite requests.
- A SUBJUNCTIVE WITH NO TRIGGER. The congiuntivo needs the clause that licenses
  it, in the sentence: "Penso che tu parli bene", not a bare "tu parli bene".

Also: Italian normally drops the subject pronoun. Write "Parlo italiano", not
"Io parlo italiano", unless the pronoun is needed for contrast or to tell apart
persons that share a form — which the imperfetto and the congiuntivo often do.
"""

CRITIQUE_RULES = """- the sentence would really be said with a different tense — above all a
  passato remoto that any speaker would render as a passato prossimo;
- an imperative Lei/Loro row is written as a statement about someone else
  instead of a polite request to the person addressed;
- a congiuntivo appears without the main clause that licenses it;
- a subject pronoun is present where Italian would drop it, or absent where the
  sentence is ambiguous without it;
- the Italian is regional or dialectal rather than standard."""

_guidance_cache: str | None = None


def guidance() -> str:
    """The Italian style guide, as a JSON string.

    Carries the register rules, the person glosses, the subjunctive cues, a
    usage note for each tense, and worked style examples.
    """
    global _guidance_cache
    if _guidance_cache is None:
        data = json.loads(GUIDANCE_FILE.read_text(encoding="utf-8"))
        _guidance_cache = json.dumps(
            {
                "instructions": data.get("_instructions", ""),
                "guidance": data.get("_guidance", {}),
            },
            ensure_ascii=False,
            indent=2,
        )
    return _guidance_cache


def prompt_material() -> PromptMaterial:
    return PromptMaterial(
        name=NAME,
        variety_rule=VARIETY_RULE,
        critique_rules=CRITIQUE_RULES,
        guidance=guidance(),
    )
