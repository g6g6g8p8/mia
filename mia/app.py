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
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import __version__
from .db import connect, database_path, initialize, transaction
from .security import hash_password, iso, new_session, now, session_hash, verify_password
from . import harness
from . import settings as installation_settings
from . import connection
from . import knowledge, organization, personalization, access, backup_jobs, operations


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
    managed_root = os.environ.get('MIA_OPERATIONS_ROOT')
    if managed_root and request.method not in SAFE_METHODS:
        try:
            maintenance = (Path(managed_root) / 'journal.json').exists()
        except OSError:
            maintenance = True
        if maintenance:
            return JSONResponse({'detail': 'Atualização ou recuperação em andamento. Aguarde a conclusão no terminal antes de alterar dados.'}, status_code=503, headers={'Retry-After':'5', 'Cache-Control':'no-store'})
    if request.url.path == '/api/imports' and request.method == 'POST':
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 12_000_000:
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


class TaskReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=2, max_length=200)
    notes: str = Field(default='', max_length=10_000)
    due_date: date | None = None
    priority: int = Field(default=2, ge=1, le=3)

    @field_validator('title')
    @classmethod
    def clean_title(cls, value: str) -> str:
        return TaskInput.clean_title(value)


class TaskApproval(BaseModel):
    model_config = ConfigDict(extra='forbid')
    edits: TaskReview | None = None


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


@app.get("/api/status")
def status() -> dict:
    return {"configured": owner_exists(), "version": __version__}


@app.post("/api/setup", status_code=201)
def setup(payload: SetupInput, request: Request, response: Response) -> dict:
    require_same_origin(request)
    owner_created = iso()
    area_id = str(uuid.uuid4())
    token, token_hash, expires_at = new_session()
    try:
        with transaction(immediate=True) as db:
            if db.execute("SELECT 1 FROM owner WHERE id = 1").fetchone():
                raise HTTPException(409, "Mia já foi configurada")
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
    return {"ok": True}


@app.post("/api/login")
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


@app.post("/api/logout")
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


@app.get("/api/me")
def me(owner: Owner) -> dict:
    return owner


@app.get("/api/areas")
def list_areas(owner: Owner) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            """
            SELECT areas.*, COUNT(tasks.id) FILTER (WHERE tasks.status = 'open') AS open_tasks
            FROM areas LEFT JOIN tasks ON tasks.area_id = areas.id
            WHERE areas.owner_id = ?
            GROUP BY areas.id ORDER BY lower(areas.name)
            """,
            (owner["id"],),
        ).fetchall()
        return [dict(row) for row in rows]


@app.post("/api/areas", status_code=201)
def create_area(payload: AreaInput, owner: Owner) -> dict:
    area_id, created = str(uuid.uuid4()), iso()
    try:
        with transaction() as db:
            db.execute(
                "INSERT INTO areas(id, owner_id, name, description, color, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                (area_id, owner["id"], payload.name, payload.description.strip(), payload.color, created, created),
            )
            audit(db, owner["id"], "area.created", "area", area_id)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "Já existe uma área com esse nome") from exc
    with connect() as db:
        return dict(db.execute("SELECT * FROM areas WHERE id = ?", (area_id,)).fetchone())


@app.put('/api/areas/{area_id}')
def update_area(area_id: str, payload: AreaInput, owner: Owner) -> dict:
    with transaction(immediate=True) as db:
        if not db.execute('SELECT 1 FROM areas WHERE id=? AND owner_id=?',(area_id,owner['id'])).fetchone():
            raise HTTPException(404, 'Área não encontrada')
        names = db.execute('SELECT name FROM areas WHERE owner_id=? AND id!=?',(owner['id'],area_id))
        if any(knowledge.normalized(row[0])==knowledge.normalized(payload.name) for row in names):
            raise HTTPException(409, 'Já existe uma área com esse nome')
        db.execute('UPDATE areas SET name=?,description=?,color=?,updated_at=? WHERE id=? AND owner_id=?',(payload.name,payload.description.strip(),payload.color,iso(),area_id,owner['id']))
        audit(db,owner['id'],'area.updated','area',area_id)
        return dict(db.execute('SELECT * FROM areas WHERE id=?',(area_id,)).fetchone())


@app.get("/api/tasks")
def list_tasks(owner: Owner, status: Literal["open", "done", "all"] = "open", area_id: str | None = None) -> list[dict]:
    filters, values = ["tasks.owner_id = ?"], [owner["id"]]
    if status != "all":
        filters.append("tasks.status = ?")
        values.append(status)
    if area_id:
        filters.append("tasks.area_id = ?")
        values.append(area_id)
    with connect() as db:
        rows = db.execute(
            f"""
            SELECT tasks.*, areas.name AS area_name, areas.color AS area_color
            FROM tasks LEFT JOIN areas ON areas.id = tasks.area_id
            WHERE {' AND '.join(filters)}
            ORDER BY tasks.status, tasks.due_date IS NULL, tasks.due_date, tasks.priority DESC, tasks.created_at DESC
            """,
            values,
        ).fetchall()
        return [dict(row) for row in rows]


@app.post("/api/tasks", status_code=201)
def create_task(payload: TaskInput, owner: Owner) -> dict:
    task_id, created = str(uuid.uuid4()), iso()
    with transaction() as db:
        if payload.area_id:
            area = db.execute("SELECT 1 FROM areas WHERE id = ? AND owner_id = ?", (payload.area_id, owner["id"])).fetchone()
            if not area:
                raise HTTPException(404, "Área não encontrada")
        db.execute(
            """
            INSERT INTO tasks(id, owner_id, area_id, title, notes, due_date, priority, status, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,'open',?,?)
            """,
            (task_id, owner["id"], payload.area_id, payload.title, payload.notes.strip(), payload.due_date.isoformat() if payload.due_date else None, payload.priority, created, created),
        )
        audit(db, owner["id"], "task.created", "task", task_id)
    return get_task(task_id, owner)


def get_task(task_id: str, owner: dict) -> dict:
    with connect() as db:
        row = db.execute(
            """
            SELECT tasks.*, areas.name AS area_name, areas.color AS area_color
            FROM tasks LEFT JOIN areas ON areas.id = tasks.area_id
            WHERE tasks.id = ? AND tasks.owner_id = ?
            """,
            (task_id, owner["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Tarefa não encontrada")
        return dict(row)


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: str, payload: TaskPatch, owner: Owner) -> dict:
    updated = iso()
    with transaction() as db:
        exists = db.execute("SELECT status FROM tasks WHERE id = ? AND owner_id = ?", (task_id, owner["id"])).fetchone()
        if not exists:
            raise HTTPException(404, "Tarefa não encontrada")
        completed = updated if payload.status == "done" else None
        db.execute(
            "UPDATE tasks SET status = ?, completed_at = ?, updated_at = ? WHERE id = ? AND owner_id = ?",
            (payload.status, completed, updated, task_id, owner["id"]),
        )
        audit(db, owner["id"], f"task.{payload.status}", "task", task_id)
    return get_task(task_id, owner)


@app.get("/api/today")
def today(owner: Owner) -> dict:
    today_iso = datetime.now(ZoneInfo(owner["timezone"])).date().isoformat()
    with connect() as db:
        areas = db.execute(
            """
            SELECT areas.id, areas.name, areas.description, areas.color,
                   COUNT(tasks.id) FILTER (WHERE tasks.status = 'open') AS open_tasks
            FROM areas LEFT JOIN tasks ON tasks.area_id = areas.id
            WHERE areas.owner_id = ?
            GROUP BY areas.id ORDER BY lower(areas.name)
            """,
            (owner["id"],),
        ).fetchall()
        tasks = db.execute(
            """
            SELECT tasks.*, areas.name AS area_name, areas.color AS area_color
            FROM tasks LEFT JOIN areas ON areas.id = tasks.area_id
            WHERE tasks.owner_id = ? AND tasks.status = 'open'
            ORDER BY
              CASE WHEN tasks.due_date IS NOT NULL AND tasks.due_date < ? THEN 0
                   WHEN tasks.due_date = ? THEN 1 ELSE 2 END,
              tasks.priority DESC, tasks.due_date IS NULL, tasks.due_date, tasks.created_at
            LIMIT 12
            """,
            (owner["id"], today_iso, today_iso),
        ).fetchall()
        overdue = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE owner_id = ? AND status = 'open' AND due_date < ?",
            (owner["id"], today_iso),
        ).fetchone()[0]
        due_today = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE owner_id = ? AND status = 'open' AND due_date = ?",
            (owner["id"], today_iso),
        ).fetchone()[0]
    return {
        "date": today_iso,
        "owner": owner,
        "overdue": overdue,
        "due_today": due_today,
        "areas": [dict(row) for row in areas],
        "tasks": [dict(row) for row in tasks],
    }


@app.get("/api/search")
def search(q: str, owner: Owner) -> dict:
    query = q.strip()
    if len(query) < 2:
        return {"query": query, "results": []}
    escaped = query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    pattern = f"%{escaped}%"
    with connect() as db:
        tasks = db.execute(
            """
            SELECT tasks.id, tasks.title, tasks.notes, tasks.status, tasks.due_date,
                   areas.name AS area_name, 'task' AS type
            FROM tasks LEFT JOIN areas ON areas.id = tasks.area_id
            WHERE tasks.owner_id = ? AND (tasks.title LIKE ? ESCAPE '!' OR tasks.notes LIKE ? ESCAPE '!')
            ORDER BY tasks.updated_at DESC LIMIT 30
            """,
            (owner["id"], pattern, pattern),
        ).fetchall()
        areas = db.execute(
            """
            SELECT id, name AS title, description AS notes, NULL AS status, NULL AS due_date,
                   name AS area_name, 'area' AS type
            FROM areas
            WHERE owner_id = ? AND (name LIKE ? ESCAPE '!' OR description LIKE ? ESCAPE '!')
            ORDER BY updated_at DESC LIMIT 20
            """,
            (owner["id"], pattern, pattern),
        ).fetchall()
    documents=[{'id':r['id'],'title':r['title'],'notes':r['content'],'type':'document','area_name':None,'due_date':None} for r in knowledge.retrieve(owner,None,query,10)]
    return {"query": query, "results": [dict(row) for row in [*tasks, *areas]]+documents}


@app.get("/api/export")
def export_data(owner: Owner) -> StreamingResponse:
    with connect() as db:
        areas = [dict(row) for row in db.execute("SELECT * FROM areas WHERE owner_id = ? ORDER BY name", (owner["id"],))]
        tasks = [dict(row) for row in db.execute("SELECT * FROM tasks WHERE owner_id = ? ORDER BY created_at", (owner["id"],))]
        documents = [dict(row) for row in db.execute("SELECT * FROM documents WHERE owner_id=?",(owner['id'],))]
        profile = db.execute("SELECT goal,completed FROM onboarding WHERE owner_id=?",(owner['id'],)).fetchone()
    payload = {
        "format": "mia-export",
        "version": 1,
        "exported_at": iso(),
        "owner": {"name": owner["name"], "email": owner["email"], "timezone": owner["timezone"]},
        "areas": areas,
        "tasks": tasks,
        "runs": harness.list_runs(owner, all_runs=True),
        "documents": documents,
        "onboarding": dict(profile) if profile else None,
        "personal_context": personalization.get_state(owner),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mia-export.json", json.dumps(payload, ensure_ascii=False, indent=2))
        archive.writestr("README.txt", "Mia export v1. Keep this file private.\n")
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="mia-export.zip"'},
    )


class OnboardingInput(BaseModel):
    goal: str = Field(default='',max_length=1000)
    completed: bool = False
    step: int = Field(default=0,ge=0,le=3)
    expected_goal_revision: int | None = Field(default=None,ge=0)


@app.get('/api/onboarding')
def get_onboarding(owner: Owner) -> dict:
    with connect() as db:
        row=db.execute('SELECT goal,completed,step,goal_revision FROM onboarding WHERE owner_id=?',(owner['id'],)).fetchone()
    return dict(row) if row else {'goal':'','completed':False,'step':0,'goal_revision':0}


@app.put('/api/onboarding')
def save_onboarding(payload: OnboardingInput, owner: Owner) -> dict:
    with transaction(immediate=True) as db:
        current=personalization.state_from_db(db,owner)
        if payload.expected_goal_revision is not None and current['goal_revision']!=payload.expected_goal_revision and current['goal']!=payload.goal.strip():
            raise HTTPException(409,'O objetivo mudou. Reabra o onboarding antes de editar.')
        db.execute('INSERT INTO onboarding(owner_id,goal,completed,updated_at,step,goal_revision) VALUES(?,?,?,?,?,?) ON CONFLICT(owner_id) DO UPDATE SET goal=excluded.goal,goal_revision=onboarding.goal_revision+(onboarding.goal!=excluded.goal),completed=excluded.completed,updated_at=excluded.updated_at,step=excluded.step',(owner['id'],payload.goal.strip(),int(payload.completed),iso(),payload.step,int(bool(payload.goal.strip()))))
    return get_onboarding(owner)


@app.post('/api/imports',status_code=201)
def prepare_import(payload: knowledge.ImportInput,owner: Owner) -> dict:
    return knowledge.prepare(payload,owner)


@app.get('/api/imports')
def imports(owner: Owner) -> list[dict]:
    with connect() as db:
        ids=[row[0] for row in db.execute('SELECT id FROM imports WHERE owner_id=? ORDER BY created_at DESC',(owner['id'],))]
    return [knowledge.get_batch(batch,owner) for batch in ids]


@app.get('/api/imports/{batch}')
def get_import(batch: str,owner: Owner) -> dict:
    return knowledge.get_batch(batch,owner)


@app.post('/api/imports/{batch}/confirm')
def confirm_import(batch: str,payload: knowledge.Selection,owner: Owner) -> dict:
    return knowledge.commit(batch,payload,owner,audit)


@app.delete('/api/imports/{batch}')
def remove_import(batch: str,owner: Owner) -> dict:
    return knowledge.remove(batch,owner,audit)


@app.get('/api/documents')
def documents(owner: Owner) -> list[dict]:
    with connect() as db:
        return [dict(row) for row in db.execute('SELECT id,title,path,kind,area_id,created_at,active FROM documents WHERE owner_id=? ORDER BY created_at DESC',(owner['id'],))]


@app.put('/api/documents/{doc}/state')
def set_document_state(doc: str,payload: knowledge.SourceState,owner: Owner) -> dict:
    return knowledge.set_source_state(doc,payload,owner,audit)


@app.get('/api/documents/{doc}')
def get_document(doc: str,owner: Owner) -> dict:
    return knowledge.document(doc,owner)


@app.get("/api/ai/config")
def ai_config(owner: Owner) -> dict:
    return harness.config()


@app.get('/api/access/config')
def access_config(owner: Owner) -> dict:
    return {**access.load(), 'secure_cookie': os.environ.get('MIA_COOKIE_SECURE', 'false').lower() == 'true'}


@app.post('/api/access/plan')
def access_plan(payload: access.AccessPlanInput, owner: Owner) -> JSONResponse:
    return JSONResponse(access.prepare(payload), headers={'Cache-Control': 'no-store'})


@app.get('/api/operations')
def operation_status(owner: Owner) -> JSONResponse:
    return JSONResponse({'app_version': __version__, **operations.public_status()}, headers={'Cache-Control': 'no-store'})


@app.get('/api/backups')
def backup_status(owner: Owner) -> dict:
    return backup_jobs.status()


@app.put('/api/backups')
def configure_backups(payload: backup_jobs.Policy, owner: Owner) -> dict:
    return backup_jobs.configure(payload)


@app.post('/api/backups')
def create_backup(owner: Owner) -> dict:
    try:
        backup_jobs.run(force=True)
    except Exception:
        raise HTTPException(503, 'Backup não concluído. Confira o estado em Sistema → Backups.')
    return backup_jobs.status()


@app.get('/api/backups/{name}')
def download_backup(name: str, owner: Owner):
    from starlette.background import BackgroundTask
    try:
        file = backup_jobs.open_snapshot(name)
    except FileNotFoundError:
        raise HTTPException(404, 'Backup não encontrado')
    def chunks():
        while block := file.read(65536):
            yield block
    return StreamingResponse(chunks(), media_type='application/octet-stream', headers={'Content-Disposition':f'attachment; filename="{name}"','Cache-Control':'no-store'}, background=BackgroundTask(file.close))


@app.put('/api/access/config')
def save_access_config(payload: access.AccessSettings, owner: Owner) -> dict:
    access.save(payload)
    return access_config(owner)


@app.get("/api/ai/context")
def ai_context(area_id: str, owner: Owner, q: str = '', include_personal_context: bool = False) -> list[dict]:
    return harness.context(owner, area_id, q, include_personal_context)


@app.put("/api/ai/config")
def save_ai_config(payload: installation_settings.AISettings, owner: Owner) -> dict:
    with transaction(immediate=True) as db:
        if db.execute("SELECT 1 FROM runs WHERE state='running'").fetchone():
            raise HTTPException(409, "Aguarde a execução antes de alterar a configuração")
        installation_settings.save(payload)
        audit(db, owner["id"], "ai.config.updated")
    return harness.config()


@app.post('/api/ai/connection')
async def check_ai_connection(payload: connection.Destination, owner: Owner) -> dict:
    return await connection.check(payload)


@app.get("/api/runs")
def runs(owner: Owner) -> list[dict]:
    return harness.list_runs(owner)


@app.post('/api/organization/preview')
def organization_preview(payload: organization.SourceSelection, owner: Owner) -> list[dict]:
    return organization.preview(payload,owner)


@app.get('/api/personalization')
def personal_context(owner: Owner) -> dict:
    return personalization.get_state(owner)


@app.put('/api/personalization')
def edit_personal_context(payload: personalization.ContextEdit, owner: Owner) -> dict:
    return personalization.edit_context(payload,owner,audit)


@app.post('/api/runs/{run_id}/personalization/approve')
def approve_personalization(run_id: str, payload: personalization.PersonalizationPlan, owner: Owner) -> dict:
    personalization.approve(run_id,payload,owner,audit)
    return harness.get_run(run_id,owner)


@app.post('/api/runs/{run_id}/organization/approve')
def approve_organization(run_id: str, payload: organization.OrganizationPlan, owner: Owner) -> dict:
    organization.approve(run_id,payload,owner,audit)
    return harness.get_run(run_id,owner)


@app.post("/api/runs")
async def start_run(payload: harness.RunInput, owner: Owner) -> dict:
    return await harness.execute(payload, owner, TaskInput)


@app.post("/api/runs/{run_id}/approve")
def approve_run(run_id: str, owner: Owner, payload: TaskApproval | None = None) -> dict:
    edits = payload.edits.model_dump(mode='json') if payload and payload.edits else None
    return harness.decide(run_id, owner, True, audit, edits)


@app.post("/api/runs/{run_id}/reject")
def reject_run(run_id: str, owner: Owner) -> dict:
    return harness.decide(run_id, owner, False, audit)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

