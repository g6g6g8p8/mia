"""Owner-scoped conversations and bounded, reauthorized continuation context."""
from __future__ import annotations

import json
import re
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .db import connect, transaction
from .security import iso
from . import personalization, experience


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(default='Nova conversa', min_length=1, max_length=120)
    area_id: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator('title')
    @classmethod
    def clean_title(cls, title):
        title = ' '.join(title.split())
        if not title:
            raise ValueError('Informe um título')
        return title


class ConversationRename(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=120)
    _clean = field_validator('title')(ConversationCreate.clean_title.__func__)


def thread_from_db(db, thread_id, owner, require_scope=True):
    row = db.execute('SELECT * FROM conversations WHERE id=? AND owner_id=?', (thread_id, owner['id'])).fetchone()
    if not row:
        raise HTTPException(404, 'Conversa não encontrada')
    # An area-deletion must not silently broaden a conversation to the library.
    area=db.execute('SELECT name FROM areas WHERE id=? AND owner_id=?',(row['area_id'],owner['id'])).fetchone() if row['area_id'] else None
    unavailable=row['scope']=='area' and not area
    if require_scope and unavailable:
        raise HTTPException(409, 'A área desta conversa não está mais disponível. Crie outra conversa com um escopo autorizado.')
    result = dict(row)
    result.pop('owner_id')
    result.update(scope_unavailable=bool(unavailable),area_name=area['name'] if area else None)
    return result


def scope(thread_id, owner, area_id=None):
    with connect() as db:
        result = thread_from_db(db, thread_id, owner)
    if area_id is not None and area_id != result['area_id']:
        raise HTTPException(422, 'O escopo da conversa não pode mudar entre pedidos')
    return result


def create(payload, owner, audit=None):
    stamp, thread_id = iso(), str(uuid.uuid4())
    with transaction(immediate=True) as db:
        if payload.area_id and not db.execute('SELECT 1 FROM areas WHERE id=? AND owner_id=?', (payload.area_id, owner['id'])).fetchone():
            raise HTTPException(404, 'Área não encontrada')
        db.execute('INSERT INTO conversations(id,owner_id,title,area_id,scope,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                   (thread_id, owner['id'], payload.title, payload.area_id, 'area' if payload.area_id else 'library', stamp, stamp))
        if audit:
            audit(db, owner['id'], 'conversation.created', 'conversation', thread_id, {'scope':'area' if payload.area_id else 'library'})
        return thread_from_db(db, thread_id, owner)


def listing(owner):
    with connect() as db:
        rows = list(db.execute('SELECT c.*,count(r.id) AS run_count FROM conversations c LEFT JOIN runs r ON r.thread_id=c.id AND r.owner_id=c.owner_id WHERE c.owner_id=? GROUP BY c.id ORDER BY c.updated_at DESC,c.id LIMIT 100', (owner['id'],)))
        return [{**thread_from_db(db,row['id'],owner,require_scope=False),'run_count':row['run_count']} for row in rows]


def detail(thread_id, owner):
    from .harness import public_run
    with connect() as db:
        result = thread_from_db(db, thread_id, owner,require_scope=False)
        # Last 100 requests are returned in chronological order. Older history
        # remains persisted/exportable and is never silently sent to the model.
        rows = list(db.execute('SELECT * FROM runs WHERE owner_id=? AND thread_id=? ORDER BY created_at DESC,rowid DESC LIMIT 100', (owner['id'], thread_id)))
        result['run_count'] = db.execute('SELECT count(*) FROM runs WHERE owner_id=? AND thread_id=?', (owner['id'], thread_id)).fetchone()[0]
        result['runs'] = [public_run(row) for row in reversed(rows)]
        result['older_history_count'] = max(0, result['run_count'] - len(rows))
        return result


def rename(thread_id, payload, owner, audit=None):
    with transaction(immediate=True) as db:
        thread_from_db(db, thread_id, owner,require_scope=False)
        db.execute('UPDATE conversations SET title=?,updated_at=? WHERE id=? AND owner_id=?', (payload.title, iso(), thread_id, owner['id']))
        if audit:
            audit(db, owner['id'], 'conversation.renamed', 'conversation', thread_id)
    return detail(thread_id, owner)


def source_current(db, source, owner, area_id, include_personal_context=False, use_confirmed_focus=False):
    """Validate snapshots before reuse; ownership and revocation outrank history."""
    ref = source.get('source', '')
    if ref.startswith('doc:'):
        row = db.execute('SELECT hash,area_id,active FROM documents WHERE id=? AND owner_id=?', (ref[4:], owner['id'])).fetchone()
        return bool(row and row['active'] and (not area_id or row['area_id'] == area_id) and row['area_id'] == source.get('area_id') and row['hash'] == source.get('hash'))
    if ref.startswith('area:'):
        row = db.execute('SELECT updated_at FROM areas WHERE id=? AND owner_id=?', (ref[5:], owner['id'])).fetchone()
        return bool(row and (not area_id or ref[5:] == area_id) and row['updated_at'] == source.get('updated_at'))
    if ref.startswith('task:'):
        row = db.execute('SELECT updated_at,area_id FROM tasks WHERE id=? AND owner_id=?', (ref[5:], owner['id'])).fetchone()
        return bool(row and (not area_id or row['area_id'] == area_id) and row['updated_at'] == source.get('updated_at'))
    if ref == 'profile:1':
        if not include_personal_context:
            return False
        state = personalization.state_from_db(db, owner)
        return all(state[key] == source.get(key) for key in ('revision', 'goal_revision', 'text', 'goal'))
    if ref == 'focus:1':
        if not use_confirmed_focus:
            return False
        current=experience.focus_from_db(db,owner)
        if current['revision']!=source.get('revision') or current['title']!=source.get('title'):
            return False
        for doc in source.get('source_ids',[]):
            row=db.execute('SELECT area_id FROM documents WHERE id=? AND owner_id=? AND active=1',(doc,owner['id'])).fetchone()
            if doc not in current['source_ids'] or not row or (area_id and row['area_id']!=area_id):
                return False
        return True
    return False


def history_from_db(db, thread_id, owner, area_id, include_personal_context=False, use_confirmed_focus=False):
    """Whole turns are omitted if any source is revoked, preventing paraphrase leaks.

    Failed/reserved calls never become model messages or get retried. Historical
    answers and proposal decisions stay visible in the owner's history.
    """
    thread_from_db(db, thread_id, owner)
    rows = list(db.execute("SELECT * FROM runs WHERE owner_id=? AND thread_id=? AND state IN ('completed','awaiting_confirmation','rejected') ORDER BY created_at DESC,rowid DESC LIMIT 12", (owner['id'], thread_id)))
    turns, sources, skipped, chars = [], {}, 0, 0
    for row in rows:
        try:
            snapshots = json.loads(row['sources_json'])
            request = json.loads(row['request_json'])
        except (ValueError,TypeError):
            skipped += 1
            continue
        if not isinstance(snapshots,list) or any(not isinstance(source,dict) for source in snapshots) or not isinstance(request,dict):
            skipped += 1
            continue
        allowed={source.get('source') for source in snapshots}
        cited=set(re.findall(r'(?:doc|area|task|profile|focus):[A-Za-z0-9-]+',row['answer'] or ''))
        # Old imports/restores without a complete continuation snapshot cannot
        # prove which source/profile influenced an answer. Keep them visible,
        # but do not send them again on the owner's behalf.
        if not row['continuation_json'] or cited-allowed or request.get('purpose', 'assistant') != 'assistant' or any(not source_current(db, source, owner, area_id, include_personal_context,use_confirmed_focus) for source in snapshots):
            skipped += 1
            continue
        if not row['answer']:
            continue
        # Never cut a previous answer: shortening could remove qualifications or
        # mix truncated approval-sensitive proposals into a later request.
        turn = [{'role':'user', 'content':request.get('message','')}, {'role':'assistant', 'content':row['answer']}]
        size = sum(len(item['content'].encode()) for item in turn)
        candidate_keys={(source.get('source'),source.get('ordinal')) for source in snapshots}
        if chars + size > 6000 or len(turns) >= 4 or len(set(sources) | candidate_keys)>24:
            skipped += 1
            continue
        chars += size
        turns.append(turn)
        for source in snapshots:
            sources[(source.get('source'), source.get('ordinal'))] = source
    history = [message for turn in reversed(turns) for message in turn]
    notice = 'Parte do histórico não foi enviada: fontes/foco alterados, perfil/foco sem autorização atual ou limite de contexto.' if skipped else None
    return {'messages':history, 'sources':list(sources.values()), 'skipped_history_count':skipped, 'history_notice':notice}


def history(thread_id, owner, area_id, include_personal_context=False, use_confirmed_focus=False):
    with connect() as db:
        return history_from_db(db, thread_id, owner, area_id, include_personal_context,use_confirmed_focus)
