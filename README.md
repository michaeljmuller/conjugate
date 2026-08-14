# Conjugation Practice

A web to aid in learning verb conjugation, in **European Portuguese** and
**Italian**. Pick a language and a verb, type each conjugation, and get
immediate feedback.

- **Drilled — pt-PT:** 12 tenses × 5 persons (`eu, tu, ele, nós, eles`) plus the
  two participles. `vós` is stored but skipped, matching the original sheet.
- **Drilled — Italian:** 10 tenses × 6 persons (`io, tu, lui/lei, noi, voi,
  loro`) plus the gerund and past participle. `voi` *is* drilled, unlike `vós`.
  Only simple tenses; see [Why no compound tenses](#why-no-compound-tenses).
- Which tenses appear, and in what order, is a per-user setting **per language**.
- **Grading:** exact match, accents included — a missing diacritic is wrong. An
  accent bar inserts the letters that language needs (`á â ã à é ê í ó ô õ ú ç`
  for Portuguese, `à è é ì ò ó ù` for Italian). A wrong first attempt can be
  reclassified as "just a typo" so it doesn't count against the score.
- **Auth:** Google OAuth (multi-user); progress is per account. Setup:
  [`docs/oauth-setup.md`](../../../docs/oauth-setup.md).

## Stack

FastAPI + SQLAlchemy + PostgreSQL, serving a dependency-free vanilla-JS SPA from
`web/static/`. No frontend build step.

## Layout

```
web/
  main.py          # app wiring: session middleware, routers, static SPA, startup seed
  api.py           # /api: verbs, forms, attempts, progress, me
  auth.py          # Google OAuth (Authlib) + session cookie; DEV_LOGIN escape hatch
  db.py            # engine / session
  models.py        # users, verbs, forms, form_variants, attempts
  grading.py       # normalize + verdict; accepts any of a cell's valid forms
  seed.py          # create tables; upsert_verb / apply_examples, shared with adding a verb
  languages/       # the language abstraction
    base.py        #   Cell / Paradigm / LanguageAdapter; tense-pref reconciliation
    pt/            #   European Portuguese — nothing outside this package is pt-specific
      adapter.py   #     the -ámos rule, the participle split
      catalogue.py #     tense/person catalogue, row labels, subjunctive prefixes
      cplp.py      #     reads paradigms from cplp.org
      regular.py   #     is this verb predictable? (the add-a-verb confirmation)
      prompts.py   #     what Claude is told about pt-PT when writing examples
      examples.json#     by-hand example sentences; doubles as the style guide
    it/            #   Italian — same shape, nothing shared but the abstraction
      adapter.py   #     block-title -> tense; the imperative and che handling
      catalogue.py #     10 simple tenses, 6 drilled persons, row labels
      reverso.py   #     reads paradigms from conjugator.reverso.net
      regular.py   #     the four regular patterns (-are/-ere/-ire/-isc-)
      prompts.py   #     what Claude is told about Italian
      guidance.json#     the Italian style guide
  llm.py           # Claude: write + refine the example sentences (language-neutral)
  jobs.py          # background add-a-verb jobs, with progress for the UI
  data/verbs_seed.json   # the 10 bootstrap pt verbs, 6 persons × 12 tenses (+ participles)
  static/          # index.html, app.js, styles.css
tests/             # pytest, against saved source pages — no network
tools/voc_check.py        # the pt regression gate: seed vs cplp.org
tools/regular_endings.py  # regenerates the pt ending table from cplp.org
tools/italian_endings.py  # regenerates the it ending table from Reverso
```

Adding a language is a new adapter plus a source for it — `jobs.py`, `api.py`,
`llm.py`, `seed.py` and the front end never learn that more than one exists.
Everything language-specific reaches them through `LanguageAdapter`: the tense
catalogue, the drilled persons, the row labels, the accent bar, the source's
name, the regularity check, and the prompt material.

## Languages

| | European Portuguese | Italian |
|---|---|---|
| Code | `pt-PT` | `it` |
| Source | [cplp.org](https://voc.cplp.org) | [Reverso](https://conjugator.reverso.net) |
| Normative? | yes — the vocabulary AO90 mandates | no — a commercial aggregator |
| Tenses drilled | 14 | 10 |
| Persons drilled | 5 (+2 participle rows) | 6 (+1 personless) |
| Regular patterns | 3 (`-ar/-er/-ir`) | 4 (`-are/-ere/-ire/-ire`-isc) |

The asymmetry in *normative?* is the one that matters. cplp.org publishes what
the Acordo Ortográfico obliges the signatory states to produce, and it agreed
with this project's hand-curated seed on all 700 cells — which is why nothing
second-guesses it and `llm.py` does not check the conjugation. Reverso has no
such standing. Its tables are good and widely used, but "unverified" is the
honest description, so an Italian equivalent of `tools/voc_check.py` against a
hand-checked seed is still owed.

### Why no compound tenses

Reverso publishes Italian's eight compound tenses; none are drilled. Their row
count depends on the verb: `parlare` (avere) gives six, `arrivare` (essere)
gives eight because the participle agrees in gender and number, and `correre` —
which takes both auxiliaries in different senses — gives **fourteen**, all under
one tense heading. One answer per `(tense, person)` cannot hold that, and the
agreement forms are not interchangeable: `sono corso` and `sono corsa` are each
right for a different subject, so accepting either would teach the wrong thing.
Drilling them needs an agreement axis the schema does not have — the same
question [`docs/todo.txt`](docs/todo.txt) raises for Portuguese's compound
pluperfect and future, and worth designing once for both.

## Run locally

From `src/docker/`:

```bash
cp .env.example .env          # set SESSION_SECRET; uncomment DEV_LOGIN=1 + SESSION_HTTPS_ONLY=0
docker compose up --build
```

Open <http://localhost:8081>. With `DEV_LOGIN=1` the "Sign in" button logs in a fake
local user so you can drill without Google credentials.

## Tests

```bash
pip install -e .[test] && pytest
```

## Adding a verb

**Avatar menu → Add a verb.** Type an infinitive and the app does the rest, showing
each step as it goes:

The verb is added to **whichever language you are drilling**, from that
language's own source.

1. **Look up the conjugation** — from the language's source (above). The job
   then stops and reports how predictable the verb is — *"parlare is a regular
   -are verb"*, *"mangiare is a regular -are verb, apart from a spelling change:
   gi → g before e/i (mangi, mangerò)"* — so you can decline a verb that teaches
   nothing the model verb hasn't. Confirming resumes.
2. **Write example sentences** — one English/target-language pair per drilled
   form, ~60 a verb.
3. **Review and revise** — each pair is checked mechanically (does the
   translation contain the exact form?) and by a second model pass (natural?
   right tense sense? right subject?). Whatever is flagged gets rewritten, for up
   to two rounds. Anything still weak is saved anyway and reported rather than
   dropped.
4. **Save** — nothing is written until here, so a failure earlier leaves no
   half-made verb behind.

Steps 2–4 are language-neutral. What the model is told *about* the language —
what to call it, the one rule that matters most, extra grounds for rejecting a
sentence, and the style guide — comes from the adapter's `PromptMaterial`. For
Portuguese that rule is not drifting into Brazilian; for Italian it is not
substituting the passato prossimo for the passato remoto, and writing the
imperative's `Lei`/`Loro` rows as the polite forms they are.

**Requires `ANTHROPIC_API_KEY`.** Without it the request is refused outright
(503) rather than adding a verb whose rows have no prompt. If the key exists but
is rejected, rate-limited or out of credit, the job fails at the sentence step —
and since nothing is written until the last step, the catalogue is untouched.

### More than one right answer

Portuguese genuinely offers alternatives in some cells, and the drill takes them
all: type `ouço` where it shows `oiço` and it is correct, with *also correct:
oiço* appearing once the row is answered. The forms come from the source; only
one selection is made programmatically — the 1st person plural preterite of `-ar`
verbs keeps the pt-PT acute (`falámos`, not `falamos`), which the Acordo ties to
the open stressed vowel of the European variety.

The **past participle** is drilled as two rows, labelled by the auxiliary the
form takes: `ter / haver` for the regular participle (*tinha aceitado*) and
`ser / estar` for the short one (*foi aceite*). Most verbs have the same form in
both.

New verbs live in the database. `verbs_seed.json` stays the bootstrap seed for a
fresh database — startup seeding only ever fills gaps, so the two coexist.

## Example sentences

Each drilled form can carry an example sentence in **English** (`example_en`, the
always-visible prompt — faint under the field, bold when focused) and its **European
Portuguese** translation (`example_pt`, revealed under it only *after* the form is
answered, since it contains the answer word).

Adding a verb writes these automatically (above).
`web/languages/pt/examples.json` is the older, by-hand route, still used for the
seeded verbs: it holds the `_instructions` and `_guidance` style guide — which
the pt adapter also hands to `llm.py`, so both routes produce sentences in one
voice — and `seed_examples()` syncs every non-empty sentence into
`forms.example_en` / `forms.example_pt` on startup. Blanks never overwrite existing
text, so it can be filled incrementally.

`llm.py` itself knows no Portuguese: it owns the draft → check → rewrite loop,
and each adapter supplies its own `PromptMaterial` (what to call the language,
the one rule that matters most, extra grounds for rejecting a sentence, and the
style guide).

## Future add-ons (schema already supports)

- Pronunciation audio per form (`forms.audio_url`).
