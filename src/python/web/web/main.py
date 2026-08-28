"""FastAPI application: API + OAuth + static SPA."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import api, auth, export_api
from .db import SessionLocal, engine
from .seed import init_db, seed_examples, seed_verbs

STATIC_DIR = Path(__file__).parent / "static"

# Written by the Dockerfile's version stage: the short commit hash on the first
# line, the commit's ISO timestamp on the second. An absolute path because it is
# stamped next to the WORKDIR rather than into the installed package.
VERSION_FILE = Path("/app/VERSION")


def read_version(path: Path = VERSION_FILE) -> dict:
    """``{"version", "committed"}`` for the running image.

    Falls back to ``dev`` whenever the file is missing, short or unreadable —
    running outside a container looks exactly like that, and so does a build that
    somehow skipped the stamp. Never raises: this feeds /healthz, and a health
    check that fails because it cannot name itself is worse than one that says
    "dev".
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    version = (lines[0].strip() if lines else "") or "dev"
    committed = lines[1].strip() if len(lines) > 1 else ""
    return {"version": version, "committed": committed}


VERSION = read_version()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(engine)
    with SessionLocal() as db:
        seed_verbs(db)
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
app.include_router(export_api.router)


@app.get("/healthz")
def healthz():
    """Liveness, and which commit is answering.

    Unauthenticated on purpose: "what is deployed right now" is a question you
    want answerable by curl, without a browser and without signing in.
    """
    return {"status": "ok", **VERSION}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


# Static assets (JS/CSS). Mounted last so it doesn't shadow API routes.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
