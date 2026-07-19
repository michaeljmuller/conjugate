"""Per-user tense settings: reconciliation logic + the settings API end-to-end."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.auth import current_user
from web.conjugation import TENSE_KEYS, resolve_tense_prefs
from web.db import get_db
from web.main import app
from web.models import Base, Form, User, Verb


# ---- resolve_tense_prefs (pure) -----------------------------------------

def test_resolve_defaults_to_all_enabled_canonical():
    resolved = resolve_tense_prefs([])
    assert [t["key"] for t in resolved] == TENSE_KEYS
    assert all(t["enabled"] for t in resolved)
    assert all({"key", "label", "mood", "enabled"} <= t.keys() for t in resolved)


def test_resolve_keeps_order_and_flags_drops_unknown_appends_new():
    saved = [
        {"key": "conditional", "enabled": False},
        {"key": "bogus_tense", "enabled": True},
        {"key": "preterite", "enabled": True},
    ]
    resolved = resolve_tense_prefs(saved)
    keys = [t["key"] for t in resolved]

    assert keys[:2] == ["conditional", "preterite"]   # order + unknown dropped
    assert "bogus_tense" not in keys
    assert set(keys) == set(TENSE_KEYS)               # every catalog tense present

    by = {t["key"]: t["enabled"] for t in resolved}
    assert by["conditional"] is False                 # saved flag preserved
    assert by["preterite"] is True
    assert by["present_indicative"] is True           # a not-saved tense: enabled


# ---- settings API end-to-end --------------------------------------------

_FORMS = {
    "present_indicative": {"eu": "sou", "tu": "és"},
    "preterite": {"eu": "fui", "tu": "foste"},
    "present_subjunctive": {"eu": "seja", "tu": "sejas"},
    "conditional": {"eu": "seria", "tu": "serias"},
}


def _make_client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'settings.db'}")
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine)
    with TS() as db:
        user = User(google_sub="t", email="t@example.com", name="T")
        db.add(user)
        verb = Verb(infinitive="ser")
        for tense, persons in _FORMS.items():
            for person, text in persons.items():
                verb.forms.append(Form(tense=tense, person=person, form_text=text))
        db.add(verb)
        db.commit()
        user_obj, vid = db.get(User, user.id), verb.id
        db.expunge(user_obj)

    def override_db():
        db = TS()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: user_obj
    return TestClient(app), vid


def _block_keys(client, vid):
    return [b["tense"] for b in client.get(f"/api/verbs/{vid}/forms").json()["blocks"]]


def test_default_order_then_reorder_and_disable(tmp_path):
    client, vid = _make_client(tmp_path)
    try:
        # No settings yet → canonical order among the four seeded tenses.
        assert _block_keys(client, vid) == [
            "present_indicative", "preterite", "conditional", "present_subjunctive",
        ]

        # Move conditional first, disable the subjunctive.
        r = client.put("/api/settings", json={"tenses": [
            {"key": "conditional", "enabled": True},
            {"key": "present_indicative", "enabled": True},
            {"key": "preterite", "enabled": True},
            {"key": "present_subjunctive", "enabled": False},
        ]})
        assert r.status_code == 200

        # Drill reflects the new order; subjunctive is gone.
        assert _block_keys(client, vid) == ["conditional", "present_indicative", "preterite"]

        # GET returns the reconciled full list: order kept, subjunctive flagged off,
        # every other catalog tense appended enabled.
        got = client.get("/api/settings").json()["tenses"]
        keys = [t["key"] for t in got]
        assert keys[:4] == ["conditional", "present_indicative", "preterite", "present_subjunctive"]
        assert set(keys) == set(TENSE_KEYS)
        flags = {t["key"]: t["enabled"] for t in got}
        assert flags["present_subjunctive"] is False
        assert flags["conditional"] is True
        assert flags["future_indicative"] is True  # not sent → default enabled
    finally:
        app.dependency_overrides.clear()


def test_put_rejects_unknown_key_and_all_disabled(tmp_path):
    client, _ = _make_client(tmp_path)
    try:
        assert client.put(
            "/api/settings", json={"tenses": [{"key": "nope", "enabled": True}]}
        ).status_code == 400
        assert client.put(
            "/api/settings", json={"tenses": [{"key": "preterite", "enabled": False}]}
        ).status_code == 400
    finally:
        app.dependency_overrides.clear()
