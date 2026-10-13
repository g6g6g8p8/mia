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
    preserved=conversations.detail(thread['id'],owner)
    assert preserved['scope_unavailable'] is True and preserved['runs'][0]['id']==first['id']
    assert conversations.listing(owner)[0]['scope_unavailable'] is True
    assert conversations.rename(thread['id'],conversations.ConversationRename(title='Histórico preservado'),owner)['title']=='Histórico preservado'


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


def test_incomplete_legacy_history_and_invalid_citations_stay_out_of_model(ready,monkeypatch):
    _,area,_,owner=ready
    thread=conversations.create(conversations.ConversationCreate(area_id=area),owner)
    seen=[]
    async def fake(settings,messages,schema):
        seen.append(json.dumps(messages))
        return answer('Answer with invalid source doc:unavailable')
    monkeypatch.setattr(harness,'call_provider',fake)
    old=invoke(thread,owner)
    second=invoke(thread,owner,'Continue')
    assert second['included_turn_count']==0 and second['skipped_history_count']==1
    with transaction() as db:
        db.execute('UPDATE runs SET answer=?,continuation_json=NULL,sources_json=? WHERE id=?',('LEGACY_WITHOUT_SNAPSHOT','[]',old['id']))
    result=invoke(thread,owner,'Outra pergunta')
    assert 'LEGACY_WITHOUT_SNAPSHOT' not in seen[-1]
    assert result['included_turn_count']==0 and result['skipped_history_count']==2


def test_source_preflight_before_paid_reservation_and_thread_http_access(ready,monkeypatch):
    browser,area,_,owner=ready
    created=browser.post('/api/conversations',json={'title':'Projeto','area_id':area})
    assert created.status_code==201
    thread=created.json()
    assert browser.get('/api/conversations').json()[0]['id']==thread['id']
    assert browser.patch('/api/conversations/'+thread['id'],json={'title':'Renomeada'}).json()['title']=='Renomeada'
    assert browser.patch('/api/conversations/'+thread['id'],json={'title':'No'},headers={'Origin':'https://wrong.example'}).status_code==403
    assert TestClient(browser.app).get('/api/conversations/'+thread['id']).status_code==401
    doc=store(area,'Protocolo âmbar sujeito a revogação.','revoked.md')
    original=harness.context
    def changed(*args,**kwargs):
        sources=original(*args,**kwargs)
        with transaction() as db:
            db.execute('UPDATE documents SET active=0 WHERE id=?',(doc,))
        return sources
    async def never(*args):
        pytest.fail('Revoked context must never reach provider')
    monkeypatch.setattr(harness,'context',changed)
    monkeypatch.setattr(harness,'call_provider',never)
    with pytest.raises(Exception) as conflict:
        invoke(thread,owner)
    assert conflict.value.status_code==409
    assert browser.get('/api/runs').json()==[]
    assert browser.get('/api/conversations/'+thread['id']).json()['runs']==[]


def test_library_provider_adapter_does_not_offer_task_tools(monkeypatch):
    import httpx
    actual=httpx.AsyncClient
    requests=[]
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json=answer())
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:actual(transport=httpx.MockTransport(respond),**kwargs))
    asyncio.run(harness.call_provider({'endpoint':'https://provider.example/v1','model':'fixture','max_output_tokens':1000,'_answer_only':True,'_key':'synthetic'},[],TaskInput.model_json_schema()))
    assert 'tools' not in requests[0]
    assert requests[0]['max_completion_tokens']==1000


def test_selected_context_too_large_does_not_consume_budget_or_call_limit(ready,monkeypatch):
    _,area,_,owner=ready
    docs=[store(area,'Conteúdo sintético '+str(number)+' '+('nota de projeto '*150),'source-'+str(number)+'.md') for number in range(6)]
    async def never(*args):
        pytest.fail('Oversize selected context must not be sent')
    monkeypatch.setattr(harness,'call_provider',never)
    payload=harness.RunInput(request_key=uuid.uuid4(),area_id=area,purpose='organization',message='🔷'*4000,document_ids=docs,consent=True)
    with pytest.raises(Exception) as error:
        asyncio.run(harness.execute(payload,owner,TaskInput))
    assert error.value.status_code==422
    with connect() as db:
        assert db.execute('SELECT count(*) FROM runs').fetchone()[0]==0


def test_confirmed_focus_retrieves_lexical_misses_without_profile_or_area_expansion(ready,monkeypatch):
    browser,area,_,owner=ready
    doc=store(area,'# Caderno\nPrecisamos revisar contrato azul.','caderno.md')
    other=browser.post('/api/areas',json={'name':'Privada'}).json()['id']
    outside=store(other,'CONTEUDO_OUTRA_AREA em fonte privada.','privado.md')
    assert browser.put('/api/focus',json={'title':'Trabalho atual','source_ids':[doc,outside],'expected_revision':0}).status_code==200
    with transaction() as db:
        personalization.write_context(db,owner,'PERFIL_FORA_DESTE_PEDIDO',[])
    thread=conversations.create(conversations.ConversationCreate(area_id=area),owner)
    seen=[]
    async def fake(settings,messages,schema):
        seen.append(json.dumps(messages,ensure_ascii=False))
        return answer('Fonte para retomar doc:'+doc)
    monkeypatch.setattr(harness,'call_provider',fake)
    assert not any(s['source'].startswith('doc:') for s in harness.context(owner,area,'Trabalho atual'))
    preview=browser.get('/api/ai/context',params={'thread_id':thread['id'],'q':'Trabalho atual','use_confirmed_focus':True}).json()
    assert [s['id'] for s in preview if s['source'].startswith('doc:')]==[doc]
    focus=next(s for s in preview if s['source']=='focus:1')
    assert focus['source_ids']==[doc] and focus['omitted_source_count']==1
    first=invoke(thread,owner,'Quero retomar Trabalho atual',use_confirmed_focus=True)
    assert any(s['source']=='doc:'+doc for s in first['sources'])
    assert 'contrato azul' in seen[-1]
    assert 'CONTEUDO_OUTRA_AREA' not in seen[-1] and 'PERFIL_FORA_DESTE_PEDIDO' not in seen[-1]
    second=invoke(thread,owner,'Outra dúvida sem foco')
    assert second['included_turn_count']==0 and second['skipped_history_count']==1
    assert not any(s['source']=='focus:1' for s in second['sources'])


def test_focus_change_and_pause_remove_previous_focus_history(ready,monkeypatch):
    browser,area,_,owner=ready
    doc=store(area,'FONTE_FOCO_ANTIGO para trabalho.','caderno.md')
    browser.put('/api/focus',json={'title':'Anterior','source_ids':[doc],'expected_revision':0})
    thread=conversations.create(conversations.ConversationCreate(),owner)
    seen=[]
    async def fake(settings,messages,schema):
        seen.append(json.dumps(messages))
        return answer('FONTE_FOCO_ANTIGO usada doc:'+doc)
    monkeypatch.setattr(harness,'call_provider',fake)
    invoke(thread,owner,'Retome o foco',use_confirmed_focus=True)
    browser.put('/api/documents/'+doc+'/state',json={'active':False})
    browser.put('/api/focus',json={'title':'Novo foco','source_ids':[],'expected_revision':1})
    result=invoke(thread,owner,'Continue foco atual',use_confirmed_focus=True)
    assert 'FONTE_FOCO_ANTIGO' not in seen[-1]
    assert result['skipped_history_count']==1 and result['included_turn_count']==0
    assert next(s for s in result['sources'] if s['source']=='focus:1')['revision']==2
