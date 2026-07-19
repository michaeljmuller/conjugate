"""JSON API for verbs, drill forms, attempts and progress."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from .auth import current_user
from .conjugation import (
    DRILL_PERSONS,
    TENSE_KEYS,
    person_label,
    resolve_tense_prefs,
)
from .db import get_db
from .grading import grade
from .models import Attempt, Form, User, UserSettings, Verb

router = APIRouter(prefix="/api")


def _load_settings(db: Session, user: User) -> dict:
    """The user's raw settings blob, or ``{}`` if they've never saved any."""
    row = db.get(UserSettings, user.id)
    return dict(row.data) if row else {}


# Interface prefs and their defaults. ``labels`` chooses English vs European
# Portuguese for tense/mood names; ``show_accents`` reveals the accent-button bar.
_DEFAULT_INTERFACE = {"labels": "en", "show_accents": False}
_LABEL_LANGS = ("en", "pt")


def _resolve_interface(settings: dict) -> dict:
    """Merge the saved interface blob over defaults, ignoring unknown keys."""
    saved = settings.get("interface", {})
    return {
        "labels": saved.get("labels") if saved.get("labels") in _LABEL_LANGS else _DEFAULT_INTERFACE["labels"],
        "show_accents": bool(saved.get("show_accents", _DEFAULT_INTERFACE["show_accents"])),
    }


def _enabled_tenses(db: Session, user: User) -> list[dict]:
    """Tenses to drill, in the user's chosen order (enabled only)."""
    prefs = resolve_tense_prefs(_load_settings(db, user).get("tenses", []))
    return [t for t in prefs if t["enabled"]]


class MeOut(BaseModel):
    id: int
    email: str
    name: str | None


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user)) -> MeOut:
    return MeOut(id=user.id, email=user.email, name=user.name)


class TensePref(BaseModel):
    key: str
    enabled: bool


class InterfaceIn(BaseModel):
    labels: str | None = None
    show_accents: bool | None = None


class SettingsIn(BaseModel):
    # Both optional so the tense panel and the interface panel can each save
    # their own slice without clobbering the other.
    tenses: list[TensePref] | None = None
    interface: InterfaceIn | None = None


def _settings_response(settings: dict) -> dict:
    return {
        "tenses": resolve_tense_prefs(settings.get("tenses", [])),
        "interface": _resolve_interface(settings),
    }


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Full, reconciled settings for the UI (every catalog tense, flagged)."""
    return _settings_response(_load_settings(db, user))


@router.put("/settings")
def put_settings(
    payload: SettingsIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    updates: dict = {}
    if payload.tenses is not None:
        unknown = [t.key for t in payload.tenses if t.key not in TENSE_KEYS]
        if unknown:
            raise HTTPException(status_code=400, detail=f"unknown tenses: {unknown}")
        if not any(t.enabled for t in payload.tenses):
            raise HTTPException(status_code=400, detail="enable at least one tense")
        updates["tenses"] = [{"key": t.key, "enabled": t.enabled} for t in payload.tenses]

    if payload.interface is not None:
        if payload.interface.labels is not None and payload.interface.labels not in _LABEL_LANGS:
            raise HTTPException(status_code=400, detail="labels must be 'en' or 'pt'")
        row_iface = _load_settings(db, user).get("interface", {})
        iface = {**row_iface}
        if payload.interface.labels is not None:
            iface["labels"] = payload.interface.labels
        if payload.interface.show_accents is not None:
            iface["show_accents"] = payload.interface.show_accents
        updates["interface"] = iface

    row = db.get(UserSettings, user.id)
    if row is None:
        row = UserSettings(user_id=user.id, data={})
        db.add(row)
    # Reassign a new dict so SQLAlchemy detects the change on the JSON column.
    row.data = {**row.data, **updates}
    db.commit()
    return _settings_response(dict(row.data))


@router.get("/verbs")
def list_verbs(db: Session = Depends(get_db), user: User = Depends(current_user)):
    verbs = db.scalars(select(Verb).order_by(Verb.infinitive)).all()
    return [
        {"id": v.id, "infinitive": v.infinitive, "translation": v.translation}
        for v in verbs
    ]


@router.get("/verbs/{verb_id}/forms")
def verb_forms(
    verb_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    """Forms for a verb, grouped by tense in drill order (skips ``vos``)."""
    verb = db.get(Verb, verb_id)
    if verb is None:
        raise HTTPException(status_code=404, detail="verb not found")

    by_key: dict[tuple[str, str], Form] = {
        (f.tense, f.person): f for f in verb.forms
    }
    blocks = []
    for tense in _enabled_tenses(db, user):
        rows = []
        for person in DRILL_PERSONS:
            form = by_key.get((tense["key"], person))
            if form is None:
                continue
            rows.append(
                {
                    "form_id": form.id,
                    "person": person,
                    "label": person_label(tense["key"], person),
                    # Answer travels to the client only to power the "Reveal"
                    # button (no attempt recorded). Acceptable for a personal
                    # practice tool; typed checks still go through /api/attempts.
                    "answer": form.form_text,
                    "example_en": form.example_en,
                    # pt-PT sentence contains the answer, so the client reveals it
                    # only after the form has been answered.
                    "example_pt": form.example_pt,
                }
            )
        if not rows:
            # Tense not yet seeded for this verb (e.g. an unfilled placeholder):
            # omit it entirely rather than render a bare heading with no inputs.
            continue
        blocks.append(
            {
                "tense": tense["key"],
                "label": tense["label"],
                "mood": tense["mood"],
                "label_pt": tense["label_pt"],
                "mood_pt": tense["mood_pt"],
                "rows": rows,
            }
        )
    return {
        "id": verb.id,
        "infinitive": verb.infinitive,
        "translation": verb.translation,
        "blocks": blocks,
    }


class AttemptIn(BaseModel):
    form_id: int
    submitted_text: str


@router.post("/attempts")
def submit_attempt(
    payload: AttemptIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if not payload.submitted_text.strip():
        raise HTTPException(status_code=400, detail="empty submission")
    form = db.get(Form, payload.form_id)
    if form is None:
        raise HTTPException(status_code=404, detail="form not found")

    result = grade(payload.submitted_text, form.form_text)
    attempt = Attempt(
        user_id=user.id,
        form_id=form.id,
        submitted_text=payload.submitted_text,
        is_correct=result.is_correct,
        verdict=result.verdict,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return {
        "attempt_id": attempt.id,
        "is_correct": result.is_correct,
        "verdict": result.verdict,
        "correct_answer": result.correct_answer,
    }


class VerdictUpdate(BaseModel):
    verdict: str  # "wrong" | "typo"


@router.post("/attempts/{attempt_id}/verdict")
def reclassify_attempt(
    attempt_id: int,
    payload: VerdictUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Let the user reclassify one of their own wrong attempts as a typo (or back).
    Never changes ``is_correct`` — a typo still wasn't the right answer; it only
    tags the attempt for later stats."""
    if payload.verdict not in ("wrong", "typo"):
        raise HTTPException(status_code=400, detail="verdict must be wrong or typo")
    attempt = db.get(Attempt, attempt_id)
    if attempt is None or attempt.user_id != user.id:
        raise HTTPException(status_code=404, detail="attempt not found")
    if attempt.is_correct:
        raise HTTPException(status_code=400, detail="cannot reclassify a correct attempt")
    attempt.verdict = payload.verdict
    db.commit()
    return {"ok": True, "verdict": attempt.verdict}


@router.get("/progress")
def progress(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Per-user accuracy rolled up by tense."""
    rows = db.execute(
        select(
            Form.tense,
            func.count(Attempt.id),
            func.sum(func.cast(Attempt.is_correct, Integer)),
        )
        .join(Form, Form.id == Attempt.form_id)
        .where(Attempt.user_id == user.id)
        .group_by(Form.tense)
    ).all()

    by_tense = {
        tense: {"attempts": int(total), "correct": int(correct or 0)}
        for tense, total, correct in rows
    }
    out = []
    for tense in _enabled_tenses(db, user):
        stat = by_tense.get(tense["key"], {"attempts": 0, "correct": 0})
        out.append(
            {
                "tense": tense["key"],
                "label": tense["label"],
                "mood": tense["mood"],
                "label_pt": tense["label_pt"],
                "mood_pt": tense["mood_pt"],
                "attempts": stat["attempts"],
                "correct": stat["correct"],
            }
        )
    total = sum(s["attempts"] for s in by_tense.values())
    correct = sum(s["correct"] for s in by_tense.values())
    return {"by_tense": out, "total_attempts": total, "total_correct": correct}
