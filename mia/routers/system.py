from __future__ import annotations

import json
import os
import zipfile
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.responses import JSONResponse
from .. import __version__
from .. import identity
from ..db import connect, database_path, transaction
from ..security import iso
from .. import harness
from .. import personalization, access, backup_jobs, operations, experience

from ..http_dependencies import EXPORT_LOCK, Owner, STATIC, audit

from ..http_schemas import OnboardingInput


router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"ok": True, "version": __version__, "database": database_path().name}


@router.get('/api/installation')
def installation_info(request: Request) -> JSONResponse:
    return JSONResponse({'version':__version__, **identity.public_info(), **experience.location(address=str(request.base_url).rstrip('/'))}, headers={'Cache-Control':'no-store'})


@router.get('/api/experience')
def experience_state(request: Request, owner: Owner) -> JSONResponse:
    return JSONResponse(experience.overview(owner,str(request.base_url).rstrip('/')), headers={'Cache-Control':'no-store'})


@router.put('/api/focus')
def confirm_focus(payload: experience.FocusInput, owner: Owner) -> dict:
    return experience.save_focus(payload,owner,audit)


@router.put('/api/location')
def confirm_location(payload: experience.LocationInput, request: Request, owner: Owner) -> dict:
    return experience.save_location(payload,owner,audit,str(request.base_url).rstrip('/'))


@router.get("/api/export")
def export_data(owner: Owner) -> StreamingResponse:
    # Build one coherent archive on an unlinked private temporary file. The
    # library can be larger than RAM; only one row/excerpt is encoded at a time.
    from contextlib import closing
    from starlette.background import BackgroundTask
    import shutil
    import tempfile
    if not EXPORT_LOCK.acquire(blocking=False):
        raise HTTPException(409, 'Uma exportação está em andamento. Aguarde a conclusão.')
    file = None
    released = False
    def cleanup():
        nonlocal released
        if not released:
            released = True
            if file is not None:
                file.close()
            EXPORT_LOCK.release()
    try:
        with closing(connect()) as db:
            db.execute('BEGIN')
            estimated = db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0]
            if shutil.disk_usage(tempfile.gettempdir()).free < estimated + 64 * 1024 * 1024:
                raise HTTPException(507, 'Espaço temporário insuficiente para exportar com segurança. Libere espaço e tente novamente.')
            file = tempfile.TemporaryFile(mode='w+b')
            encoder = json.JSONEncoder(ensure_ascii=False, separators=(',', ':'))
            def rows(query):
                return (dict(row) for row in db.execute(query, (owner['id'],)))
            arrays = {
                'areas':rows('SELECT * FROM areas WHERE owner_id=? ORDER BY name'),
                'tasks':rows('SELECT * FROM tasks WHERE owner_id=? ORDER BY created_at'),
                'runs':(harness.public_run(row) for row in db.execute('SELECT * FROM runs WHERE owner_id=? ORDER BY created_at', (owner['id'],))),
                'documents':rows('SELECT * FROM documents WHERE owner_id=? ORDER BY created_at'),
                'conversations':rows('SELECT * FROM conversations WHERE owner_id=? ORDER BY created_at'),
                'migration_provenance':rows('SELECT p.* FROM migration_provenance p JOIN documents d ON d.id=p.document_id WHERE d.owner_id=? ORDER BY p.document_id,p.import_id'),
            }
            profile = db.execute('SELECT goal,completed FROM onboarding WHERE owner_id=?', (owner['id'],)).fetchone()
            values = {
                'format':'mia-export', 'version':1, 'exported_at':iso(),
                'owner':{key:owner[key] for key in ('name','email','timezone')},
                'onboarding':dict(profile) if profile else None,
                'personal_context':personalization.state_from_db(db,owner),
                'focus':experience.export_focus_from_db(db,owner),
            }
            with zipfile.ZipFile(file, 'w', zipfile.ZIP_DEFLATED) as archive:
                with archive.open('mia-export.json', 'w', force_zip64=True) as output:
                    def emit(value):
                        for piece in encoder.iterencode(value):
                            output.write(piece.encode('utf-8'))
                    output.write(b'{')
                    first = True
                    for key,value in values.items():
                        if not first: output.write(b',')
                        first = False
                        emit(key); output.write(b':'); emit(value)
                    for key,items in arrays.items():
                        output.write(b','); emit(key); output.write(b':[')
                        first_item = True
                        for item in items:
                            if not first_item: output.write(b',')
                            first_item = False
                            emit(item)
                        output.write(b']')
                    output.write(b'}')
                archive.writestr('README.txt', 'Mia export v1. Keep this file private.\\n')
            db.rollback()
        file.seek(0)
    except BaseException:
        cleanup()
        raise
    def chunks():
        try:
            while block := file.read(65536):
                yield block
        finally:
            cleanup()
    return StreamingResponse(chunks(), media_type='application/zip',
        headers={'Content-Disposition':'attachment; filename="mia-export.zip"', 'Cache-Control':'no-store'},
        background=BackgroundTask(cleanup))


@router.get('/api/onboarding')
def get_onboarding(owner: Owner) -> dict:
    with connect() as db:
        row=db.execute('SELECT goal,completed,step,goal_revision FROM onboarding WHERE owner_id=?',(owner['id'],)).fetchone()
    return dict(row) if row else {'goal':'','completed':False,'step':0,'goal_revision':0}


@router.put('/api/onboarding')
def save_onboarding(payload: OnboardingInput, owner: Owner) -> dict:
    with transaction(immediate=True) as db:
        current=personalization.state_from_db(db,owner)
        if payload.expected_goal_revision is not None and current['goal_revision']!=payload.expected_goal_revision and current['goal']!=payload.goal.strip():
            raise HTTPException(409,'O objetivo mudou. Reabra o onboarding antes de editar.')
        db.execute('INSERT INTO onboarding(owner_id,goal,completed,updated_at,step,goal_revision) VALUES(?,?,?,?,?,?) ON CONFLICT(owner_id) DO UPDATE SET goal=excluded.goal,goal_revision=onboarding.goal_revision+(onboarding.goal!=excluded.goal),completed=excluded.completed,updated_at=excluded.updated_at,step=excluded.step',(owner['id'],payload.goal.strip(),int(payload.completed),iso(),payload.step,int(bool(payload.goal.strip()))))
    return get_onboarding(owner)


@router.get('/api/access/config')
def access_config(owner: Owner) -> dict:
    return {**access.load(), 'secure_cookie': os.environ.get('MIA_COOKIE_SECURE', 'false').lower() == 'true'}


@router.post('/api/access/plan')
def access_plan(payload: access.AccessPlanInput, owner: Owner) -> JSONResponse:
    return JSONResponse(access.prepare(payload), headers={'Cache-Control': 'no-store'})


@router.get('/api/operations')
def operation_status(owner: Owner) -> JSONResponse:
    return JSONResponse({'app_version': __version__, **operations.public_status()}, headers={'Cache-Control': 'no-store'})


@router.get('/api/backups')
def backup_status(owner: Owner) -> dict:
    return backup_jobs.status()


@router.put('/api/backups')
def configure_backups(payload: backup_jobs.Policy, owner: Owner) -> dict:
    return backup_jobs.configure(payload)


@router.post('/api/backups')
def create_backup(owner: Owner) -> dict:
    try:
        backup_jobs.run(force=True)
    except Exception:
        raise HTTPException(503, 'Backup não concluído. Confira o estado em Sistema → Backups.')
    return backup_jobs.status()


@router.get('/api/backups/{name}')
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


@router.put('/api/access/config')
def save_access_config(payload: access.AccessSettings, owner: Owner) -> dict:
    access.save(payload)
    return access_config(owner)


@router.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
