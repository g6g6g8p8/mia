from __future__ import annotations

import io
import asyncio
import json
import os
import sqlite3
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from . import __version__
from .db import connect, database_path, initialize, transaction
from .security import hash_password, iso, new_session, now, session_hash, verify_password
from . import harness
from . import settings as installation_settings
from . import connection
from . import knowledge, organization, personalization, access, backup_jobs


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
COOKIE_NAME = "mia_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize()
    stop = asyncio.Event()
    task = asyncio.create_task(backup_jobs.worker(stop))
    try:
        yield
    finally:
        stop.set()
        await task


app = FastAPI(title="Mia", version=__version__, lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def safe_validation(request: Request, error: RequestValidationError):
    return JSONResponse({'detail':[{'loc':item['loc'],'msg':item['msg']} for item in error.errors()]},status_code=422)


@app.middleware("http")
async def limit_upload(request: Request, call_next):
    if request.url.path == '/api/imports' and request.method == 'POST':
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 12_000_000:
                from fastapi.responses import JSONResponse
                return JSONResponse({'detail':'Upload excede o limite de 8 MB (12 MB codificado)'},status_code=413)
        request._body = bytes(body)
    return await call_next(request)


class SetupInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(default="", max_length=200)
    timezone: str = Field(default="America/Sao_Paulo", min_length=3, max_length=80)
    password: str = Field(min_length=10, max_length=200)
    area_name: str = Field(min_length=2, max_length=80)
    area_description: str = Field(default="", max_length=500)

    @field_validator("name", "area_name")
    @classmethod
    def clean_required(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Campo obrigatório")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Fuso horário inválido") from exc
        return value


class LoginInput(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class AreaInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    color: Literal["slate", "violet", "blue", "green", "amber", "rose"] = "slate"

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Use pelo menos dois caracteres")
        return value


class TaskInput(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    notes: str = Field(default="", max_length=10_000)
    area_id: str | None = None
    due_date: date | None = None
    priority: int = Field(default=2, ge=1, le=3)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Use pelo menos dois caracteres")
        return value


class TaskPatch(BaseModel):
    status: Literal["open", "done"]


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


@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": __version__, "database": database_path().name}


# Routers are split into mia/routers/*.py. Import them after helpers are defined so
# router modules can import helpers from this module safely.
from .routers import auth, areas, tasks, sources, ia, system  # noqa: E402

app.include_router(auth.router)
app.include_router(areas.router)
app.include_router(tasks.router)
app.include_router(sources.router)
app.include_router(ia.router)
app.include_router(system.router)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")
