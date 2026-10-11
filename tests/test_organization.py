import base64
import io
import json
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from test_harness import ready, priced_config
from test_app import client
from mia import harness


def source(browser, area, title='Plano', text='Pesquisa sobre plantas.'):
    batch=browser.post('/api/imports',json={'area_id':area,'filename':title+'.md','content_base64':base64.b64encode(('# '+title+'\n'+text).encode()).decode()}).json()
    browser.post('/api/imports/'+batch['id']+'/confirm',json={'item_ids':[batch['items'][0]['id']]})
    return next(d['id'] for d in browser.get('/api/documents').json() if d['title']==title)


def request(area, docs):
    return {'request_key':str(uuid.uuid4()),'message':'Organize minhas fontes','area_id':area,'document_ids':docs,'purpose':'organization','consent':True}


def plan(docs, name='Botânica'):
    return {'areas':[{'name':name,'description':'Estudos de plantas, a revisar.','document_ids':docs}]}


def provider(monkeypatch, proposal, seen=None):
    async def fake(settings,messages,schema):
        if seen is not None: seen.append((settings,messages,schema))
        return {'choices':[{'finish_reason':'tool_calls','message':{'content':'Sugestão para revisar.', 'tool_calls':[{'function':{'name':'propose_organization','arguments':json.dumps(proposal)}}]}}], 'usage':{'prompt_tokens':100,'completion_tokens':200,'total_tokens':300}}
    monkeypatch.setattr(harness,'call_provider',fake)


def test_organization_edited_confirmation_scope_and_concurrent_replay(ready,monkeypatch):
    browser,area,_=ready
    doc=source(browser,area)
    untouched=source(browser,area,'Fora da seleção','NAO_ENVIAR')
    seen=[];provider(monkeypatch,plan([doc]),seen)
    payload=request(area,[doc])
    preview=browser.post('/api/organization/preview',json={'area_id':area,'document_ids':[doc]}).json()
    run=browser.post('/api/runs',json=payload).json()
    assert run['state']=='awaiting_confirmation'
    assert len(browser.get('/api/areas').json())==1
    assert browser.get('/api/documents/'+doc).json()['area_id']==area
    assert 'NAO_ENVIAR' not in json.dumps(seen)
    assert run['sources']==preview
    assert seen[0][0]['_tool_name']=='propose_organization'
    assert browser.post('/api/runs/'+run['id']+'/approve').status_code==409
    accepted=plan([doc],'Jardim e pesquisa')
    url='/api/runs/'+run['id']+'/organization/approve'
    assert TestClient(browser.app).post(url,json=accepted).status_code==401
    assert browser.post(url,json=accepted,headers={'Origin':'https://wrong.example'}).status_code==403
    with TestClient(browser.app) as restarted:
        restarted.post('/api/login',json={'password':'senha-forte-123'})
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(restarted.post,url,json=accepted)
            b=pool.submit(restarted.post,url,json=accepted)
            assert a.result().status_code==b.result().status_code==200
        done=restarted.post(url,json=accepted).json()
    new=done['organization_result']['created_areas'][0]['id']
    assert done['proposal']['areas'][0]['name']=='Botânica'  # Original proposal is preserved.
    assert done['organization_result']['accepted_plan']==accepted
    assert browser.post(url,json=plan([doc],'Outra escolha')).status_code==409
    assert browser.post('/api/runs',json=payload).json()['id']==run['id']
    assert len(seen)==1
    assert browser.get('/api/documents/'+doc).json()['area_id']==new
    assert browser.get('/api/documents/'+untouched).json()['area_id']==area
    assert any(s['source']=='doc:'+doc for s in browser.get('/api/ai/context',params={'area_id':new,'q':'plantas'}).json())
    assert all(s['source']!='doc:'+doc for s in browser.get('/api/ai/context',params={'area_id':area,'q':'plantas'}).json())
    assert browser.get('/api/tasks').json()==[]
    with zipfile.ZipFile(io.BytesIO(browser.get('/api/export').content)) as archive:
        data=json.loads(archive.read('mia-export.json'))
        assert data['runs'][0]['organization_result']['accepted_plan']==accepted


@pytest.mark.parametrize('change',['pause','delete','move'])
def test_stale_sources_cannot_be_applied(ready,monkeypatch,change):
    browser,area,_=ready
    doc=source(browser,area)
    provider(monkeypatch,plan([doc]))
    run=browser.post('/api/runs',json=request(area,[doc])).json()
    if change=='pause': browser.put('/api/documents/'+doc+'/state',json={'active':False})
    elif change=='delete': browser.delete('/api/imports/'+browser.get('/api/imports').json()[0]['id'])
    else:
        other=browser.post('/api/runs',json=request(area,[doc])).json()
        assert browser.post('/api/runs/'+other['id']+'/organization/approve',json=plan([doc],'Movida')).status_code==200
    count=len(browser.get('/api/areas').json())
    assert browser.post('/api/runs/'+run['id']+'/organization/approve',json=plan([doc])).status_code==409
    assert len(browser.get('/api/areas').json())==count


def test_invalid_selection_and_untrusted_plan_do_not_write(ready,monkeypatch):
    browser,area,_=ready
    doc=source(browser,area)
    provider(monkeypatch,plan(['invented-source']))
    assert browser.post('/api/runs',json=request(area,[])).status_code==422
    assert browser.post('/api/runs',json=request(area,[doc,doc])).status_code==422
    other=browser.post('/api/areas',json={'name':'Outra'}).json()['id']
    assert browser.post('/api/runs',json=request(other,[doc])).status_code==409
    payload=request(area,[doc]);payload['consent']=False
    assert browser.post('/api/runs',json=payload).status_code==422
    result=browser.post('/api/runs',json=request(area,[doc])).json()
    assert result['state']=='failed' and result['proposal'] is None
    assert len(browser.get('/api/areas').json())==2
    assert browser.get('/api/documents/'+doc).json()['area_id']==area


def test_partial_review_existing_names_and_rejection(ready,monkeypatch):
    browser,area,_=ready
    doc=source(browser,area)
    second=source(browser,area,'Outra nota','Estudo de árvores')
    proposed={'areas':plan([doc])['areas']+plan([second],'Árvores')['areas']}
    provider(monkeypatch,proposed)
    run=browser.post('/api/runs',json=request(area,[doc,second])).json()
    url='/api/runs/'+run['id']+'/organization/approve'
    assert browser.post(url,json=plan(['invented'])).status_code==422
    existing=browser.get('/api/areas').json()[0]['name'].upper()
    assert browser.post(url,json=plan([doc],existing)).status_code==409
    assert browser.post(url,json={'areas':plan([doc])['areas']+plan([doc],'Outra sugestão')['areas']}).status_code==422
    assert browser.post(url,json=plan([doc])).status_code==200
    assert browser.get('/api/documents/'+second).json()['area_id']==area
    provider(monkeypatch,plan([second],'Recusada'))
    rejected=browser.post('/api/runs',json=request(area,[second])).json()
    assert browser.post('/api/runs/'+rejected['id']+'/reject').json()['state']=='rejected'
    assert browser.post('/api/runs/'+rejected['id']+'/organization/approve',json=plan([second],'Recusada')).status_code==409


def test_organization_uses_shared_budget_and_limited_preview(ready,monkeypatch):
    browser,area,_=ready
    doc=source(browser,area,text='Árvore '*1000)
    preview=browser.post('/api/organization/preview',json={'area_id':area,'document_ids':[doc]}).json()
    assert len(preview[0]['content'].encode())<=1800 and preview[0]['truncated']
    priced_config(browser,'0.001')
    async def never(*args): raise AssertionError('No network call allowed')
    monkeypatch.setattr(harness,'call_provider',never)
    assert browser.post('/api/runs',json=request(area,[doc])).status_code==429
    assert browser.get('/api/runs').json()==[]
    priced_config(browser,'0.04')
    provider(monkeypatch,plan([doc]))
    run=browser.post('/api/runs',json=request(area,[doc])).json()
    assert run['charged_micro']==500 and run['cost_status']=='estimated'
