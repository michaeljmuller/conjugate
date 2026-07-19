"""Google OAuth (OIDC) login with a session cookie.

Multi-user: each Google account maps to a ``users`` row. A ``DEV_LOGIN=1`` escape
hatch (off by default, never enable in prod) signs in a fixed local account so the
app can be exercised without real Google credentials.
"""

from __future__ import annotations

import os

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.status import HTTP_401_UNAUTHORIZED

from .db import get_db
from .models import User

DEV_LOGIN = os.environ.get("DEV_LOGIN") == "1"
# Optional comma-separated allowlist of emails; empty = allow any Google account.
ALLOWED_EMAILS = {
    e.strip().lower() for e in os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip()
}

oauth = OAuth()
if os.environ.get("GOOGLE_CLIENT_ID"):
    oauth.register(
        name="google",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        client_kwargs={"scope": "openid email profile"},
    )

router = APIRouter()


def _upsert_user(db: Session, *, sub: str, email: str, name: str | None) -> User:
    user = db.scalar(select(User).where(User.google_sub == sub))
    if user is None:
        user = User(google_sub=sub, email=email, name=name)
        db.add(user)
    else:
        user.email = email
        user.name = name
    db.commit()
    db.refresh(user)
    return user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency: resolve the signed-in user or 401."""
    uid = request.session.get("uid")
    if uid is None:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="not signed in")
    user = db.get(User, uid)
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="unknown user")
    return user


@router.get("/auth/login")
async def login(request: Request, db: Session = Depends(get_db)):
    if DEV_LOGIN:
        user = _upsert_user(
            db, sub="dev|local", email="dev@localhost", name="Dev User"
        )
        request.session["uid"] = user.id
        return RedirectResponse(url="/", status_code=303)
    if "google" not in oauth._clients:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    info = token.get("userinfo") or {}
    email = (info.get("email") or "").lower()
    if ALLOWED_EMAILS and email not in ALLOWED_EMAILS:
        raise HTTPException(status_code=403, detail="account not allowed")
    user = _upsert_user(
        db, sub=info["sub"], email=email, name=info.get("name")
    )
    request.session["uid"] = user.id
    return RedirectResponse(url="/", status_code=303)


@router.post("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}
