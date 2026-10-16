from __future__ import annotations

import asyncio
from fastapi import APIRouter, HTTPException, Request
from ..db import connect
from .. import knowledge, migrations

from ..http_dependencies import Owner, audit


router = APIRouter()


@router.get('/api/migrations')
def list_migrations(owner: Owner) -> list[dict]:
    return migrations.list_jobs(owner)


@router.post('/api/migrations', status_code=201)
def create_migration(payload: migrations.CreateUpload, owner: Owner) -> dict:
    return migrations.create_upload(payload, owner)


@router.get('/api/migrations/{job}')
def get_migration(job: str, owner: Owner, offset: int = 0, limit: int = 100, q: str = '') -> dict:
    return migrations.get_job(job, owner, offset, limit, q)


@router.put('/api/migrations/{job}/upload')
@router.patch('/api/migrations/{job}/upload')
async def upload_migration(job: str, request: Request, owner: Owner, offset: int = 0) -> dict:
    # Authentication/origin checks run before accepting the stream. One chunk
    # is bounded independently of Content-Length, which clients may omit.
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > migrations.MAX_CHUNK:
            raise HTTPException(413, 'Envie blocos de no máximo 1 MiB; retome do offset recebido.')
        body.extend(chunk)
    return await asyncio.to_thread(migrations.append_upload, job, offset, bytes(body), owner)


@router.post('/api/migrations/{job}/finish')
def finish_migration(job: str, owner: Owner) -> dict:
    return migrations.finish_upload(job, owner)


@router.put('/api/migrations/{job}/selection')
def select_migration(job: str, payload: migrations.Selection, owner: Owner) -> dict:
    return migrations.save_selection(job, payload, owner)


@router.post('/api/migrations/{job}/confirm')
def confirm_migration(job: str, payload: migrations.Confirm, owner: Owner) -> dict:
    return migrations.confirm(job, payload, owner, audit)


@router.post('/api/migrations/{job}/cancel')
def cancel_migration(job: str, owner: Owner) -> dict:
    return migrations.cancel(job, owner, audit)


@router.post('/api/migrations/{job}/resume')
def resume_migration(job: str, owner: Owner) -> dict:
    return migrations.resume(job, owner)


@router.delete('/api/migrations/{job}')
def remove_migration(job: str, owner: Owner) -> dict:
    return migrations.remove(job, owner, audit)


@router.get("/api/search")
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


@router.post('/api/imports',status_code=201)
def prepare_import(payload: knowledge.ImportInput,owner: Owner) -> dict:
    return knowledge.prepare(payload,owner)


@router.get('/api/imports')
def imports(owner: Owner) -> list[dict]:
    with connect() as db:
        ids=[row[0] for row in db.execute('SELECT id FROM imports WHERE owner_id=? AND NOT EXISTS (SELECT 1 FROM migration_jobs m WHERE m.id=imports.id) ORDER BY created_at DESC',(owner['id'],))]
    return [knowledge.get_batch(batch,owner) for batch in ids]


@router.get('/api/imports/{batch}')
def get_import(batch: str,owner: Owner) -> dict:
    require_legacy_import(batch, owner)
    return knowledge.get_batch(batch,owner)


@router.post('/api/imports/{batch}/confirm')
def confirm_import(batch: str,payload: knowledge.Selection,owner: Owner) -> dict:
    require_legacy_import(batch, owner)
    return knowledge.commit(batch,payload,owner,audit)


@router.delete('/api/imports/{batch}')
def remove_import(batch: str,owner: Owner) -> dict:
    with connect() as db:
        modern = db.execute('SELECT 1 FROM migration_jobs WHERE id=? AND owner_id=?', (batch,owner['id'])).fetchone()
    if modern:
        return migrations.remove(batch, owner, audit)
    return knowledge.remove(batch,owner,audit)


def require_legacy_import(batch: str, owner: dict) -> None:
    with connect() as db:
        modern = db.execute('SELECT 1 FROM migration_jobs WHERE id=? AND owner_id=?', (batch,owner['id'])).fetchone()
    if modern:
        raise HTTPException(409, 'Esta importação usa a revisão por grupos. Consulte-a em Biblioteca ou /api/migrations.')


@router.get('/api/documents')
def documents(owner: Owner) -> list[dict]:
    with connect() as db:
        return [dict(row) for row in db.execute('SELECT id,title,path,kind,area_id,created_at,active FROM documents WHERE owner_id=? ORDER BY created_at DESC',(owner['id'],))]


@router.put('/api/documents/{doc}/state')
def set_document_state(doc: str,payload: knowledge.SourceState,owner: Owner) -> dict:
    return knowledge.set_source_state(doc,payload,owner,audit)


@router.get('/api/documents/{doc}')
def get_document(doc: str,owner: Owner) -> dict:
    return knowledge.document(doc,owner)
