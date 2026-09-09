"""What Claude needs to know to write Spanish example sentences.

``llm.py`` owns the shape of the request and the draft → check → rewrite loop.
This is the part only Spanish can supply.

Portuguese's one rule that matters most is not drifting into Brazilian. Spanish
has a comparable split and one deliberate straddle: the vocabulary is
pan-Hispanic and neutral, but the vosotros rows are peninsular by definition, so
a model asked for a vosotros sentence must write one rather than quietly
rewriting it with ustedes. Beyond that the slot goes to what a model actually
gets wrong here: ser against estar, a subjunctive with nothing to license it,
and the imperative's polite rows read as statements about someone else.

Like ``it``, the guidance lives in its own file rather than doubling as a
by-hand example catalogue — there is no seeded Spanish catalogue for it to
double as.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..base import PromptMaterial
from .catalogue import NAME

GUIDANCE_FILE = Path(__file__).parent / "guidance.json"

VARIETY_RULE = """WHAT MATTERS MOST HERE:

Write standard modern Spanish, and make each sentence actually demonstrate the
tense it is drilling. The four ways this goes wrong:

- VOSOTROS REWRITTEN AS USTEDES. The vosotros rows are the informal plural used
  in Spain, and they are what the learner has to produce. When the given form is
  a vosotros form, write a sentence that really uses it — "¿Habláis español?" —
  and never substitute "ustedes hablan". Every other row should use neutral,
  pan-Hispanic vocabulary that a reader in Mexico or Madrid would both accept.
- SER AGAINST ESTAR. Both are "to be" and the choice is not free. Use ser for
  identity, origin, and inherent qualities; estar for location, condition, and
  the result of a change. If the drilled verb is one of them, the sentence has
  to be one where THAT verb is the right one.
- A SUBJUNCTIVE WITH NO TRIGGER. The subjunctive needs the clause that licenses
  it, in the sentence: "Espero que hables con ella", not a bare "hables con
  ella". For the imperfect subjunctive that is usually "si ..." or a main clause
  in the past or conditional.
- THE POLITE IMPERATIVE. The imperative's Ud. and Uds. rows are the POLITE
  forms, addressed to the person you are speaking to, not to someone else.
  "Hable más despacio" means "Speak more slowly" to a stranger, NOT "he speaks".
  Write those as polite requests.

Also: Spanish normally drops the subject pronoun. Write "Hablo español", not
"Yo hablo español", unless the pronoun is needed for contrast or to tell apart
persons that share a form — which the imperfect, the conditional and both
subjunctives often do, where yo and él/ella are identical.
"""

CRITIQUE_RULES = """- a vosotros form is glossed or rendered as ustedes, or the sentence is written
  so that ustedes would be the natural choice;
- the sentence uses ser where estar is right, or estar where ser is right;
- a subjunctive appears without the main clause or "si" that licenses it;
- an imperative Ud./Uds. row is written as a statement about someone else
  instead of a polite request to the person addressed;
- the sentence would really be said with a different tense — above all a
  preterite where the imperfect is what a speaker would use, or vice versa;
- a subject pronoun is present where Spanish would drop it, or absent where the
  sentence is ambiguous without it;
- the vocabulary is markedly regional rather than pan-Hispanic."""

_guidance_cache: str | None = None


def guidance() -> str:
    """The Spanish style guide, as a JSON string.

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
