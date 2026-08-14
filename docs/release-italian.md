# Promoting the Italian release to production

Everything in this release is packaged and committed; deployment, the Caddy and
DNS side, and the database are the release manager's. Nothing below needs a
registry — images are built on the server from a `git pull`, as usual.

**The one thing that is not routine:** this release adds a *column*, and
`create_all()` cannot add columns. **Run the migration before starting the new
image**, or the app will crash on startup with `column verbs.language does not
exist` and the container will restart-loop.

---

## 1. Before you start

- No new environment variables. `.env` is unchanged.
- No new ports, no Caddy change, no DNS change. Still one vhost on the same
  host port.
- No new Python dependencies. Italian is scraped with `httpx`, which was
  already there.
- **Back up the database.** Not because the migration is risky — it is one
  additive column — but because it is the first schema change this app has
  needed and there is no rollback path that preserves data if it goes wrong.

## 2. Take a backup

```bash
podman exec conjugate-db-1 pg_dump -U conjugate conjugate \
  > ~/conjugate-$(date +%F).sql
```

Check it is non-empty and ends with `PostgreSQL database dump complete`.

## 3. Pull the code

```bash
cd <repo>
git pull
```

## 4. Run the migration

Against the **running old** database, before building or restarting anything.
It is one transaction; if any statement fails the whole thing rolls back and
the old image keeps working.

```bash
podman exec -i conjugate-db-1 psql -U conjugate -d conjugate -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
ALTER TABLE verbs ADD COLUMN language VARCHAR(8) NOT NULL DEFAULT 'pt-PT';

-- Uniqueness on the infinitive alone is a unique INDEX, not a named table
-- constraint, so it is dropped and recreated non-unique rather than
-- DROP CONSTRAINT. Confirm the name with \d verbs first if unsure.
DROP INDEX ix_verbs_infinitive;
CREATE INDEX ix_verbs_infinitive ON verbs (infinitive);

CREATE INDEX ix_verbs_language ON verbs (language);
ALTER TABLE verbs ADD CONSTRAINT uq_verb_language_infinitive
    UNIQUE (language, infinitive);
COMMIT;
SQL
```

Verify — every existing verb should come back as `pt-PT`, and the count should
match what you had before:

```bash
podman exec conjugate-db-1 psql -U conjugate -d conjugate \
  -c "SELECT language, count(*) FROM verbs GROUP BY language;"
```

This is the same migration recorded in [`migrations.md`](migrations.md), and it
was rehearsed against a database with 15 verbs, 1075 forms and 355 attempts —
all preserved.

## 5. Build and start

```bash
cd src/docker
podman-compose up -d --build
```

## 6. Check it came up

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:<host-port>/healthz   # 200
podman logs conjugate-web-1 --tail 20                                          # no traceback
```

If the web container restart-loops with `column verbs.language does not exist`,
step 4 did not run or did not commit. Re-run it; the image is fine.

## 7. Smoke test in the browser

1. Sign in. The Portuguese catalogue should look exactly as before — same
   verbs, same tense order, same accent bar, same scores.
2. **Avatar menu → Interface.** There is a new **Language** picker. Switch to
   **Italian** and save.
3. The verb list will be empty — *"No Italian verbs yet"* — and the accent bar
   becomes `à è é ì ò ó ù`. That is correct: no Italian verbs ship with the
   release.
4. **Avatar menu → Add a verb**, type `parlare`. It should report *"parlare is
   a regular -are verb. Add it?"*; confirm and let it run. ~1–2 minutes.
5. Drill it. Check the rows read `io / tu / lui/lei / noi / voi / loro`, the
   congiuntivo rows show `che io`, and the imperative shows `tu / Lei / noi /
   voi / Loro`.
6. Switch back to **European Portuguese** and confirm your verbs, tense order
   and scores are all as they were.

## What changed for existing users

- **Nothing is lost and nothing needs re-doing.** Every existing verb becomes
  European Portuguese, which is what it already was.
- Saved **tense order** migrates itself. It used to be one flat list; it becomes
  one list per language, and the old flat list is read as Portuguese's until the
  user next saves.
- The **"Tense labels"** interface setting used to have values `en` and `pt`;
  `pt` is now `native` and is labelled with whichever language is being drilled.
  A saved `pt` is read as `native`, so nobody's preference flips.
- **Progress is now per language.** Existing Portuguese totals are unaffected —
  they are all Portuguese — but Italian accuracy will accumulate separately
  rather than being averaged in.

## Known gaps, in case they come up

- **Italian ships with no verbs.** Portuguese has a 10-verb bootstrap seed;
  Italian has none, so the catalogue starts empty and is filled with *Add a
  verb*. Each verb costs an Anthropic call for its ~60 example sentences.
- **Reverso is not a normative source**, unlike cplp.org for Portuguese. Its
  tables are good and it is what `../vibeedit` already uses, but there is no
  Italian equivalent of `tools/voc_check.py`'s 700/700 agreement — an Italian
  hand-checked seed to gate against is still owed.
- **No compound tenses in Italian**, by design — see the README. `passato
  prossimo` is the everyday past, so its absence is the first thing a learner
  will notice; it needs an agreement axis the schema does not have.
- **No negative imperative in Italian.** Reverso does not publish one and this
  project does not derive forms.
- **Reverso cannot distinguish a non-verb from a typo** — both come back as
  *"No Italian verb … found"* rather than *"… is not a verb"*.

## Rolling back

The migration is additive, so the **old image runs unchanged against the
migrated database** — `language` simply sits there with a default. To roll back,
redeploy the previous commit; do not reverse the SQL. Only restore the backup if
something has actually corrupted data, which this release has no path to do.
