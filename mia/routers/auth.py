from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Annotated
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from .. import __version__
from .. import bootstrap
from ..db import transaction
from ..security import hash_password, iso, new_session, now, session_hash, verify_password

from ..http_dependencies import COOKIE_NAME, Owner, audit, client_identity, owner_exists, require_same_origin, set_session_cookie

from ..http_schemas import LoginInput, SetupInput


router = APIRouter()


@router.get("/api/status")
def status() -> dict:
    return {"configured": owner_exists(), "version": __version__}


@router.post("/api/setup", status_code=201)
def setup(payload: SetupInput, request: Request, response: Response) -> dict:
    require_same_origin(request)
    owner_created = iso()
    area_id = str(uuid.uuid4())
    token, token_hash, expires_at = new_session()
    try:
        with transaction(immediate=True) as db:
            if db.execute("SELECT 1 FROM owner WHERE id = 1").fetchone():
                raise HTTPException(409, "Mia já foi configurada")
            bootstrap.require_owner_creation(request)
            db.execute(
                "INSERT INTO owner(id, name, email, timezone, password_hash, created_at) VALUES(1,?,?,?,?,?)",
                (payload.name, payload.email.strip(), payload.timezone, hash_password(payload.password), owner_created),
            )
            db.execute(
                "INSERT INTO areas(id, owner_id, name, description, color, created_at, updated_at) VALUES(?,1,?,?,?, ?, ?)",
                (area_id, payload.area_name, payload.area_description.strip(), "violet", owner_created, owner_created),
            )
            db.execute(
                "INSERT INTO sessions(token_hash, owner_id, created_at, expires_at, last_seen_at) VALUES(?,1,?,?,?)",
                (token_hash, owner_created, expires_at, owner_created),
            )
            audit(db, 1, "owner.created", "owner", "1")
            audit(db, 1, "area.created", "area", area_id)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "Mia já foi configurada ou a área já existe") from exc
    set_session_cookie(response, token)
    response.delete_cookie(bootstrap.COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/api/login")
def login(payload: LoginInput, request: Request, response: Response) -> dict:
    require_same_origin(request)
    identity = client_identity(request)
    current = now()
    with transaction(immediate=True) as db:
        attempt = db.execute("SELECT failures, blocked_until FROM login_attempts WHERE identity = ?", (identity,)).fetchone()
        if attempt and attempt["blocked_until"] and datetime.fromisoformat(attempt["blocked_until"]) > current:
            raise HTTPException(429, "Muitas tentativas. Tente novamente mais tarde.")
        owner = db.execute("SELECT id, password_hash FROM owner WHERE id = 1").fetchone()
        if not owner or not verify_password(payload.password, owner["password_hash"]):
            failures = (attempt["failures"] if attempt and not attempt["blocked_until"] else 0) + 1
            blocked_until = iso(current + timedelta(minutes=15)) if failures >= 5 else None
            db.execute(
                """
                INSERT INTO login_attempts(identity, failures, blocked_until) VALUES(?,?,?)
                ON CONFLICT(identity) DO UPDATE SET failures=excluded.failures, blocked_until=excluded.blocked_until
                """,
                (identity, failures, blocked_until),
            )
            db.commit()  # Keep the failed attempt when the error exits the transaction.
            raise HTTPException(401, "Senha incorreta")
        db.execute("DELETE FROM login_attempts WHERE identity = ?", (identity,))
        token, token_hash, expires_at = new_session()
        db.execute(
            "INSERT INTO sessions(token_hash, owner_id, created_at, expires_at, last_seen_at) VALUES(?,1,?,?,?)",
            (token_hash, iso(current), expires_at, iso(current)),
        )
        audit(db, 1, "session.created")
    set_session_cookie(response, token)
    return {"ok": True}


@router.post("/api/logout")
def logout(
    request: Request,
    response: Response,
    _: Owner,
    mia_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> dict:
    require_same_origin(request)
    if mia_session:
        with transaction() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (session_hash(mia_session),))
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/api/me")
def me(owner: Owner) -> dict:
    return owner
