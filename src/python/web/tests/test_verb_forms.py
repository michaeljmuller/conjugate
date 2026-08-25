"""What /api/verbs/{id}/forms chooses to render.

The endpoint is not a straight dump of the stored rows: a contrastive row —
pt-PT's ser/estar participle — is dropped when it holds the same form as the
row it contrasts with, because then it is the answer above it typed again.
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.auth import current_user
from web.db import get_db
from web.languages import INVARIABLE_PERSON
from web.languages.pt.catalogue import PAST_PARTICIPLE_TENSE, SHORT_PERSON
from web.main import app
from web.models import Base, Form, FormVariant, User, Verb


def _client(tmp_path, *, past: str, short: str, short_variants: tuple[str, ...] = ()):
    engine = create_engine(f"sqlite:///{tmp_path / 'forms.db'}")
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine)
    with TS() as db:
        user = User(google_sub="t", email="t@example.com", name="T")
        db.add(user)
        verb = Verb(infinitive="aceitar", past_participle=past)
        verb.forms.append(
            Form(tense=PAST_PARTICIPLE_TENSE, person=INVARIABLE_PERSON, form_text=past)
        )
        short_row = Form(
            tense=PAST_PARTICIPLE_TENSE, person=SHORT_PERSON, form_text=short
        )
        short_row.variants = [FormVariant(text=t) for t in short_variants]
        verb.forms.append(short_row)
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


def _participle_rows(client, vid):
    blocks = client.get(f"/api/verbs/{vid}/forms").json()["blocks"]
    block = next(b for b in blocks if b["tense"] == PAST_PARTICIPLE_TENSE)
    return [(r["person"], r["label"]) for r in block["rows"]]


def _participle_persons(client, vid):
    return [person for person, _ in _participle_rows(client, vid)]


def test_short_participle_hidden_when_it_repeats_the_regular_one(tmp_path):
    """``ouvido``/``ouvido``: the ser/estar row would just be a free copy."""
    client, vid = _client(tmp_path, past="ouvido", short="ouvido")
    try:
        assert _participle_persons(client, vid) == [INVARIABLE_PERSON]
    finally:
        app.dependency_overrides.clear()


def test_short_participle_shown_when_it_differs(tmp_path):
    """``aceitado``/``aceite``: the row is the whole point for this verb."""
    client, vid = _client(tmp_path, past="aceitado", short="aceite")
    try:
        assert _participle_persons(client, vid) == [INVARIABLE_PERSON, SHORT_PERSON]
    finally:
        app.dependency_overrides.clear()


def test_hiding_is_display_only_and_leaves_the_row_stored(tmp_path):
    """The hidden row stays in the database, so reversing the rule needs no data.

    It also stays gradeable: /api/attempts re-grades against the stored form,
    and an attempt on a row the drill no longer renders is still valid.
    """
    client, vid = _client(tmp_path, past="posto", short="posto")
    try:
        assert _participle_persons(client, vid) == [INVARIABLE_PERSON]
        from web.db import get_db as _  # noqa: F401

        db = next(app.dependency_overrides[get_db]())
        rows = {f.person for f in db.get(Verb, vid).forms}
        assert rows == {INVARIABLE_PERSON, SHORT_PERSON}
    finally:
        app.dependency_overrides.clear()


def test_variants_alone_do_not_keep_the_row(tmp_path):
    """Only the displayed answer counts: same form_text, still hidden.

    A variant is never what the learner is asked to produce, so a row whose
    only difference is an extra accepted spelling is still a free copy.
    """
    client, vid = _client(
        tmp_path, past="aceitado", short="aceitado", short_variants=("aceite",)
    )
    try:
        assert _participle_persons(client, vid) == [INVARIABLE_PERSON]
    finally:
        app.dependency_overrides.clear()


def test_lone_participle_row_loses_its_auxiliary_label(tmp_path):
    """"ter / haver" is only true as a contrast with a visible "ser / estar".

    ``partido`` is what you use with either auxiliary, so labelling the one
    surviving row "ter / haver" would assert a restriction the verb does not
    have. The row falls back to the tense heading, as the gerund does.
    """
    client, vid = _client(tmp_path, past="partido", short="partido")
    try:
        assert _participle_rows(client, vid) == [(INVARIABLE_PERSON, "")]
    finally:
        app.dependency_overrides.clear()


def test_both_rows_keep_their_labels_when_both_show(tmp_path):
    """With the contrast visible, the auxiliaries are the point of the rows."""
    client, vid = _client(tmp_path, past="aceitado", short="aceite")
    try:
        assert _participle_rows(client, vid) == [
            (INVARIABLE_PERSON, "ter / haver"),
            (SHORT_PERSON, "ser / estar"),
        ]
    finally:
        app.dependency_overrides.clear()
