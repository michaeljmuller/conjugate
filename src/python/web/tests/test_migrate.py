"""The startup schema patch.

The patch itself only ever fires on PostgreSQL, and these run on SQLite, so
what is pinned here is the half that protects a working database: that a
current schema is left alone, and that a non-PostgreSQL engine is not touched
at all. The PostgreSQL path — an old-shaped `verbs` table being altered — was
verified against the dev container; see docs/migrations.md.
"""

from sqlalchemy import create_engine, inspect

from web.migrate import patch_schema
from web.models import Base


def _fresh(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    Base.metadata.create_all(engine)
    return engine


def test_a_current_schema_is_left_alone(tmp_path):
    """The normal boot: nothing to patch, so nothing is reported."""
    assert patch_schema(_fresh(tmp_path)) == []


def test_patching_is_repeatable(tmp_path):
    """It runs on every boot, so a second run must be as quiet as the first."""
    engine = _fresh(tmp_path)
    patch_schema(engine)
    assert patch_schema(engine) == []


def test_an_empty_database_is_left_to_create_all(tmp_path):
    """No tables yet: create_all() builds them in the current shape, so there is
    nothing for a patch to find and no table for it to trip over."""
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    assert patch_schema(engine) == []
    assert "verbs" not in inspect(engine).get_table_names()


def test_sqlite_is_never_altered(tmp_path):
    """SQLite cannot ALTER TABLE ... ADD CONSTRAINT, and never holds an old
    shape, so the patch declines it outright rather than half-applying."""
    engine = _fresh(tmp_path)
    before = sorted(c["name"] for c in inspect(engine).get_columns("verbs"))
    assert patch_schema(engine) == []
    assert sorted(c["name"] for c in inspect(engine).get_columns("verbs")) == before
