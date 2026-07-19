# Conjugation Practice

A web port of the Excel "Conjugation Practice Tool" for European-Portuguese verbs.
Pick a verb, type each conjugation, and check it against the answer key — the same
type-and-check drill as the spreadsheet, plus per-user progress tracking.

- **Drilled:** 7 tenses × 5 persons (`eu, tu, ele, nós, eles`). `vós` is stored but
  skipped in the drill, matching the original sheet.
- **Grading:** exact match is correct; a diacritic-only miss (e.g. `venho` for
  `vênho`) is flagged amber as "almost — check the accent" and not counted correct.
  An accent bar inserts `á â ã à é ê í ó ô õ ú ç`.
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
  models.py        # users, verbs, forms, attempts (forms carry future example/audio cols)
  grading.py       # normalize + accent-tolerant verdict
  seed.py          # create tables, seed verbs if empty
  conjugation.py   # tense/person constants, subjunctive pronoun prefixes
  data/verbs_seed.json   # 10 verbs, 6 persons × 7 tenses (+ participles), typos fixed
  static/          # index.html, app.js, styles.css
tests/             # pytest
```

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

## Example sentences

Each drilled form can carry an example sentence in **English** (`example_en`, the
always-visible prompt — faint under the field, bold when focused) and its **European
Portuguese** translation (`example_pt`, revealed under it only *after* the form is
answered, since it contains the answer word). They live in `web/data/examples.json`, a
fill-out form covering all 350 drilled forms (10 verbs × 7 tenses × 5 persons):

1. Hand `examples.json` to a capable model — the embedded `_instructions` and
   `_guidance` tell it to fill each `example_en` and matching pt-PT `example_pt`.
2. Save the returned file back to `web/data/examples.json`.
3. Restart the app. `seed_examples()` syncs every non-empty sentence into
   `forms.example_en` / `forms.example_pt` on startup (blanks never overwrite existing
   text), so you can fill it incrementally.

## Future add-ons (schema already supports)

- Web UI to add verbs (`verbs.created_by` is wired).
- Editing example sentences in-app (currently seeded from `examples.json`).
- Pronunciation audio per form (`forms.audio_url`).
