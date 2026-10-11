import json
import uuid

import pytest
from fastapi.testclient import TestClient

from test_app import client, setup_payload
from mia import harness


@pytest.fixture
def ready(client, monkeypatch):
    browser, path = client
    browser.post('/api/setup', json=setup_payload())
    area = browser.get('/api/areas').json()[0]['id']
    monkeypatch.setenv('MIA_AI_ENABLED', 'true')
    monkeypatch.setenv('MIA_AI_BASE_URL', 'https://provider.example.test/v1')
    monkeypatch.setenv('MIA_AI_API_KEY', 'test-key-not-real')
    monkeypatch.setenv('MIA_AI_MODEL', 'test-model')
    monkeypatch.setenv('MIA_AI_DAILY_CALL_LIMIT', '2')
    return browser, area, path


def request(area):
    return {'request_key':str(uuid.uuid4()),'message':'Proponha uma tarefa','area_id':area,'consent':True}


def reply(area):
    return {'choices':[{'finish_reason':'tool_calls','message':{'content':'Proposta para revisar.', 'tool_calls':[{'function':{'name':'propose_task','arguments':json.dumps({'title':'Tarefa de teste','area_id':area})}}]}}], 'usage':{'total_tokens':200}}


def test_proposal_confirmation_idempotency_and_scope(ready, monkeypatch):
    browser, area, _ = ready
    other = browser.post('/api/areas', json={'name':'Outra área','description':'Conteúdo fora do escopo'}).json()
    seen=[]
    async def fake(settings,messages,schema):
        seen.append(messages)
        return reply(area)
    monkeypatch.setattr(harness,'call_provider',fake)
    payload=request(area)
    result=browser.post('/api/runs',json=payload).json()
    assert result['state']=='awaiting_confirmation'
    assert 'Conteúdo fora do escopo' not in json.dumps(seen)
    assert browser.get('/api/tasks').json()==[]
    assert browser.post('/api/runs',json=payload).json()['id']==result['id']
    assert len(seen)==1
    url='/api/runs/'+result['id']+'/approve'
    anonymous=TestClient(browser.app)
    assert anonymous.post(url).status_code==401
    assert browser.post(url,headers={'Origin':'https://wrong.example'}).status_code==403
    with TestClient(browser.app) as restarted:
        restarted.post('/api/login',json={'password':'senha-forte-123'})
        a=restarted.post(url).json()
        b=restarted.post(url).json()
        assert a['task_id']==b['task_id']
        assert len(restarted.get('/api/tasks').json())==1
    payload['message']='Outro pedido'
    assert browser.post('/api/runs',json=payload).status_code==409


def test_rejection_and_daily_limit(ready,monkeypatch):
    browser,area,_=ready
    async def fake(*args): return reply(area)
    monkeypatch.setattr(harness,'call_provider',fake)
    result=browser.post('/api/runs',json=request(area)).json()
    assert browser.post('/api/runs/'+result['id']+'/reject').json()['state']=='rejected'
    assert browser.post('/api/runs/'+result['id']+'/approve').status_code==409
    browser.post('/api/runs',json=request(area))
    assert browser.post('/api/runs',json=request(area)).status_code==429
    assert browser.get('/api/tasks').json()==[]


@pytest.mark.parametrize('kind',['tool','scope','malformed','timeout'])
def test_untrusted_output_and_failures_cannot_write(ready,monkeypatch,kind):
    browser,area,_=ready
    async def fake(*args):
        if kind=='timeout': raise TimeoutError('test-key-not-real')
        result=reply(area)
        fn=result['choices'][0]['message']['tool_calls'][0]['function']
        if kind=='tool': fn['name']='shell'
        if kind=='scope': fn['arguments']=json.dumps({'title':'Bad area','area_id':'not-allowed'})
        if kind=='malformed': fn['arguments']='invalid json'
        return result
    monkeypatch.setattr(harness,'call_provider',fake)
    result=browser.post('/api/runs',json=request(area)).json()
    assert result['state']=='failed'
    assert 'test-key-not-real' not in json.dumps(result)
    assert browser.get('/api/tasks').json()==[]


def test_disabled_consent_context_and_secrets(ready,monkeypatch):
    browser,area,_=ready
    monkeypatch.setenv('MIA_AI_ENABLED','false')
    assert browser.post('/api/runs',json=request(area)).status_code==409
    payload=request(area); payload['consent']=False
    assert browser.post('/api/runs',json=payload).status_code==422
    assert 'test-key-not-real' not in browser.get('/api/ai/config').text
    assert browser.get('/api/ai/context',params={'area_id':'missing'}).status_code==404
    monkeypatch.setenv('MIA_AI_BASE_URL','http://public.example/v1')
    monkeypatch.setenv('MIA_AI_ENABLED','true')
    assert browser.get('/api/ai/config').json()['enabled'] is False


def test_concurrent_requests_reserve_once(ready,monkeypatch):
    import asyncio
    import threading
    from concurrent.futures import ThreadPoolExecutor
    browser,area,_=ready
    entered=threading.Event()
    release=threading.Event()
    async def fake(*args):
        entered.set()
        while not release.is_set(): await asyncio.sleep(.01)
        return reply(area)
    monkeypatch.setattr(harness,'call_provider',fake)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(browser.post,'/api/runs',json=request(area))
        try:
            assert entered.wait(3)
            assert browser.post('/api/runs',json=request(area)).status_code==409
        finally: release.set()
        run=first.result().json()
        a=pool.submit(browser.post,'/api/runs/'+run['id']+'/approve')
        b=pool.submit(browser.post,'/api/runs/'+run['id']+'/approve')
        assert a.result().json()['task_id']==b.result().json()['task_id']
    assert len(browser.get('/api/tasks').json())==1


def test_interrupted_run_is_not_replayed(ready):
    from mia.db import transaction
    from mia.security import iso
    browser,area,_=ready
    with transaction() as db:
        db.execute("INSERT INTO runs(id,owner_id,request_key,request_json,state,model,endpoint,sources_json,created_at,updated_at) VALUES('interrupted',1,'key','{}','running','test','https://provider.example','[]',?,?)",(iso(),iso()))
    with TestClient(browser.app) as restarted:
        restarted.post('/api/login',json={'password':'senha-forte-123'})
        run=restarted.get('/api/runs').json()[0]
        assert run['state']=='failed'
        assert 'interrompida' in run['error']


def test_http_adapter_contract(monkeypatch):
    import asyncio
    import httpx
    real_client=httpx.AsyncClient
    seen=[]
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'Teste'}}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    result=asyncio.run(harness.call_provider({'endpoint':'https://provider.example/v1','model':'test','max_output_tokens':1000},[],{}))
    assert result['choices'][0]['message']['content']=='Teste'
    assert seen[0]['max_completion_tokens']==1000
    assert seen[0]['tools'][0]['function']['name']=='propose_task'


def priced_config(browser, budget='0.04'):
    return browser.put('/api/ai/config',json={'enabled':True,'endpoint':'https://provider.example.test/v1','model':'test-model','api_key':'secret-fixture','daily_budget_usd':budget,'input_usd_per_million':'1','output_usd_per_million':'2','daily_call_limit':20})


def test_budget_reservation_reconciliation_and_failed_unknown_usage(ready,monkeypatch):
    browser,area,path=ready
    assert priced_config(browser).status_code==200
    async def fake(*args):
        result=reply(area)
        result['usage']={'prompt_tokens':100,'completion_tokens':50,'total_tokens':150}
        return result
    monkeypatch.setattr(harness,'call_provider',fake)
    run=browser.post('/api/runs',json=request(area)).json()
    assert run['cost_status']=='estimated'
    assert run['charged_micro']==200
    assert run['reserved_micro']==34768
    async def failed(*args): raise TimeoutError()
    monkeypatch.setattr(harness,'call_provider',failed)
    failed_run=browser.post('/api/runs',json=request(area)).json()
    assert failed_run['state']=='failed'
    assert failed_run['charged_micro']==34768
    assert browser.post('/api/runs',json=request(area)).status_code==429
    assert 'secret-fixture' not in browser.get('/api/ai/config').text
    assert (path/'ai-settings.json').stat().st_mode & 0o777==0o600


def test_budget_blocks_before_network_and_credentials_do_not_follow_destination(ready,monkeypatch):
    browser,area,_=ready
    assert priced_config(browser,'0.001').status_code==200
    async def never(*args): raise AssertionError('Should not call')
    monkeypatch.setattr(harness,'call_provider',never)
    assert browser.post('/api/runs',json=request(area)).status_code==429
    assert browser.get('/api/runs').json()==[]
    assert browser.put('/api/ai/config',json={'enabled':True,'endpoint':'https://new.example/v1','model':'test'}).status_code==422


def test_provider_overrun_blocks_following_calls(ready,monkeypatch):
    browser,area,_=ready
    priced_config(browser,'1')
    async def fake(*args):
        result=reply(area)
        result['usage']={'prompt_tokens':40000,'completion_tokens':100,'total_tokens':40100}
        return result
    monkeypatch.setattr(harness,'call_provider',fake)
    run=browser.post('/api/runs',json=request(area)).json()
    assert run['state']=='failed' and run['cost_status']=='overrun'
    assert browser.post('/api/runs',json=request(area)).status_code==409
