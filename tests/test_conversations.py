import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from test_app import client, setup_payload
from test_retrieval import store
from mia import conversations, harness, personalization
from mia.app import TaskInput
from mia.db import connect, transaction


@pytest.fixture
def ready(client,monkeypatch):
    browser,path=client
    browser.post('/api/setup',json=setup_payload())
    area=browser.get('/api/areas').json()[0]['id']
    monkeypatch.setenv('MIA_AI_ENABLED','true')
    monkeypatch.setenv('MIA_AI_BASE_URL','https://provider.example.test/v1')
    monkeypatch.setenv('MIA_AI_API_KEY','fixture-never-real')
    monkeypatch.setenv('MIA_AI_MODEL','fixture-model')
    monkeypatch.setenv('MIA_AI_DAILY_CALL_LIMIT','100')
    return browser,area,path,{'id':1,'timezone':'America/Sao_Paulo'}


def invoke(thread,owner,message='Retome protocolo âmbar',**extra):
    payload=harness.RunInput(request_key=uuid.uuid4(),thread_id=thread['id'],message=message,consent=True,**extra)
    return asyncio.run(harness.execute(payload,owner,TaskInput))


def answer(text='Resposta sintética para continuar.'):
    return {'choices':[{'finish_reason':'stop','message':{'content':text}}],'usage':{'prompt_tokens':120,'completion_tokens':40}}


def test_threads_survive_restart_rename_and_new_requests_keep_history(ready,monkeypatch):
    browser,area,_,owner=ready
    doc=store(area,'Protocolo âmbar: decisão anterior revisada.','projeto.md')
    thread=conversations.create(conversations.ConversationCreate(title='Projeto',area_id=area),owner)
    seen=[]
    async def fake(settings,messages,schema):
        seen.append(messages)
        return answer('Decisão com fonte doc:'+doc)
    monkeypatch.setattr(harness,'call_provider',fake)
    first=invoke(thread,owner)
    second=invoke(thread,owner,'E qual próximo passo?')
    assert second['thread_id']==thread['id'] and second['included_turn_count']==1
    assert [m['role'] for m in seen[1]]==['system','user','assistant','user']
    assert 'Decisão com fonte' in seen[1][2]['content']
    assert 'doc:'+doc in second['citations']
    renamed=conversations.rename(thread['id'],conversations.ConversationRename(title='  Retomar   projeto '),owner)
    assert renamed['title']=='Retomar projeto' and len(renamed['runs'])==2
    with TestClient(browser.app) as restarted:
        restarted.post('/api/login',json={'password':'senha-forte-123'})
        restored=conversations.detail(thread['id'],owner)
        assert [r['id'] for r in restored['runs']]==[first['id'],second['id']]
    assert conversations.listing(owner)[0]['run_count']==2
    assert len(seen)==2


def test_library_scope_explicit_no_arbitrary_task_and_request_key_replay(ready,monkeypatch):
    _,area,_,owner=ready
    one=store(area,'Protocolo âmbar uma fonte.','one.md')
    thread=conversations.create(conversations.ConversationCreate(),owner)
    other=conversations.create(conversations.ConversationCreate(title='Outra'),owner)
    seen=[]
    async def fake(settings,messages,schema):
        seen.append((settings,messages))
        return answer('Biblioteca doc:'+one)
    monkeypatch.setattr(harness,'call_provider',fake)
    payload=harness.RunInput(request_key=uuid.uuid4(),thread_id=thread['id'],message='Protocolo âmbar',consent=True)
    result=asyncio.run(harness.execute(payload,owner,TaskInput))
    assert seen[0][0]['_answer_only'] is True
    assert asyncio.run(harness.execute(payload,owner,TaskInput))['id']==result['id']
    assert len(seen)==1
    with pytest.raises(Exception) as conflict:
        asyncio.run(harness.execute(payload.model_copy(update={'thread_id':other['id']}),owner,TaskInput))
    assert conflict.value.status_code==409
    async def invalid(*args):
        return {'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{'function':{'name':'propose_task','arguments':json.dumps({'title':'Not authorized','area_id':area})}}]}}]}
    monkeypatch.setattr(harness,'call_provider',invalid)
    failed=invoke(thread,owner)
    assert failed['state']=='failed' and failed['proposal'] is None
    with connect() as db:
        assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==0


@pytest.mark.parametrize('change',['pause','delete','move','content'])
def test_revoked_sources_omit_whole_turn_and_new_context(ready,monkeypatch,change):
    browser,area,_,owner=ready
    doc=store(area,'Protocolo âmbar SEGREDO_REVOGADO.','private.md')
    thread=conversations.create(conversations.ConversationCreate(area_id=area),owner)
    seen=[]
    async def fake(settings,messages,schema):
        seen.append(json.dumps(messages))
        return answer('SEGREDO_REVOGADO encontrado doc:'+doc)
    monkeypatch.setattr(harness,'call_provider',fake)
    invoke(thread,owner)
    with transaction() as db:
        if change=='pause': db.execute('UPDATE documents SET active=0 WHERE id=?',(doc,))
        elif change=='delete': db.execute('DELETE FROM documents WHERE id=?',(doc,))
        elif change=='move':
            other=browser.post('/api/areas',json={'name':'Movida'}).json()['id']
            db.execute('UPDATE documents SET area_id=? WHERE id=?',(other,doc))
        else:
            db.execute('UPDATE documents SET hash=?,content=? WHERE id=?',('changed','texto novo',doc))
            db.execute('UPDATE chunks SET content=?,searchable=? WHERE document_id=?',('texto novo','texto novo',doc))
    second=invoke(thread,owner,'Qual próximo passo?')
    assert 'SEGREDO_REVOGADO' not in seen[-1]
    assert second['included_turn_count']==0 and second['skipped_history_count']==1 and second['history_notice']
    assert len(conversations.detail(thread['id'],owner)['runs'])==2


def test_profile_consent_is_per_turn_and_changed_profile_revokes_history(ready,monkeypatch):
    _,area,_,owner=ready
    with transaction() as db:
        personalization.write_context(db,owner,'CONTEXTO_PESSOAL_CONFIRMADO',[])
    thread=conversations.create(conversations.ConversationCreate(area_id=area),owner)
    seen=[]
    async def fake(settings,messages,schema):
        seen.append(json.dumps(messages))
        return answer('CONTEXTO_PESSOAL_CONFIRMADO influenciou esta resposta.')
    monkeypatch.setattr(harness,'call_provider',fake)
    invoke(thread,owner,include_personal_context=True)
    second=invoke(thread,owner,'Continue sem perfil')
    assert 'CONTEXTO_PESSOAL_CONFIRMADO' not in seen[-1]
    assert second['included_turn_count']==0 and second['skipped_history_count']==1
    with transaction() as db:
        personalization.write_context(db,owner,'NOVO_PERFIL',[])
    third=invoke(thread,owner,'Retome com perfil atual',include_personal_context=True)
    # First request used an obsolete profile, and the second deliberately had
    # none. Its fake answer cannot be treated as a confirmed personal fact.
    assert third['skipped_history_count']>=1
    assert 'NOVO_PERFIL' in seen[-1]


def test_scope_owner_deleted_area_and_failed_calls_never_replayed(ready,monkeypatch):
    _,area,_,owner=ready
    thread=conversations.create(conversations.ConversationCreate(area_id=area),owner)
    with pytest.raises(Exception) as wrong:
        conversations.detail(thread['id'],{'id':2})
    assert wrong.value.status_code==404
    with pytest.raises(Exception) as wrongscope:
        invoke(thread,owner,area_id='elsewhere')
    assert wrongscope.value.status_code==422
    calls=[]
    async def failed(*args):
        calls.append(1)
        raise TimeoutError('fixture-never-real')
    monkeypatch.setattr(harness,'call_provider',failed)
    payload=harness.RunInput(request_key=uuid.uuid4(),thread_id=thread['id'],message='Pergunta',consent=True)
    first=asyncio.run(harness.execute(payload,owner,TaskInput))
    replay=asyncio.run(harness.execute(payload,owner,TaskInput))
    assert replay['id']==first['id'] and len(calls)==1 and replay['state']=='failed'
    assert 'fixture-never-real' not in json.dumps(replay)
    with transaction() as db:
        db.execute('DELETE FROM areas WHERE id=?',(area,))
    with pytest.raises(Exception) as missing:
        conversations.scope(thread['id'],owner)
    assert missing.value.status_code==409


def test_many_turns_keep_context_and_dependency_snapshots_bounded(ready,monkeypatch):
    _,area,_,owner=ready
    thread=conversations.create(conversations.ConversationCreate(area_id=area),owner)
    seen=[]
    async def fake(settings,messages,schema):
        seen.append(json.dumps(messages,ensure_ascii=False).encode())
        return answer('Resposta de continuidade '+('observação '*100))
    monkeypatch.setattr(harness,'call_provider',fake)
    for number in range(15):
        doc=store(area,f'Termo{number} evidência sintética de novo projeto.','note-'+str(number)+'.md')
        result=invoke(thread,owner,'Retome Termo'+str(number))
        assert len(result['sources'])<=30
    assert all(len(body)<=24000 for body in seen)
    assert result['included_turn_count']<=4 and result['history_notice']
