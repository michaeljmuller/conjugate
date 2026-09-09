# Promoting the Spanish release to production

Everything in this release is packaged and committed; deployment, the Caddy and
DNS side, and the database are the release manager's. Nothing below needs a
registry — images are built on the server from a `git pull`, as usual.

**Unlike the Italian release, this one is routine.** There is no migration. The
`verbs.language` column the Italian release added already holds `es` (it is
`VARCHAR(8)`), and nothing else about the schema changes. If that release went
in cleanly, this one is a rebuild.

---

## 1. Before you start

- No new environment variables. `.env` is unchanged.
- No new ports, no Caddy change, no DNS change. Still one vhost on the same
  host port.
- No new Python dependencies. Spanish is read with `httpx`, as Italian already
  was.
- No migration, so no forced ordering between the migration and the restart.

A backup is still worth taking, on the general principle that a rebuild is when
you find out whether you had one — but there is nothing in this release that
touches existing rows.

```bash
podman exec conjugate-db-1 pg_dump -U conjugate conjugate \
  > ~/conjugate-$(date +%F).sql
```

## 2. Pull and build

```bash
cd <repo>
git pull
cd src/docker
podman-compose up -d --build
```

## 3. Check it came up

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:<host-port>/healthz   # 200
podman logs conjugate-web-1 --tail 20                                          # no traceback
```

## 4. Smoke test in the browser

1. Sign in. Portuguese and Italian should look exactly as before — same verbs,
   same tense order, same accent bars, same scores.
2. **Avatar menu → Interface.** The **Language** picker now offers a third
   entry, **Spanish**. Switch to it and save.
3. The verb list will be empty — *"No Spanish verbs yet"* — and the accent bar
   becomes `á é í ó ú ü ñ`. That is correct: no Spanish verbs ship with the
   release.
4. **Avatar menu → Add a verb**, type `hablar`. It should report *"hablar is a
   regular -ar verb. Add it?"*; confirm and let it run. Spanish drills 85 cells
   against Italian's ~60, so expect it to take proportionally longer.
5. Drill it. Check that:
   - the rows read `yo / tú / él/ella/Ud. / nosotros / vosotros /
     ellos/ellas/Uds.`
   - the four subjunctive blocks show `que yo`, `que tú`, …
   - the imperative shows `tú / Ud. / nosotros / vosotros / Uds.` — five rows,
     no `yo`
   - the compound tenses read `he hablado`, not a bare `hablado`
   - the imperfect subjunctive answers `hablara`, and typing `hablase` is also
     accepted and reported as the alternative
6. Optionally add `levantarse` to see a reflexive: every answer carries its
   clitic (`me levanto`, `me he levantado`), and the gerund is `levantándose`.
7. Switch back to European Portuguese and confirm your verbs, tense order and
   scores are all as they were.

## What changed for existing users

- **Nothing is lost and nothing needs re-doing.** No existing row is touched.
- The **Language** picker gains a third entry. Tense order, tense selection and
  progress are already per-language, so Spanish starts with its own defaults and
  its own scoreboard without disturbing either existing language.

## Known gaps, in case they come up

- **Spanish ships with no verbs**, like Italian. The catalogue starts empty and
  is filled with *Add a verb*; each verb costs an Anthropic call for its example
  sentences, and Spanish has more rows than either other language.
- **Reverso is not a normative source.** The RAE would be Spanish's cplp.org,
  but `dle.rae.es` is behind a Cloudflare browser challenge and answers 403 to
  any server-side fetch. There is no Spanish equivalent of `tools/voc_check.py`
  and no hand-checked seed to gate against — the same debt Italian already
  carries. `tools/spanish_endings.py --check` is the one canary there is: it
  refetches the model verbs and fails if the table has moved.
- **Reflexive and stem-changing verbs report as "irregular"** in the add-a-verb
  confirmation, even when they are entirely predictable. `web/languages/es/
  regular.py` explains why; the error is one-sided (it understates how regular a
  verb is, never overstates) but it covers a lot of ordinary Spanish vocabulary.
- **No negative imperative.** Reverso publishes none and this project does not
  derive forms. Spanish's negative imperative is the present subjunctive, which
  is drilled in its own right, so little is missing.
- **No voseo**, and no option to hide the vosotros row. Both are wanted; see the
  README.
- **Reverso cannot distinguish a non-verb from a typo**, and in Spanish it is
  worse than in Italian: it resolves any inflected form to a lemma, so the noun
  `mesa` comes back as the conjugation of the verb `mesar` rather than as
  not-found.

## Rolling back

Nothing to undo. Redeploy the previous commit; the database is unchanged either
way, and rows with `language = 'es'` are simply invisible to an image that has
no Spanish adapter.
