import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from test_app import client
from test_harness import ready, priced_config
from test_organization import source, request
from mia import harness


def suggestion(doc, text='Pesquisa de plantas', quote='Pesquisa sobre plantas.'):
    return {'text':text,'evidence':[{'document_id':doc,'quote':quote}]}


def plan(doc):
    return {'context':suggestion(doc),'goal':suggestion(doc,'Organizar a pesquisa de plantas')}


def start(browser, area, doc):
    payload=request(area,[doc]);payload['purpose']='personalization'
    return browser.post('/api/runs',json=payload)


def provider(monkeypatch, proposal, seen=None):
    async def fake(settings,messages,schema):
        if seen is not None: seen.append((settings,messages,schema))
        return {'choices':[{'finish_reason':'tool_calls','message':{'content':'Sugestões para revisão, não fatos confirmados.','tool_calls':[{'function':{'name':'propose_personalization','arguments':json.dumps(proposal)}}]}}],'usage':{'prompt_tokens':100,'completion_tokens':200,'total_tokens':300}}
    monkeypatch.setattr(harness,'call_provider',fake)


def test_review_edit_partial_confirmation_restart_and_export(ready,monkeypatch):
    browser,area,_=ready
    doc=source(browser,area)
    source(browser,area,'Outra nota','SEGREDO_NAO_SELECIONADO')
    browser.put('/api/onboarding',json={'goal':'Objetivo declarado antes','step':3,'completed':True})
    seen=[];provider(monkeypatch,plan(doc),seen)
    run=start(browser,area,doc).json()
    assert run['state']=='awaiting_confirmation'
    assert 'SEGREDO_NAO_SELECIONADO' not in json.dumps(seen)
    assert 'Objetivo declarado antes' not in json.dumps(seen)
    assert seen[0][0]['_tool_name']=='propose_personalization'
    assert browser.get('/api/personalization').json()['text']==''
    assert browser.post('/api/runs/'+run['id']+'/approve').status_code==409
    accepted={'context':suggestion(doc,'Contexto editado pelo usuário'),'goal':None}
    url='/api/runs/'+run['id']+'/personalization/approve'
    assert TestClient(browser.app).post(url,json=accepted).status_code==401
    assert browser.post(url,json=accepted,headers={'Origin':'https://wrong.example'}).status_code==403
    with TestClient(browser.app) as restarted:
        restarted.post('/api/login',json={'password':'senha-forte-123'})
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(restarted.post,url,json=accepted)
            b=pool.submit(restarted.post,url,json=accepted)
            assert a.result().status_code==b.result().status_code==200
        assert restarted.get('/api/personalization').json()['revision']==1
    assert browser.post(url,json=plan(doc)).status_code==409
    current=browser.get('/api/personalization').json()
    assert current['text']=='Contexto editado pelo usuário'
    assert current['goal']=='Objetivo declarado antes'
    assert browser.get('/api/tasks').json()==[]
    assert len(browser.get('/api/areas').json())==1
    assert browser.get('/api/documents/'+doc).json()['area_id']==area
    with zipfile.ZipFile(io.BytesIO(browser.get('/api/export').content)) as archive:
        data=json.loads(archive.read('mia-export.json'))
        assert data['personal_context']['text']==current['text']
        assert data['runs'][0]['personalization_result']['accepted_plan']==accepted
        assert data['runs'][0]['proposal']==plan(doc)


@pytest.mark.parametrize('bad',['invented_quote','wrong_source','no_evidence','extra_field'])
def test_untrusted_personalization_cannot_write(ready,monkeypatch,bad):
    browser,area,_=ready;doc=source(browser,area)
    proposed=plan(doc)
    if bad=='invented_quote': proposed['context']['evidence'][0]['quote']='Texto que não consta no arquivo.'
    elif bad=='wrong_source': proposed['goal']['evidence'][0]['document_id']='unknown'
    elif bad=='no_evidence': proposed['context']['evidence']=[]
    else: proposed['shell']='execute'
    provider(monkeypatch,proposed)
    result=start(browser,area,doc).json()
    assert result['state']=='failed' and result['proposal'] is None
    assert browser.get('/api/personalization').json()['text']==''
    assert browser.get('/api/onboarding').json()['goal']==''


def test_newer_edits_are_preserved_and_unselected_field_can_change(ready,monkeypatch):
    browser,area,_=ready;doc=source(browser,area)
    provider(monkeypatch,plan(doc))
    run=start(browser,area,doc).json();url='/api/runs/'+run['id']+'/personalization/approve'
    assert browser.put('/api/personalization',json={'text':'Edição manual mais recente','expected_revision':0}).status_code==200
    assert browser.post(url,json=plan(doc)).status_code==409
    assert browser.put('/api/personalization',json={'text':'Texto antigo','expected_revision':0}).status_code==409
    assert browser.post(url,json={'context':None,'goal':plan(doc)['goal']}).status_code==200
    assert browser.put('/api/onboarding',json={'goal':'Edição de aba antiga','expected_goal_revision':0}).status_code==409
    assert browser.get('/api/personalization').json()['text']=='Edição manual mais recente'
    newer=start(browser,area,doc).json()
    browser.put('/api/onboarding',json={'goal':'Meta escrita depois da geração','step':2})
    assert browser.post('/api/runs/'+newer['id']+'/personalization/approve',json=plan(doc)).status_code==409
    assert browser.get('/api/onboarding').json()['goal']=='Meta escrita depois da geração'


def test_paused_source_rejection_and_shared_budget(ready,monkeypatch):
    browser,area,_=ready;doc=source(browser,area)
    priced_config(browser,'0.001')
    seen=[];provider(monkeypatch,plan(doc),seen)
    assert start(browser,area,doc).status_code==429 and not seen
    priced_config(browser,'0.04')
    run=start(browser,area,doc).json()
    assert run['charged_micro']==500
    browser.put('/api/documents/'+doc+'/state',json={'active':False})
    url='/api/runs/'+run['id']+'/personalization/approve'
    assert browser.post(url,json=plan(doc)).status_code==409
    assert browser.post('/api/runs/'+run['id']+'/reject').json()['state']=='rejected'
    browser.put('/api/documents/'+doc+'/state',json={'active':True})
    assert browser.post(url,json=plan(doc)).status_code==409


def test_personal_context_only_sent_when_explicitly_selected(ready,monkeypatch):
    browser,area,_=ready
    assert browser.put('/api/personalization',json={'text':'CONTEXTO_PESSOAL_CONFIRMADO','expected_revision':0}).status_code==200
    browser.put('/api/onboarding',json={'goal':'OBJETIVO_CONFIRMADO'})
    default=browser.get('/api/ai/context',params={'area_id':area}).json()
    assert 'CONTEXTO_PESSOAL_CONFIRMADO' not in json.dumps(default)
    explicit=browser.get('/api/ai/context',params={'area_id':area,'include_personal_context':True}).json()
    assert explicit[-1]['source']=='profile:1'
    assert explicit[-1]['goal']=='OBJETIVO_CONFIRMADO'
    seen=[]
    async def fake(settings,messages,schema):
        seen.append(messages)
        return {'choices':[{'finish_reason':'stop','message':{'content':'Resposta de teste profile:1'}}]}
    monkeypatch.setattr(harness,'call_provider',fake)
    from test_harness import request as assistant_request
    first=browser.post('/api/runs',json=assistant_request(area)).json()
    assert first['invalid_citations']==['profile:1']
    payload=assistant_request(area);payload['include_personal_context']=True
    second=browser.post('/api/runs',json=payload).json()
    assert second['citations']==['profile:1']
    assert 'CONTEXTO_PESSOAL_CONFIRMADO' not in json.dumps(seen[0])
    assert 'CONTEXTO_PESSOAL_CONFIRMADO' in json.dumps(seen[1])
    assert browser.put('/api/personalization',json={'text':'','expected_revision':1}).status_code==200
    assert browser.get('/api/personalization').json()['text']==''
    assert 'CONTEXTO_PESSOAL_CONFIRMADO' in json.dumps(browser.get('/api/runs').json())
