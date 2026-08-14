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

```sql
ALTER TABLE verbs ADD COLUMN language VARCHAR(8) NOT NULL DEFAULT 'pt-PT';
CREATE INDEX ix_verbs_language ON verbs (language);

-- Infinitives are unique per language now, not globally.
ALTER TABLE verbs DROP CONSTRAINT verbs_infinitive_key;
ALTER TABLE verbs ADD CONSTRAINT uq_verb_language_infinitive
    UNIQUE (language, infinitive);
```

Every existing verb is European Portuguese, which is what the default fills in,
so the data needs no other change. The old unique index on `infinitive` alone
may be named differently — check with `\d verbs` before dropping it.

Saved tense preferences migrate themselves: `user_settings.data["tenses"]` was a
flat list and becomes `{language: [...]}`, with any flat list still read as the
default language's until the user next saves.
