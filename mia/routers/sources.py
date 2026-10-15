from fastapi import APIRouter, HTTPException
from typing import Annotated

from mia import knowledge
from mia.app import Owner, audit
from mia.db import connect, transaction

router = APIRouter()


@router.post('/api/imports',status_code=201)
def prepare_import(payload: knowledge.ImportInput,owner: Annotated[dict, Owner]) -> dict:
    return knowledge.prepare(payload,owner)


@router.get('/api/imports')
def imports(owner: Annotated[dict, Owner]) -> list[dict]:
    with connect() as db:
        ids=[row[0] for row in db.execute('SELECT id FROM imports WHERE owner_id=? ORDER BY created_at DESC',(owner['id'],))]
    return [knowledge.get_batch(batch,owner) for batch in ids]


@router.get('/api/imports/{batch}')
def get_import(batch: str,owner: Annotated[dict, Owner]) -> dict:
    return knowledge.get_batch(batch,owner)


@router.post('/api/imports/{batch}/confirm')
def confirm_import(batch: str,payload: knowledge.Selection,owner: Annotated[dict, Owner]) -> dict:
    return knowledge.commit(batch,payload,owner,audit)


@router.delete('/api/imports/{batch}')
def remove_import(batch: str,owner: Annotated[dict, Owner]) -> dict:
    return knowledge.remove(batch,owner,audit)


@router.get('/api/documents')
def documents(owner: Annotated[dict, Owner]) -> list[dict]:
    with connect() as db:
        return [dict(row) for row in db.execute('SELECT id,title,path,kind,area_id,created_at,active FROM documents WHERE owner_id=? ORDER BY created_at DESC',(owner['id'],))]


@router.put('/api/documents/{doc}/state')
def set_document_state(doc: str,payload: knowledge.SourceState,owner: Annotated[dict, Owner]) -> dict:
    return knowledge.set_source_state(doc,payload,owner,audit)


@router.get('/api/documents/{doc}')
def get_document(doc: str,owner: Annotated[dict, Owner]) -> dict:
    return knowledge.document(doc,owner)
