"""What Claude needs to know to write European-Portuguese example sentences.

``llm.py`` owns the shape of the request — one English sentence per slot, plus a
translation containing the exact form, then a critique round and a rewrite of
whatever was flagged. None of that is language-specific. Everything that *is*
lives here.

The style guide is not written twice: it is read from ``examples.json``, the
same tuned ``_instructions``/``_guidance`` block that produced the existing
hand-made catalogue, so verbs added through the app sound like the ones already
there.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..base import PromptMaterial

EXAMPLES_FILE = Path(__file__).parent / "examples.json"

NAME = "European Portuguese"

# Stated up front in both prompts rather than left to the appended style guide:
# the drill is specifically for the European variety, and pt-BR phrasing is the
# failure mode a model drifts into by default. The full contrast lists live in
# examples.json's _guidance.variety, which is appended after this.
VARIETY_RULE = """LANGUAGE VARIETY — the one rule that matters most:

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

# Extra grounds for rejecting a sentence, appended to the critique prompt's
# shared list. Portuguese's is entirely about catching pt-BR drift.
CRITIQUE_RULES = """- ANY part of the Portuguese is Brazilian rather than European — a pt-BR
  construction ("estou correndo", "me chamo", "você fala", "a gente vai"), a
  pt-BR word (trem, ônibus, celular, banheiro, suco, sorvete, café da manhã), or
  a pt-BR spelling (acadêmico, gênero, falamos for falámos);
- a subjunctive lacks the trigger that licenses it.

Do NOT report a correct pt-PT form for looking unlike its Brazilian equivalent —
that is the point."""

_guidance_cache: str | None = None


def guidance() -> str:
    """The pt-PT style guide from ``examples.json``, as a JSON string.

    Carries the variety rules, the person glosses, the subjunctive prefixes, a
    usage note for each tense, and worked style examples.
    """
    global _guidance_cache
    if _guidance_cache is None:
        data = json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))
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
