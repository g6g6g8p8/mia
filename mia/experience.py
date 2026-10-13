"""Owner-confirmed focus and installation disclosure; never infers personal facts."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .db import connect, transaction
from .security import iso


class FocusInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(default='', max_length=200)
    source_ids: list[str] = Field(default_factory=list, max_length=20)
    expected_revision: int = Field(ge=0)

    @field_validator('title')
    @classmethod
    def clean_title(cls, value):
        return ' '.join(value.split())


class LocationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['local', 'remote']


def location(owner=None, address='') -> dict:
    configured = os.environ.get('MIA_INSTALLATION_MODE', '')
    mode = {'server':'remote', 'remote':'remote', 'local':'local'}.get(configured, 'unknown')
    if owner:
        with connect() as db:
            row = db.execute('SELECT mode FROM experience_location WHERE owner_id=?', (owner['id'],)).fetchone()
            if row:
                mode = row['mode']
    description = {
        'local':'Os arquivos importados ficam no computador onde esta Mia foi instalada. Acesso de outro dispositivo depende de ele estar ligado e acessível.',
        'remote':'Os arquivos enviados são copiados para o servidor desta instalação. Mac e iPhone podem acessar o mesmo contexto pelo endereço preparado.',
        'unknown':'Os arquivos enviados ficam nesta instalação da Mia. Confirme se ela está no seu computador ou em um servidor antes de importar.'
    }[mode]
    return {'mode':mode, 'address':address, 'description':description,
            'model_disclosure':'Importar e indexar não envia conteúdo a uma IA. Consultas com IA usam somente o contexto autorizado e o destino escolhido.'}


def save_location(payload, owner, audit, address='') -> dict:
    with transaction(immediate=True) as db:
        db.execute('INSERT INTO experience_location(owner_id,mode,updated_at) VALUES(?,?,?) ON CONFLICT(owner_id) DO UPDATE SET mode=excluded.mode,updated_at=excluded.updated_at', (owner['id'],payload.mode,iso()))
        audit(db,owner['id'],'installation.location.confirmed',metadata={'mode':payload.mode})
    return location(owner,address)


def focus_from_db(db, owner) -> dict:
    row = db.execute('SELECT title,source_ids_json,revision,updated_at FROM experience_focus WHERE owner_id=?',(owner['id'],)).fetchone()
    if not row:
        return {'title':'','source_ids':[],'revision':0,'updated_at':None,'unavailable_sources':0}
    value = dict(row)
    original = json.loads(value.pop('source_ids_json'))
    available = [identity for identity in original if db.execute('SELECT 1 FROM documents WHERE id=? AND owner_id=? AND active=1',(identity,owner['id'])).fetchone()]
    value.update(source_ids=available, unavailable_sources=len(original)-len(available))
    return value


def focus(owner) -> dict:
    with connect() as db:
        return focus_from_db(db,owner)


def export_focus_from_db(db, owner) -> dict:
    value = focus_from_db(db, owner)
    value['available_source_ids'] = value['source_ids']
    row = db.execute('SELECT source_ids_json FROM experience_focus WHERE owner_id=?', (owner['id'],)).fetchone()
    value['source_ids'] = json.loads(row[0]) if row else []
    return value


def source_evidence(db, doc, owner) -> dict:
    """Literal, bounded source material; labels are navigation, not fact claims."""
    row = db.execute('''SELECT content FROM chunks WHERE document_id=?
        ORDER BY CASE WHEN lower(content) LIKE '%decis%' OR lower(content) LIKE '%decision%'
          OR lower(content) LIKE '%penden%' OR lower(content) LIKE '%next step%'
          OR lower(content) LIKE '%próximo passo%' THEN 0 ELSE 1 END, ordinal DESC LIMIT 1''', (doc['id'],)).fetchone()
    # Keep structured role/date headers from conversation chunks. A quoted
    # assistant message must never be relabelled as a confirmed user decision.
    excerpt = row['content'][:900] if row else ''
    dates = None
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='migration_provenance'").fetchone():
        metadata = db.execute('''SELECT json_extract(p.metadata_json,'$.source.dates') FROM migration_provenance p
            JOIN imports i ON i.id=p.import_id WHERE p.document_id=? AND i.owner_id=? ORDER BY i.created_at DESC LIMIT 1''', (doc['id'],owner['id'])).fetchone()
        dates = json.loads(metadata[0]) if metadata and metadata[0] else {}
    value = next((dates.get(key) for key in ('updated_at','update_time','created_at','create_time') if dates.get(key) is not None), None) if dates else None
    if isinstance(value, (float, int)):
        try:
            value = datetime.fromtimestamp(value, timezone.utc).isoformat()
        except (ValueError, OSError, OverflowError):
            value = str(value)
    return {'evidence_excerpt':excerpt, 'source_date':str(value)[:240] if value is not None else None,
            'evidence_status':'Trecho literal para conferir; não confirma decisão vigente ou tarefa.'}


def save_focus(payload, owner, audit) -> dict:
    sources = list(dict.fromkeys(payload.source_ids))
    with transaction(immediate=True) as db:
        current = focus_from_db(db,owner)
        if payload.expected_revision != current['revision']:
            raise HTTPException(409,'O foco mudou. Reabra antes de salvar para preservar sua revisão.')
        for identity in sources:
            if not db.execute('SELECT 1 FROM documents WHERE id=? AND owner_id=? AND active=1',(identity,owner['id'])).fetchone():
                raise HTTPException(409,'Selecione somente fontes ativas da sua biblioteca.')
        db.execute('INSERT INTO experience_focus(owner_id,title,source_ids_json,revision,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(owner_id) DO UPDATE SET title=excluded.title,source_ids_json=excluded.source_ids_json,revision=excluded.revision,updated_at=excluded.updated_at', (owner['id'],payload.title,json.dumps(sources),current['revision']+1,iso()))
        audit(db,owner['id'],'focus.confirmed',metadata={'sources':len(sources)})
    return focus(owner)


def overview(owner, address='') -> dict:
    with connect() as db:
        documents = [dict(row) for row in db.execute('SELECT id,title,path,kind,area_id,created_at,active FROM documents WHERE owner_id=? ORDER BY created_at DESC,id', (owner['id'],))]
        current_focus = focus_from_db(db,owner)
        threads = [dict(row) for row in db.execute('SELECT id,title,scope,area_id,updated_at FROM conversations WHERE owner_id=? ORDER BY updated_at DESC LIMIT 5',(owner['id'],))]
        goal = db.execute('SELECT goal FROM onboarding WHERE owner_id=?',(owner['id'],)).fetchone()
        states = []
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='migration_jobs'").fetchone():
            states = [row[0] for row in db.execute('SELECT state FROM migration_jobs WHERE owner_id=?',(owner['id'],))]
    active = [doc for doc in documents if doc['active']]
    groups = {}
    for doc in active:
        parts = PurePosixPath(doc['path']).parts
        group = '/'.join(parts[:-1]) or 'Arquivos avulsos'
        groups[group] = groups.get(group,0)+1
    priority = {identity:index for index,identity in enumerate(current_focus['source_ids'])}
    active.sort(key=lambda doc:(priority.get(doc['id'],21),doc['title'].casefold()))
    terminal = {'completed','complete','cancelled','canceled','error','failed','partial'}
    with connect() as db:
        sources = [{**doc, **source_evidence(db, doc, owner)} for doc in active[:20]]
    return {'location':location(owner,address), 'library':{'total':len(documents),'active':len(active),'paused':len(documents)-len(active),'groups':[{'name':name,'total':count} for name,count in sorted(groups.items())]},
            'focus':current_focus,'sources':sources, 'migrations':{'total':len(states),'active':sum(state not in terminal for state in states),'failed':sum(state in {'failed','error'} for state in states),'partial':states.count('partial')},
            'threads':threads,'goal':goal['goal'] if goal else '', 'knowledge_status':'Fontes da biblioteca; não são decisões atuais ou tarefas inferidas. Confira a origem e confirme o que continua em andamento.'}
