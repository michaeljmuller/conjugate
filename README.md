# Conjugation Practice

A web to aid in learning the conjugation European-Portuguese verbs.
Pick a verb, type each conjugation, and get immediate feedback.

- **Drilled:** 12 tenses × 5 persons (`eu, tu, ele, nós, eles`) plus the two
  participles. `vós` is stored but skipped in the drill, matching the original
  sheet. Which tenses appear, and in what order, is a per-user setting.
- **Grading:** exact match, accents included — a missing diacritic is wrong. An
  accent bar inserts `á â ã à é ê í ó ô õ ú ç`. A wrong first attempt can be
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
  conjugation.py   # pt tense/person catalogue, row labels, subjunctive prefixes
  languages/       # the language abstraction
    base.py        #   Cell / Paradigm / LanguageAdapter
    pt_pt.py       #   European Portuguese: the -ámos rule, the participle split
    cplp.py        #   reads paradigms from cplp.org
  llm.py           # Claude: write + refine the example sentences
  jobs.py          # background add-a-verb jobs, with progress for the UI
  data/verbs_seed.json   # the 10 bootstrap verbs, 6 persons × 12 tenses (+ participles)
  static/          # index.html, app.js, styles.css
tests/             # pytest, against saved cplp.org pages — no network
tools/voc_check.py # the regression gate: seed vs cplp.org
```

Adding a language is a new adapter plus a source for it — `jobs.py`, `api.py` and
the front end never learn that more than one exists.

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

1. **Look up the conjugation** — from **cplp.org**, which publishes the
   orthographic vocabulary that Article 2 of the Acordo Ortográfico obliges the
   signatory states to produce. It is normative rather than one more site with an
   opinion: checked against the ten hand-curated seed verbs it agrees on all 700
   cells, so nothing second-guesses it afterwards. `tools/voc_check.py` re-runs
   that check.
2. **Write example sentences** — one English/pt-PT pair per drilled form, ~60 a verb.
3. **Review and revise** — each pair is checked mechanically (does the Portuguese
   actually contain the exact form?) and by a second model pass (natural pt-PT?
   right tense sense? right subject?). Whatever is flagged gets rewritten, for up
   to two rounds. Anything still weak is saved anyway and reported rather than
   dropped.
4. **Save** — nothing is written until here, so a failure earlier leaves no
   half-made verb behind.

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

Adding a verb writes these automatically (above). `web/data/examples.json` is the
older, by-hand route, still used for the seeded verbs: it holds the `_instructions`
and `_guidance` style guide — which `llm.py` also reads, so both routes produce
sentences in one voice — and `seed_examples()` syncs every non-empty sentence into
`forms.example_en` / `forms.example_pt` on startup. Blanks never overwrite existing
text, so it can be filled incrementally.

## Future add-ons (schema already supports)

- Pronunciation audio per form (`forms.audio_url`).
