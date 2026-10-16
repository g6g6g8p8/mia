from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Annotated
from fastapi import Cookie, Depends, HTTPException, Request, Response
from .db import connect
from .security import iso, session_hash


ROOT = Path(__file__).resolve().parent


STATIC = ROOT / "static"


COOKIE_NAME = "mia_session"


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


EXPORT_LOCK = threading.Lock()


def owner_exists() -> bool:
    with connect() as db:
        return db.execute("SELECT 1 FROM owner WHERE id = 1").fetchone() is not None


def audit(db: sqlite3.Connection, owner_id: int | None, event: str, entity_type: str | None = None, entity_id: str | None = None, metadata: dict | None = None) -> None:
    db.execute(
        "INSERT INTO audit_events(id, owner_id, event, entity_type, entity_id, metadata_json, created_at) VALUES(?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), owner_id, event, entity_type, entity_id, json.dumps(metadata or {}, ensure_ascii=False), iso()),
    )


def client_identity(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return host[:128]


def require_same_origin(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if not origin:
        return
    expected = str(request.base_url).rstrip("/")
    if origin.rstrip("/") != expected:
        raise HTTPException(403, "Origem não autorizada")


def current_owner(
    request: Request,
    mia_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> dict:
    require_same_origin(request)
    if not mia_session:
        raise HTTPException(401, "Entre para continuar")
    token_hash = session_hash(mia_session)
    current = iso()
    with connect() as db:
        row = db.execute(
            """
            SELECT owner.id, owner.name, owner.email, owner.timezone
            FROM sessions JOIN owner ON owner.id = sessions.owner_id
            WHERE sessions.token_hash = ? AND sessions.expires_at > ?
            """,
            (token_hash, current),
        ).fetchone()
        if not row:
            raise HTTPException(401, "Sessão inválida ou expirada")
        db.execute("UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?", (current, token_hash))
        return dict(row)


Owner = Annotated[dict, Depends(current_owner)]


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=30 * 24 * 60 * 60,
        httponly=True,
        secure=os.environ.get("MIA_COOKIE_SECURE", "false").lower() == "true",
        samesite="strict",
        path="/",
    )
