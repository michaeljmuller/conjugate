# Schema migrations

The schema is created by `Base.metadata.create_all()` on startup and nothing
else. That adds *missing tables* to an existing database, so most changes need
no migration — a new table appears by itself, and new settings go into the
`user_settings` JSON blob rather than into columns.

It will **not** add a column to a table that already exists. Those are listed
here, newest first, to be run once against the production database before
deploying the release that needs them. A fresh database needs none of them:
`create_all()` builds the current shape directly.

## `verbs.language`

Needed by: the release that adds a second drillable language.

Run as one transaction — verified against a database created before the column
existed (15 verbs, 1075 forms, 355 attempts; all preserved):

```sql
BEGIN;
ALTER TABLE verbs ADD COLUMN language VARCHAR(8) NOT NULL DEFAULT 'pt-PT';

-- Uniqueness on the infinitive alone is a unique INDEX, not a named table
-- constraint (SQLAlchemy's index=True, unique=True) — so it is dropped and
-- recreated non-unique rather than DROP CONSTRAINT.
DROP INDEX ix_verbs_infinitive;
CREATE INDEX ix_verbs_infinitive ON verbs (infinitive);

CREATE INDEX ix_verbs_language ON verbs (language);
ALTER TABLE verbs ADD CONSTRAINT uq_verb_language_infinitive
    UNIQUE (language, infinitive);
COMMIT;
```

Every existing verb is European Portuguese, which is what the default fills in,
so the data needs no other change. Confirm with
`SELECT language, count(*) FROM verbs GROUP BY language;` — one `pt-PT` row.
Check `\d verbs` first if the index name differs.

Saved tense preferences migrate themselves: `user_settings.data["tenses"]` was a
flat list and becomes `{language: [...]}`, with any flat list still read as the
default language's until the user next saves.
