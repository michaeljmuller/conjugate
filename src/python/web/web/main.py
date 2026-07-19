"""FastAPI application: API + OAuth + static SPA."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import api, auth
from .db import SessionLocal, engine
from .seed import init_db, seed_examples, seed_verbs

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(engine)
    with SessionLocal() as db:
        seed_verbs(db)
        seed_examples(db)
    yield


app = FastAPI(title="Conjugation Practice", lifespan=lifespan)

# Signed session cookie holds only the user id. Secret must be set in prod.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "dev-insecure-change-me"),
    https_only=os.environ.get("SESSION_HTTPS_ONLY", "1") == "1",
    same_site="lax",
)

app.include_router(auth.router)
app.include_router(api.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


# Static assets (JS/CSS). Mounted last so it doesn't shadow API routes.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
