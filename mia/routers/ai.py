from __future__ import annotations

from fastapi import APIRouter, HTTPException
from ..db import transaction
from .. import harness
from .. import settings as installation_settings
from .. import connection
from .. import organization, personalization, conversations

from ..http_dependencies import Owner, audit

from ..http_schemas import TaskApproval, TaskInput


router = APIRouter()


@router.get('/api/conversations')
def list_conversations(owner: Owner) -> list[dict]:
    return conversations.listing(owner)


@router.post('/api/conversations', status_code=201)
def create_conversation(payload: conversations.ConversationCreate, owner: Owner) -> dict:
    return conversations.create(payload, owner, audit)


@router.get('/api/conversations/{thread_id}')
def get_conversation(thread_id: str, owner: Owner) -> dict:
    return conversations.detail(thread_id, owner)


@router.patch('/api/conversations/{thread_id}')
def rename_conversation(thread_id: str, payload: conversations.ConversationRename, owner: Owner) -> dict:
    return conversations.rename(thread_id, payload, owner, audit)


@router.get("/api/ai/config")
def ai_config(owner: Owner) -> dict:
    return harness.config()


@router.get("/api/ai/context")
def ai_context(owner: Owner, area_id: str | None = None, thread_id: str | None = None, q: str = '', include_personal_context: bool = False, use_confirmed_focus: bool = False) -> list[dict]:
    if thread_id:
        area_id = conversations.scope(thread_id, owner, area_id)['area_id']
    return harness.context(owner, area_id, q, include_personal_context, use_confirmed_focus)


@router.put("/api/ai/config")
def save_ai_config(payload: installation_settings.AISettings, owner: Owner) -> dict:
    with transaction(immediate=True) as db:
        if db.execute("SELECT 1 FROM runs WHERE state='running'").fetchone():
            raise HTTPException(409, "Aguarde a execução antes de alterar a configuração")
        installation_settings.save(payload)
        audit(db, owner["id"], "ai.config.updated")
    return harness.config()


@router.post('/api/ai/connection')
async def check_ai_connection(payload: connection.Destination, owner: Owner) -> dict:
    return await connection.check(payload)


@router.get("/api/runs")
def runs(owner: Owner) -> list[dict]:
    return harness.list_runs(owner)


@router.post('/api/organization/preview')
def organization_preview(payload: organization.SourceSelection, owner: Owner) -> list[dict]:
    return organization.preview(payload,owner)


@router.get('/api/personalization')
def personal_context(owner: Owner) -> dict:
    return personalization.get_state(owner)


@router.put('/api/personalization')
def edit_personal_context(payload: personalization.ContextEdit, owner: Owner) -> dict:
    return personalization.edit_context(payload,owner,audit)


@router.post('/api/runs/{run_id}/personalization/approve')
def approve_personalization(run_id: str, payload: personalization.PersonalizationPlan, owner: Owner) -> dict:
    personalization.approve(run_id,payload,owner,audit)
    return harness.get_run(run_id,owner)


@router.post('/api/runs/{run_id}/organization/approve')
def approve_organization(run_id: str, payload: organization.OrganizationPlan, owner: Owner) -> dict:
    organization.approve(run_id,payload,owner,audit)
    return harness.get_run(run_id,owner)


@router.post("/api/runs")
async def start_run(payload: harness.RunInput, owner: Owner) -> dict:
    return await harness.execute(payload, owner, TaskInput)


@router.post("/api/runs/{run_id}/approve")
def approve_run(run_id: str, owner: Owner, payload: TaskApproval | None = None) -> dict:
    edits = payload.edits.model_dump(mode='json') if payload and payload.edits else None
    return harness.decide(run_id, owner, True, audit, edits)


@router.post("/api/runs/{run_id}/reject")
def reject_run(run_id: str, owner: Owner) -> dict:
    return harness.decide(run_id, owner, False, audit)
