"""The seed-file export endpoints, for a script rather than a browser.

Deliberately outside ``/api`` and outside the Google session: this is fetched by
whatever job refreshes the committed files, which has no browser to complete an
OAuth round trip with. HTTP Basic instead, from the environment.

    curl -u "$EXPORT_USER:$EXPORT_PASSWORD" -fo web/data/verbs_seed.json \\
        https://conjugate.example.org/export/verbs_seed.json

Off unless both variables are set, and 404 rather than 401 when off — an endpoint
that isn't configured shouldn't advertise that it exists.
"""

from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from . import export
from .db import get_db

router = APIRouter(prefix="/export")

# Read once at import, like the rest of the app's configuration.
EXPORT_USER = os.environ.get("EXPORT_USER", "")
EXPORT_PASSWORD = os.environ.get("EXPORT_PASSWORD", "")

_security = HTTPBasic(auto_error=False)


def _enabled() -> bool:
    return bool(EXPORT_USER and EXPORT_PASSWORD)


def require_export_auth(
    credentials: HTTPBasicCredentials | None = Depends(_security),
) -> None:
    """Check HTTP Basic against the configured pair, in constant time.

    Both halves are always compared even when the username is already wrong, so
    the response time says nothing about which half failed.
    """
    if not _enabled():
        raise HTTPException(status_code=404, detail="not found")
    user_ok = secrets.compare_digest(
        (credentials.username if credentials else ""), EXPORT_USER
    )
    password_ok = secrets.compare_digest(
        (credentials.password if credentials else ""), EXPORT_PASSWORD
    )
    if not (user_ok and password_ok):
        raise HTTPException(
            status_code=401,
            detail="not authorized",
            headers={"WWW-Authenticate": 'Basic realm="export"'},
        )


def _file(payload) -> Response:
    """Serve as a file body, so `curl -o` writes something committable."""
    return Response(
        content=export.as_json(payload),
        media_type="application/json",
        # No caching: the point of asking is to get what the database holds now.
        headers={"Cache-Control": "no-store"},
    )


@router.get("/verbs_seed.json", dependencies=[Depends(require_export_auth)])
def verbs_seed(db: Session = Depends(get_db)) -> Response:
    """``web/data/verbs_seed.json`` as the database would write it."""
    return _file(export.verbs_seed(db))


@router.get("/examples.json", dependencies=[Depends(require_export_auth)])
def examples(db: Session = Depends(get_db)) -> Response:
    """``web/languages/pt/examples.json``, prompt material carried across."""
    return _file(export.examples(db))
