"""Schema patches that ``create_all()`` cannot apply.

``Base.metadata.create_all()`` adds missing *tables*. It will never add a
missing column to a table that already exists, so a database created before a
column existed stays wrong until somebody alters it. This runs those alterations
at startup, so a deployment does not depend on the release manager remembering
the SQL in ``docs/migrations.md``.

Every patch first inspects the live schema and does nothing unless the thing it
would change is actually missing. That is what makes it safe on every boot:
against an already-patched database, or a fresh one ``create_all()`` has just
built in the current shape, the whole module is a few catalogue reads.

PostgreSQL only. The tests run on SQLite and always start from a fresh
``create_all()``, so there is never an old shape there to patch — and SQLite
cannot ``ALTER TABLE ... ADD CONSTRAINT`` anyway.

Adding a patch here does not retire its entry in ``docs/migrations.md``: that
file is the record of what changed and why, and is what you read when a patch
has to be undone by hand.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from .languages import DEFAULT_LANGUAGE

log = logging.getLogger(__name__)


def patch_schema(engine) -> list[str]:
    """Bring an existing database up to the current shape.

    Returns what it changed, newest schema last, for the caller to log. An empty
    list is the normal answer.

    Runs after ``init_db``: on an empty database ``create_all()`` has already
    built every table in the current shape, which leaves each patch below with
    nothing to find.
    """
    if engine.dialect.name != "postgresql":
        return []
    with engine.begin() as conn:
        if "verbs" not in inspect(conn).get_table_names():
            return []
        done = _verbs_language(conn)
    for change in done:
        log.info("schema patch applied: %s", change)
    return done


def _verbs_language(conn) -> list[str]:
    """``verbs.language``, and the index rearrangement that goes with it.

    Needed by the release that added a second drillable language: before it,
    every verb was European Portuguese and the infinitive alone was unique.
    Written out in full, with the reasoning, under ``verbs.language`` in
    ``docs/migrations.md``; these are the same statements, each one guarded so
    a half-applied database finishes the job rather than failing on the step it
    already has.
    """
    inspector = inspect(conn)
    done: list[str] = []

    columns = {c["name"] for c in inspector.get_columns("verbs")}
    if "language" not in columns:
        # DEFAULT_LANGUAGE is our own constant, not input; DDL takes no bound
        # parameters, so it is interpolated.
        conn.execute(
            text(
                "ALTER TABLE verbs ADD COLUMN language VARCHAR(8) "
                f"NOT NULL DEFAULT '{DEFAULT_LANGUAGE}'"
            )
        )
        done.append(f"verbs.language added, defaulting to {DEFAULT_LANGUAGE}")

    indexes = {i["name"]: i for i in inspector.get_indexes("verbs")}
    # Uniqueness on the infinitive alone was a unique INDEX rather than a named
    # table constraint, so it is dropped and recreated rather than dropped by
    # name as a constraint.
    if indexes.get("ix_verbs_infinitive", {}).get("unique"):
        conn.execute(text("DROP INDEX ix_verbs_infinitive"))
        conn.execute(text("CREATE INDEX ix_verbs_infinitive ON verbs (infinitive)"))
        done.append("ix_verbs_infinitive made non-unique")

    if "ix_verbs_language" not in indexes:
        conn.execute(text("CREATE INDEX ix_verbs_language ON verbs (language)"))
        done.append("ix_verbs_language created")

    constraints = {c["name"] for c in inspector.get_unique_constraints("verbs")}
    if "uq_verb_language_infinitive" not in constraints:
        conn.execute(
            text(
                "ALTER TABLE verbs ADD CONSTRAINT uq_verb_language_infinitive "
                "UNIQUE (language, infinitive)"
            )
        )
        done.append("uq_verb_language_infinitive added")

    return done
