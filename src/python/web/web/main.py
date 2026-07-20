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
from .seed import init_db, seed_examples, seed_verbs, strip_negative_imperative_prefix

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(engine)
    with SessionLocal() as db:
        seed_verbs(db)
        strip_negative_imperative_prefix(db)
        seed_examples(db)
    yield


# docs/openapi off by default so the public deployment doesn't advertise its whole
# API surface to scanners; set ENABLE_DOCS=1 (dev) to get the Swagger UI back.
_docs_on = os.environ.get("ENABLE_DOCS") == "1"
app = FastAPI(
    title="Conjugation Practice",
    lifespan=lifespan,
    docs_url="/docs" if _docs_on else None,
    redoc_url=None,
    openapi_url="/openapi.json" if _docs_on else None,
)

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
