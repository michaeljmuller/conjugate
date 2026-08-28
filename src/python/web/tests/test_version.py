"""Which commit is running, as reported by /healthz.

The stamp is written into the image by the Dockerfile's version stage, so these
tests exercise the reading half: what happens with a good file, no file, and a
file that is not what we expect. The health check must survive all three — one
that fails because it cannot name itself is worse than one that says "dev".
"""

import pytest
from fastapi.testclient import TestClient

from web import main as main_mod
from web.main import app, read_version

STAMP = "9f8e5ad\n2026-08-28T09:59:30-06:00\n"


def _write(tmp_path, text):
    p = tmp_path / "VERSION"
    p.write_text(text, encoding="utf-8")
    return p


def test_reads_the_hash_and_commit_date(tmp_path):
    assert read_version(_write(tmp_path, STAMP)) == {
        "version": "9f8e5ad",
        "committed": "2026-08-28T09:59:30-06:00",
    }


def test_absent_file_reads_as_dev(tmp_path):
    """What running outside a container looks like — the tests included."""
    assert read_version(tmp_path / "nothing-here") == {"version": "dev", "committed": ""}


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", {"version": "dev", "committed": ""}),            # empty
        ("\n\n", {"version": "dev", "committed": ""}),        # blank lines
        ("9f8e5ad\n", {"version": "9f8e5ad", "committed": ""}),  # hash, no date
        ("  9f8e5ad  \n  2026-01-01T00:00:00Z  \n",           # stray whitespace
         {"version": "9f8e5ad", "committed": "2026-01-01T00:00:00Z"}),
    ],
)
def test_a_malformed_stamp_degrades_rather_than_raising(tmp_path, text, expected):
    assert read_version(_write(tmp_path, text)) == expected


def test_a_directory_where_the_file_should_be_still_reads(tmp_path):
    """OSError, not just FileNotFoundError: the read is wrapped for any of them."""
    (tmp_path / "VERSION").mkdir()
    assert read_version(tmp_path / "VERSION")["version"] == "dev"


def test_healthz_reports_the_version_without_authentication(monkeypatch):
    """Answerable by curl: no browser, no sign-in, no session cookie."""
    monkeypatch.setattr(
        main_mod, "VERSION", {"version": "9f8e5ad", "committed": "2026-08-28T09:59:30-06:00"}
    )
    body = TestClient(app).get("/healthz").json()

    assert body == {
        "status": "ok",
        "version": "9f8e5ad",
        "committed": "2026-08-28T09:59:30-06:00",
    }
