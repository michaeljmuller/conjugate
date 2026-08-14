"""JSON API for verbs, drill forms, attempts and progress."""

from __future__ import annotations

import asyncio
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from . import jobs, llm
from .auth import current_user
from .db import get_db
from .languages import DEFAULT_LANGUAGE, get_adapter, languages
from .grading import grade
from .models import Attempt, Form, User, UserSettings, Verb

router = APIRouter(prefix="/api")


def _load_settings(db: Session, user: User) -> dict:
    """The user's raw settings blob, or ``{}`` if they've never saved any."""
    row = db.get(UserSettings, user.id)
    return dict(row.data) if row else {}


def _language(settings: dict) -> str:
    """Which language the user is drilling. Unknown codes fall back to the
    default rather than 404-ing a drill that used to work."""
    code = settings.get("language")
    return code if code in languages() else DEFAULT_LANGUAGE


def _saved_tenses(settings: dict, language: str) -> list[dict]:
    """The user's saved tense order for one language.

    ``tenses`` was a bare list before there was more than one language; such a
    list is that language's, and belongs to the default one.
    """
    saved = settings.get("tenses", {})
    if isinstance(saved, list):
        return saved if language == DEFAULT_LANGUAGE else []
    return saved.get(language, [])


# Interface prefs and their defaults. ``labels`` chooses English vs the drilled
# language's own tense/mood names; ``show_accents`` reveals the accent-button bar.
_DEFAULT_INTERFACE = {"labels": "en", "show_accents": False}
_LABEL_LANGS = ("en", "native")

# What "native" was called when Portuguese was the only language it could mean.
_LEGACY_LABEL_LANGS = {"pt": "native"}


def _resolve_interface(settings: dict) -> dict:
    """Merge the saved interface blob over defaults, ignoring unknown keys."""
    saved = settings.get("interface", {})
    labels = _LEGACY_LABEL_LANGS.get(saved.get("labels"), saved.get("labels"))
    return {
        "labels": labels if labels in _LABEL_LANGS else _DEFAULT_INTERFACE["labels"],
        "show_accents": bool(saved.get("show_accents", _DEFAULT_INTERFACE["show_accents"])),
    }


def _drilling(db: Session, user: User):
    """``(settings, adapter)`` for the language this user is drilling."""
    settings = _load_settings(db, user)
    return settings, get_adapter(_language(settings))


def _enabled_tenses(settings: dict, adapter) -> list[dict]:
    """Tenses to drill, in the user's chosen order (enabled only)."""
    prefs = adapter.resolve_tense_prefs(_saved_tenses(settings, adapter.code))
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
    # All optional so the tense panel, the interface panel and the language
    # picker can each save their own slice without clobbering the others.
    language: str | None = None
    tenses: list[TensePref] | None = None
    interface: InterfaceIn | None = None


def _settings_response(settings: dict, adapter) -> dict:
    """Settings for the UI. ``tenses`` is the drilled language's catalogue,
    already reconciled, so the client never sees the per-language blob."""
    return {
        "language": adapter.code,
        "language_name": adapter.name,
        # Every registered language, so the picker needs no second request.
        "languages": [
            {"code": c, "name": get_adapter(c).name} for c in languages()
        ],
        # The accent bar's buttons: which letters are hard to type depends on
        # the language, so the client is told rather than knowing.
        "accents": adapter.accents,
        "tenses": adapter.resolve_tense_prefs(_saved_tenses(settings, adapter.code)),
        "interface": _resolve_interface(settings),
    }


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Full, reconciled settings for the UI (every catalog tense, flagged)."""
    settings, adapter = _drilling(db, user)
    return _settings_response(settings, adapter)


@router.put("/settings")
def put_settings(
    payload: SettingsIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    settings = _load_settings(db, user)
    updates: dict = {}

    # Applied first, so tenses in the same request are validated against the
    # catalogue they are being saved for.
    if payload.language is not None:
        if payload.language not in languages():
            raise HTTPException(status_code=400, detail=f"unknown language: {payload.language}")
        updates["language"] = payload.language
    adapter = get_adapter(_language({**settings, **updates}))

    if payload.tenses is not None:
        unknown = [t.key for t in payload.tenses if t.key not in adapter.tense_keys]
        if unknown:
            raise HTTPException(status_code=400, detail=f"unknown tenses: {unknown}")
        if not any(t.enabled for t in payload.tenses):
            raise HTTPException(status_code=400, detail="enable at least one tense")
        # Per language: saving Portuguese's order must not disturb Italian's.
        saved = settings.get("tenses", {})
        by_language = {DEFAULT_LANGUAGE: saved} if isinstance(saved, list) else dict(saved)
        by_language[adapter.code] = [
            {"key": t.key, "enabled": t.enabled} for t in payload.tenses
        ]
        updates["tenses"] = by_language

    if payload.interface is not None:
        if payload.interface.labels is not None and payload.interface.labels not in _LABEL_LANGS:
            raise HTTPException(status_code=400, detail="labels must be 'en' or 'native'")
        iface = {**settings.get("interface", {})}
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
    return _settings_response(dict(row.data), adapter)


@router.get("/verbs")
def list_verbs(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The drilled language's verbs. Another language's are a different list."""
    _, adapter = _drilling(db, user)
    verbs = db.scalars(
        select(Verb).where(Verb.language == adapter.code).order_by(Verb.infinitive)
    ).all()
    return [
        {"id": v.id, "infinitive": v.infinitive, "translation": v.translation}
        for v in verbs
    ]


# A single word of letters — accented ones included, digits and punctuation not.
# Keeps junk out of the lookup URL; the site itself decides what's really a verb.
_INFINITIVE_RE = re.compile(r"^[^\W\d_]{2,32}$", re.UNICODE)

# How long the SSE stream waits before sending a comment to keep the connection
# (and any proxy in front of it) from timing out on a slow model call.
_SSE_KEEPALIVE_SECONDS = 15


class AddVerbIn(BaseModel):
    infinitive: str
    # Answers yes to a job that stopped to confirm, skipping the second ask.
    force: bool = False


@router.post("/verbs", status_code=202)
async def add_verb(
    payload: AddVerbIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Start a background job that looks a verb up, writes its example sentences
    and saves it. Returns immediately with the job to follow.

    Async because it schedules an asyncio task — a sync endpoint would run in a
    worker thread with no running loop to schedule onto.
    """
    _, adapter = _drilling(db, user)
    infinitive = jobs.normalize_infinitive(payload.infinitive)
    if not _INFINITIVE_RE.match(infinitive):
        raise HTTPException(status_code=400, detail="enter a single verb, letters only")
    if jobs.verb_exists(db, infinitive, adapter.code):
        raise HTTPException(status_code=409, detail=f'"{infinitive}" is already in the list')
    if not llm.is_configured():
        # A verb without example sentences isn't worth adding, so say so now
        # rather than after a lookup that's about to be thrown away. A key that
        # exists but is rejected or out of credit fails later, in the job.
        raise HTTPException(
            status_code=503,
            detail="Adding a verb needs ANTHROPIC_API_KEY, which is not set on the server.",
        )
    return jobs.start(infinitive, user.id, adapter.code, force=payload.force).as_dict()


@router.get("/verbs/jobs/{job_id}")
def get_verb_job(job_id: str, user: User = Depends(current_user)):
    """Current job state. Polling fallback for clients without EventSource, and
    the way a reconnecting page catches up."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.as_dict()


@router.get("/verbs/jobs/{job_id}/stream")
async def stream_verb_job(job_id: str, user: User = Depends(current_user)):
    """Server-sent events: the job's full state on every change, then close."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    async def events():
        seen = -1
        while True:
            if job.version != seen:
                seen = job.version
                yield f"data: {json.dumps(job.as_dict())}\n\n"
            if job.status != jobs.RUNNING:
                return
            try:
                await asyncio.wait_for(
                    job.wait_for_change(seen), timeout=_SSE_KEEPALIVE_SECONDS
                )
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Tell any buffering reverse proxy to pass this straight through.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/verbs/{verb_id}/forms")
def verb_forms(
    verb_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    """Forms for a verb, grouped by tense in drill order (skips ``vos``)."""
    verb = db.get(Verb, verb_id)
    if verb is None:
        raise HTTPException(status_code=404, detail="verb not found")

    # The verb's own language, not the one being drilled: a verb is rendered
    # with the person rows and labels of the language it belongs to.
    settings = _load_settings(db, user)
    adapter = get_adapter(verb.language)
    by_key: dict[tuple[str, str], Form] = {
        (f.tense, f.person): f for f in verb.forms
    }
    blocks = []
    for tense in _enabled_tenses(settings, adapter):
        rows = []
        for person in adapter.drill_persons:
            form = by_key.get((tense["key"], person))
            if form is None:
                continue
            rows.append(
                {
                    "form_id": form.id,
                    "person": person,
                    "label": adapter.person_label(tense["key"], person),
                    # The client grades locally and synchronously so focus can
                    # move without waiting on the network, so it needs both the
                    # answer and every other form that counts as correct.
                    # Attempts are still recorded via /api/attempts, which
                    # re-grades against the same list.
                    "answer": form.form_text,
                    "variants": [v.text for v in form.variants],
                    "example_en": form.example_en,
                    # The native-language sentence contains the answer, so the
                    # client reveals it only after the form has been answered.
                    "example_native": form.example_pt,
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
                "label_native": tense["label_native"],
                "mood_native": tense["mood_native"],
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

    result = grade(payload.submitted_text, form.form_text, [v.text for v in form.variants])
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
    """Per-user accuracy rolled up by tense, for the drilled language.

    Scoped by language because tense keys are not globally unique — two
    languages can both have a ``present_indicative`` meaning different things,
    and rolling them into one row would be meaningless.
    """
    settings, adapter = _drilling(db, user)
    rows = db.execute(
        select(
            Form.tense,
            func.count(Attempt.id),
            func.sum(func.cast(Attempt.is_correct, Integer)),
        )
        .join(Form, Form.id == Attempt.form_id)
        .join(Verb, Verb.id == Form.verb_id)
        .where(Attempt.user_id == user.id, Verb.language == adapter.code)
        .group_by(Form.tense)
    ).all()

    by_tense = {
        tense: {"attempts": int(total), "correct": int(correct or 0)}
        for tense, total, correct in rows
    }
    out = []
    for tense in _enabled_tenses(settings, adapter):
        stat = by_tense.get(tense["key"], {"attempts": 0, "correct": 0})
        out.append(
            {
                "tense": tense["key"],
                "label": tense["label"],
                "mood": tense["mood"],
                "label_native": tense["label_native"],
                "mood_native": tense["mood_native"],
                "attempts": stat["attempts"],
                "correct": stat["correct"],
            }
        )
    total = sum(s["attempts"] for s in by_tense.values())
    correct = sum(s["correct"] for s in by_tense.values())
    return {"by_tense": out, "total_attempts": total, "total_correct": correct}
