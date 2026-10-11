"""Reviewable organization of explicitly selected sources; no provider calls here."""
import json
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .db import connect, transaction
from .knowledge import normalized
from .security import iso


class SourceSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    area_id: str = Field(min_length=1, max_length=80)
    document_ids: list[str] = Field(min_length=1, max_length=6)

    @field_validator('document_ids')
    @classmethod
    def unique_documents(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('Selecione cada fonte uma única vez')
        return value


class SuggestedArea(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default='', max_length=500)
    document_ids: list[str] = Field(min_length=1, max_length=6)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        value = ' '.join(value.split())
        if len(value) < 2:
            raise ValueError('Use pelo menos dois caracteres no nome')
        return value


class OrganizationPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    areas: list[SuggestedArea] = Field(min_length=1, max_length=4)

    @model_validator(mode='after')
    def no_duplicates(self):
        names = [normalized(area.name) for area in self.areas]
        docs = [doc for area in self.areas for doc in area.document_ids]
        if len(set(names)) != len(names) or len(set(docs)) != len(docs):
            raise ValueError('Cada nome e fonte deve aparecer uma única vez')
        return self


def preview(selection, owner):
    with connect() as db:
        if not db.execute('SELECT 1 FROM areas WHERE id=? AND owner_id=?', (selection.area_id, owner['id'])).fetchone():
            raise HTTPException(404, 'Área não encontrada')
        sources = []
        for doc in selection.document_ids:
            row = db.execute('SELECT id,title,path,kind,hash,area_id,content FROM documents WHERE id=? AND owner_id=? AND area_id=? AND active=1', (doc, owner['id'], selection.area_id)).fetchone()
            if not row:
                raise HTTPException(409, 'Selecione apenas fontes ativas da área escolhida')
            item = dict(row)
            # Byte limit also bounds non-ASCII exports within the harness envelope.
            excerpt = item['content'].encode()[:1800].decode('utf-8', errors='ignore')
            item.update(source='doc:'+doc, content=excerpt, truncated=len(excerpt)<len(item['content']))
            sources.append(item)
    return sources


def validate_plan(plan, sources):
    allowed = {source['id'] for source in sources}
    if any(doc not in allowed for area in plan.areas for doc in area.document_ids):
        raise ValueError('Proposta inclui fonte não selecionada')


def validate_current(db, sources, owner, selected_ids=None):
    for source in sources:
        if selected_ids is not None and source['id'] not in selected_ids:
            continue
        row = db.execute('SELECT active,area_id,hash FROM documents WHERE id=? AND owner_id=?', (source['id'],owner['id'])).fetchone()
        if not row or not row['active'] or row['area_id']!=source['area_id'] or row['hash']!=source['hash']:
            raise HTTPException(409, 'Uma fonte foi pausada, removida ou reorganizada. Revise a seleção e gere outra proposta.')


def approve(run_id, plan, owner, audit):
    with transaction(immediate=True) as db:
        row = db.execute('SELECT * FROM runs WHERE id=? AND owner_id=?', (run_id,owner['id'])).fetchone()
        if not row:
            raise HTTPException(404, 'Execução não encontrada')
        request = json.loads(row['request_json'])
        if request.get('purpose')!='organization':
            raise HTTPException(409, 'Esta execução não é uma proposta de organização')
        accepted = plan.model_dump(mode='json')
        if row['organization_result_json']:
            prior = json.loads(row['organization_result_json'])
            if prior['accepted_plan']!=accepted:
                raise HTTPException(409, 'Esta proposta já foi aplicada com outra seleção')
            return prior
        if row['state']!='awaiting_confirmation':
            raise HTTPException(409, 'Execução não aguarda confirmação')
        sources = json.loads(row['sources_json'])
        try:
            validate_plan(plan, sources)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        selected = {doc for area in plan.areas for doc in area.document_ids}
        validate_current(db, sources, owner, selected)
        existing = {normalized(r[0]) for r in db.execute('SELECT name FROM areas WHERE owner_id=?',(owner['id'],))}
        if any(normalized(area.name) in existing for area in plan.areas):
            raise HTTPException(409, 'Já existe uma área com esse nome. Edite o nome da sugestão antes de confirmar.')
        created = []
        stamp = iso()
        for area in plan.areas:
            area_id = str(uuid.uuid4())
            db.execute('INSERT INTO areas(id,owner_id,name,description,created_at,updated_at) VALUES(?,?,?,?,?,?)', (area_id,owner['id'],area.name,area.description,stamp,stamp))
            for doc in area.document_ids:
                db.execute('UPDATE documents SET area_id=? WHERE id=? AND owner_id=?', (area_id,doc,owner['id']))
            created.append({'id':area_id,'name':area.name,'document_ids':area.document_ids})
            audit(db,owner['id'],'area.created.from_sources','area',area_id,{'run_id':run_id,'document_ids':area.document_ids})
        result = {'accepted_plan':accepted,'created_areas':created}
        db.execute("UPDATE runs SET state='completed',organization_result_json=?,updated_at=? WHERE id=?", (json.dumps(result),stamp,run_id))
        audit(db,owner['id'],'organization.approved','run',run_id)
    return result
