# Conjugation Practice

A web to aid in learning verb conjugation, in **European Portuguese**,
**Italian** and **Spanish**. Pick a language and a verb, type each conjugation,
and get immediate feedback.

- **Drilled — pt-PT:** 12 tenses × 5 persons (`eu, tu, ele, nós, eles`) plus the
  two participles. `vós` is stored but skipped, matching the original sheet.
- **Drilled — Italian:** 10 tenses × 6 persons (`io, tu, lui/lei, noi, voi,
  loro`) plus the gerund and past participle. `voi` *is* drilled, unlike `vós`.
  Only simple tenses; see
  [Why no compound tenses in Italian](#why-no-compound-tenses-in-italian).
- **Drilled — Spanish:** 14 tenses × 6 persons (`yo, tú, él/ella/Ud., nosotros,
  vosotros, ellos/ellas/Uds.`) plus the gerund and past participle. `vosotros`
  *is* drilled — see [Spanish and vosotros](#spanish-and-vosotros) — and so are
  the six compound tenses, which Spanish can hold and Italian cannot.
- Which tenses appear, and in what order, is a per-user setting **per language**.
- **Grading:** exact match, accents included — a missing diacritic is wrong. An
  accent bar inserts the letters that language needs (`á â ã à é ê í ó ô õ ú ç`
  for Portuguese, `à è é ì ò ó ù` for Italian, `á é í ó ú ü ñ` for Spanish). A
  wrong first attempt can be
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
      regular.py   #     the four regular patterns (-are/-ere/-ire/-isc-)
      prompts.py   #     what Claude is told about Italian
      guidance.json#     the Italian style guide
    es/            #   Spanish — same shape again
      adapter.py   #     block-title -> tense; -ra/-se merging, reflexive clitics
      catalogue.py #     16 tenses (6 compound), 6 drilled persons, row labels
      regular.py   #     three patterns, and spelling changes in both directions
      prompts.py   #     what Claude is told about Spanish
      guidance.json#     the Spanish style guide
    reverso.py     #   reads paradigms from conjugator.reverso.net (it + es)
  llm.py           # Claude: write + refine the example sentences (language-neutral)
  jobs.py          # background add-a-verb jobs, with progress for the UI
  data/verbs_seed.json   # the 10 bootstrap pt verbs, 6 persons × 12 tenses (+ participles)
  static/          # index.html, app.js, styles.css
tests/             # pytest, against saved source pages — no network
tools/pull_seed.sh        # refresh the seed files from the deployment's database
tools/voc_check.py        # the pt regression gate: seed vs cplp.org
tools/regular_endings.py  # regenerates the pt ending table from cplp.org
tools/italian_endings.py  # regenerates the it ending table from Reverso
tools/spanish_endings.py  # regenerates the es ending table from Reverso
```

Adding a language is a new adapter plus a source for it — `jobs.py`, `api.py`,
`llm.py`, `seed.py` and the front end never learn that more than one exists.
Everything language-specific reaches them through `LanguageAdapter`: the tense
catalogue, the drilled persons, the row labels, the accent bar, the source's
name, the regularity check, and the prompt material.

## Languages

| | European Portuguese | Italian | Spanish |
|---|---|---|---|
| Code | `pt-PT` | `it` | `es` |
| Source | [cplp.org](https://voc.cplp.org) | [Reverso](https://conjugator.reverso.net) | [Reverso](https://conjugator.reverso.net) |
| Normative? | yes — the vocabulary AO90 mandates | no — a commercial aggregator | no — the RAE is Cloudflare-gated |
| Tenses drilled | 14 | 10 | 16 (6 of them compound) |
| Persons drilled | 5 (+2 participle rows) | 6 (+1 personless) | 6 (+1 personless) |
| Regular patterns | 3 (`-ar/-er/-ir`) | 4 (`-are/-ere/-ire/-ire`-isc) | 3 (`-ar/-er/-ir`) |

The asymmetry in *normative?* is the one that matters. cplp.org publishes what
the Acordo Ortográfico obliges the signatory states to produce, and it agreed
with this project's hand-curated seed on all 700 cells — which is why nothing
second-guesses it and `llm.py` does not check the conjugation. Reverso has no
such standing. Its tables are good and widely used, but "unverified" is the
honest description, so an Italian equivalent of `tools/voc_check.py` against a
hand-checked seed is still owed. Spanish inherits that gap. The RAE would be its
cplp.org — the same kind of normative authority — but `dle.rae.es` sits behind a
Cloudflare browser challenge and answers 403 to any server-side fetch, so
Reverso is what there is. `en.wiktionary.org` (or kaikki.org's extracted JSON)
is the openly-licensed fallback if Reverso ever changes shape.

### Spanish and vosotros

`vosotros` is drilled, which is the opposite of the `vós` call in Portuguese.
`vós` is archaic in every variety, so drilling it would teach a form nobody
uses. `vosotros` is ordinary everyday speech in Spain, and US textbooks —
Realidades/Auténtico, Descubre/Vistas, Avancemos — print the six-person chart
with it in, with the AP exam expecting recognition. It costs one row, and
nothing is missing for a learner who will never say it: Latin American `ustedes`
takes the same forms as `ellos`, which is already a drilled row.

An option to hide the row (and a `pt-BR` variety, which would need a different
source — cplp.org's tables are identical under both editions) is wanted but not
built.

### Spanish and reflexive verbs

Typing a reflexive infinitive adds the plain verb: `levantarse` adds `levantar`,
`dormirse` adds `dormir`. The confirmation says so before you agree to it.

The reason is that a reflexive adds no conjugation. Measured against `levantar`,
the 85 cells of `levantarse` are one identical (the participle takes no
pronoun), 78 that are the same conjugated form with a fixed pronoun in front —
`me`, `te`, `se`, `nos`, `os`, `se`, chosen by the person and never anything
else — and 6 where the pronoun fuses onto the end (`levántate`, `levantémonos`,
`levantaos`). Even those six leave the conjugation alone; only the spelling of
the fused word changes. So drilling a reflexive asks for the same six-item
pronoun list eighty times per verb, which is vocabulary, not conjugation.

The pronoun is also a separate axis rather than part of the verb: `te levanto`
("I get you up") is equally good Spanish. Drilling the reflexive would cover only
the slice of that axis where the object happens to be the subject, and this drill
has no way to model the rest — the same shape of problem that keeps Italian's
compound tenses out.

Nothing is lost. The reflexive *sense* still reaches the learner through the
example sentences, which are told to mix it with the plain one — so `levantar`'s
`yo` row can be *Me levanto temprano* and its `tú` row *Levantas las pesas*.

The one machinery this needs is `LanguageAdapter.substitute`, which Portuguese
and Italian both leave as `None`. Italian has the same clitic question
(`lavarsi`) and does not currently answer it.

### Spanish and compound tenses

Spanish **does** drill them, unlike Italian. The reason Italian
excludes them does not apply: after *haber* the participle never agrees, so
every Spanish compound tense is exactly six rows. Reverso publishes three tenses
that are not drilled because they are dead rather than out of scope — the
`pretérito anterior` (*hube hablado*) and both future subjunctives (*hablare*,
*hubiere hablado*). Portuguese drills its future subjunctive because the tense
is alive there; Spanish is where it died.

### Why no compound tenses in Italian

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
