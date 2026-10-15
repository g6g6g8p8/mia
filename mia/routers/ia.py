from fastapi import APIRouter, HTTPException
from typing import Annotated

from mia.app import Owner, audit
from mia import access, backup_jobs, connection, harness, installation_settings, organization, personalization
from mia.db import transaction, connect
from mia import __version__

router = APIRouter()


@router.get('/api/ai/config')
def ai_config(owner: Annotated[dict, Owner]) -> dict:
    return harness.config()


@router.get('/api/access/config')
def access_config(owner: Annotated[dict, Owner]) -> dict:
    return {**access.load(), 'secure_cookie': os.environ.get('MIA_COOKIE_SECURE', 'false').lower() == 'true'}


@router.get('/api/backups')
def backup_status(owner: Annotated[dict, Owner]) -> dict:
    return backup_jobs.status()


@router.put('/api/backups')
def configure_backups(payload: backup_jobs.Policy, owner: Annotated[dict, Owner]) -> dict:
    return backup_jobs.configure(payload)


@router.post('/api/backups')
def create_backup(owner: Annotated[dict, Owner]) -> dict:
    try:
        backup_jobs.run(force=True)
    except Exception:
        raise HTTPException(503, 'Backup não concluído. Confira o estado em Sistema → Backups.')
    return backup_jobs.status()


@router.get('/api/backups/{name}')
def download_backup(name: str, owner: Annotated[dict, Owner]):
    from starlette.background import BackgroundTask
    try:
        file = backup_jobs.open_snapshot(name)
    except FileNotFoundError:
        raise HTTPException(404, 'Backup não encontrado')
    def chunks():
        while block := file.read(65536):
            yield block
    from fastapi.responses import StreamingResponse
    return StreamingResponse(chunks(), media_type='application/octet-stream', headers={'Content-Disposition':f'attachment; filename="{name}"','Cache-Control':'no-store'})


@router.put('/api/access/config')
def save_access_config(payload: access.AccessSettings, owner: Annotated[dict, Owner]) -> dict:
    access.save(payload)
    return access_config(owner)


@router.get("/api/ai/context")
def ai_context(area_id: str, owner: Annotated[dict, Owner], q: str = '', include_personal_context: bool = False) -> list[dict]:
    return harness.context(owner, area_id, q, include_personal_context)


@router.put("/api/ai/config")
def save_ai_config(payload: installation_settings.AISettings, owner: Annotated[dict, Owner]) -> dict:
    with transaction(immediate=True) as db:
        if db.execute("SELECT 1 FROM runs WHERE state='running'").fetchone():
            raise HTTPException(409, "Aguarde a execução antes de alterar a configuração")
        installation_settings.save(payload)
        audit(db, owner["id"], "ai.config.updated")
    return harness.config()


@router.post('/api/ai/connection')
async def check_ai_connection(payload: connection.Destination, owner: Annotated[dict, Owner]) -> dict:
    return await connection.check(payload)


@router.get("/api/runs")
def runs(owner: Annotated[dict, Owner]) -> list[dict]:
    return harness.list_runs(owner)


@router.post('/api/organization/preview')
def organization_preview(payload: organization.SourceSelection, owner: Annotated[dict, Owner]) -> list[dict]:
    return organization.preview(payload,owner)


@router.get('/api/personalization')
def personal_context(owner: Annotated[dict, Owner]) -> dict:
    return personalization.get_state(owner)


@router.put('/api/personalization')
def edit_personal_context(payload: personalization.ContextEdit, owner: Annotated[dict, Owner]) -> dict:
    return personalization.edit_context(payload,owner,audit)


@router.post('/api/runs/{run_id}/personalization/approve')
def approve_personalization(run_id: str, payload: personalization.PersonalizationPlan, owner: Annotated[dict, Owner]) -> dict:
    personalization.approve(run_id,payload,owner,audit)
    return harness.get_run(run_id,owner)


@router.post('/api/runs/{run_id}/organization/approve')
def approve_organization(run_id: str, payload: organization.OrganizationPlan, owner: Annotated[dict, Owner]) -> dict:
    organization.approve(run_id,payload,owner,audit)
    return harness.get_run(run_id,owner)


@router.post("/api/runs")
async def start_run(payload: harness.RunInput, owner: Annotated[dict, Owner]) -> dict:
    return await harness.execute(payload, owner, __import__('mia').app.TaskInput)


@router.post('/api/runs/{run_id}/approve')
def approve_run(run_id: str, owner: Annotated[dict, Owner]) -> dict:
    return harness.decide(run_id, owner, True, audit)


@router.post('/api/runs/{run_id}/reject')
def reject_run(run_id: str, owner: Annotated[dict, Owner]) -> dict:
    return harness.decide(run_id, owner, False, audit)
