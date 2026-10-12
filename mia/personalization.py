"""Source-grounded suggestions become personal context only after review."""
import json

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .db import connect, transaction
from .organization import validate_current
from .security import iso


class Evidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    document_id: str = Field(min_length=1, max_length=80)
    quote: str = Field(min_length=3, max_length=240)

    @field_validator('quote')
    @classmethod
    def nonblank(cls, value):
        if len(value.strip()) < 3:
            raise ValueError('Informe um trecho de apoio legível')
        return value


class Suggestion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=2, max_length=1000)
    evidence: list[Evidence] = Field(min_length=1, max_length=3)

    @field_validator('text')
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError('Informe um texto legível')
        return value


class PersonalizationPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    context: Suggestion | None = None
    goal: Suggestion | None = None

    @model_validator(mode='after')
    def at_least_one(self):
        if self.context is None and self.goal is None:
            raise ValueError('Selecione contexto ou objetivo para aplicar')
        return self


class ContextEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(max_length=1000)
    expected_revision: int = Field(ge=0)


def state_from_db(db, owner):
    row = db.execute('SELECT text,revision,evidence_json,updated_at FROM personal_context WHERE owner_id=?',(owner['id'],)).fetchone()
    goal = db.execute('SELECT goal,goal_revision FROM onboarding WHERE owner_id=?',(owner['id'],)).fetchone()
    return {'text':row['text'] if row else '', 'revision':row['revision'] if row else 0,
            'evidence':json.loads(row['evidence_json']) if row else [],'updated_at':row['updated_at'] if row else None,
            'goal':goal['goal'] if goal else '', 'goal_revision':goal['goal_revision'] if goal else 0}


def get_state(owner):
    with connect() as db:
        return state_from_db(db,owner)


def write_context(db, owner, text, evidence):
    db.execute('INSERT INTO personal_context(owner_id,text,revision,evidence_json,updated_at) VALUES(?,?,1,?,?) ON CONFLICT(owner_id) DO UPDATE SET text=excluded.text,revision=personal_context.revision+1,evidence_json=excluded.evidence_json,updated_at=excluded.updated_at',(owner['id'],text,json.dumps(evidence),iso()))


def edit_context(payload, owner, audit):
    with transaction(immediate=True) as db:
        current=state_from_db(db,owner)
        if current['revision']!=payload.expected_revision:
            raise HTTPException(409,'O contexto mudou. Reabra a tela antes de editar.')
        write_context(db,owner,payload.text.strip(),[])
        audit(db,owner['id'],'personal_context.edited','owner',str(owner['id']))
    return get_state(owner)


def validate_plan(plan, sources):
    allowed={source['id']:source['content'] for source in sources}
    for suggestion in (plan.context,plan.goal):
        if suggestion is None:
            continue
        for evidence in suggestion.evidence:
            if evidence.document_id not in allowed or evidence.quote not in allowed[evidence.document_id]:
                raise ValueError('Trecho de apoio não pertence às fontes enviadas')


def approve(run_id, plan, owner, audit):
    with transaction(immediate=True) as db:
        row=db.execute('SELECT * FROM runs WHERE id=? AND owner_id=?',(run_id,owner['id'])).fetchone()
        if not row:
            raise HTTPException(404,'Execução não encontrada')
        if json.loads(row['request_json']).get('purpose')!='personalization':
            raise HTTPException(409,'Esta execução não é uma proposta de personalização')
        accepted=plan.model_dump(mode='json')
        if row['personalization_result_json']:
            result=json.loads(row['personalization_result_json'])
            if result['accepted_plan']!=accepted:
                raise HTTPException(409,'Esta proposta já foi aplicada com outra seleção')
            return result
        if row['state']!='awaiting_confirmation':
            raise HTTPException(409,'Execução não aguarda confirmação')
        proposed=json.loads(row['proposal_json'])
        for name in ('context','goal'):
            if accepted[name] is not None and proposed.get(name) is None:
                raise HTTPException(422,'Este campo não foi sugerido nesta execução')
        sources=json.loads(row['sources_json'])
        try:
            validate_plan(plan,sources)
        except ValueError as error:
            raise HTTPException(422,str(error)) from error
        selected={e.document_id for s in (plan.context,plan.goal) if s for e in s.evidence}
        validate_current(db,sources,owner,selected)
        base=json.loads(row['personalization_base_json'])
        current=state_from_db(db,owner)
        if (plan.context and current['revision']!=base['revision']) or (plan.goal and current['goal_revision']!=base['goal_revision']):
            raise HTTPException(409,'Seu contexto ou objetivo mudou após esta geração. Gere outra proposta para preservar a edição mais recente.')
        if plan.context:
            write_context(db,owner,plan.context.text,[e.model_dump() for e in plan.context.evidence])
        if plan.goal:
            db.execute('INSERT INTO onboarding(owner_id,goal,updated_at,goal_revision) VALUES(?,?,?,1) ON CONFLICT(owner_id) DO UPDATE SET goal=excluded.goal,goal_revision=onboarding.goal_revision+1,updated_at=excluded.updated_at',(owner['id'],plan.goal.text,iso()))
        result={'accepted_plan':accepted}
        db.execute("UPDATE runs SET state='completed',personalization_result_json=?,updated_at=? WHERE id=?",(json.dumps(result),iso(),run_id))
        audit(db,owner['id'],'personalization.approved','run',run_id,{'context':bool(plan.context),'goal':bool(plan.goal)})
    return result
