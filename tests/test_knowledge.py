import base64
import io
import json
import stat
import zipfile

import pytest
from fastapi.testclient import TestClient

from test_app import client, setup_payload


@pytest.fixture
def ready(client):
    browser,path=client
    browser.post('/api/setup',json=setup_payload())
    area=browser.get('/api/areas').json()[0]['id']
    return browser,area,path


def upload(browser,area,raw,name='nota.md'):
    return browser.post('/api/imports',json={'filename':name,'area_id':area,'content_base64':base64.b64encode(raw).decode()})


def confirm(browser,batch):
    return browser.post('/api/imports/'+batch['id']+'/confirm',json={'item_ids':[i['id'] for i in batch['items']]})


def test_review_confirm_repeat_delete_and_export(ready):
    browser,area,_=ready
    raw='# Decisão\n\nLançamento previsto em novembro.'.encode()
    batch=upload(browser,area,raw).json()
    assert browser.get('/api/documents').json()==[]
    assert not browser.get('/api/search',params={'q':'novembro'}).json()['results']
    result=confirm(browser,batch).json()
    assert result['report']['imported']==1
    assert confirm(browser,batch).json()['report']['imported']==1
    again=upload(browser,area,raw).json()
    assert confirm(browser,again).json()['report']['duplicates']==1
    docs=browser.get('/api/documents').json()
    assert len(docs)==1
    assert browser.get('/api/search',params={'q':'NOVEMBRO'}).json()['results'][0]['id']==docs[0]['id']
    context=browser.get('/api/ai/context',params={'area_id':area,'q':'lançamento novembro'}).json()
    assert any(s['source']=='doc:'+docs[0]['id'] for s in context)
    with zipfile.ZipFile(io.BytesIO(browser.get('/api/export').content)) as archive:
        exported=json.loads(archive.read('mia-export.json'))
        assert exported['documents'][0]['content']==raw.decode()
    browser.delete('/api/imports/'+batch['id'])
    assert len(browser.get('/api/documents').json())==1
    browser.delete('/api/imports/'+again['id'])
    assert browser.get('/api/documents').json()==[]
    assert browser.get('/api/documents/'+docs[0]['id']).status_code==404
    assert not browser.get('/api/search',params={'q':'novembro'}).json()['results']


def test_scopes_cancel_and_resume(ready):
    browser,area,_=ready
    batch=upload(browser,area,b'# Private\nSecret context').json()
    with TestClient(browser.app) as restarted:
        restarted.post('/api/login',json={'password':'senha-forte-123'})
        assert restarted.get('/api/imports/'+batch['id']).json()['state']=='review'
        assert confirm(restarted,batch).status_code==200
    other=browser.post('/api/areas',json={'name':'Outra'}).json()['id']
    assert all(not s['source'].startswith('doc:') for s in browser.get('/api/ai/context',params={'area_id':other,'q':'Secret'}).json())
    anon=TestClient(browser.app)
    assert anon.get('/api/imports').status_code==401
    assert anon.get('/api/documents').status_code==401
    assert browser.delete('/api/imports/'+batch['id'],headers={'Origin':'https://wrong.example'}).status_code==403


@pytest.mark.parametrize('name,mode',[('../bad.md',None),('/bad.md',None),('bad\\name.md',None),('link.md','link')])
def test_bad_zip_paths_and_links(ready,name,mode):
    browser,area,_=ready
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive:
        info=zipfile.ZipInfo(name)
        if mode=='link': info.external_attr=(stat.S_IFLNK|0o777)<<16
        archive.writestr(info,'text')
    assert upload(browser,area,buffer.getvalue(),'vault.zip').status_code==422
    assert browser.get('/api/imports').json()==[]


def test_partial_zip_reports_and_selection(ready):
    browser,area,_=ready
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive:
        archive.writestr('good.md','# Good\nUseful source')
        archive.writestr('bad.txt',b'\xff')
        archive.writestr('.obsidian/settings.json','{"private":true}')
        archive.writestr('photo.png',b'binary')
    batch=upload(browser,area,buffer.getvalue(),'vault.zip').json()
    assert len(batch['items'])==1
    assert len(batch['report']['errors'])==1
    assert len(batch['report']['ignored'])==2
    assert browser.post('/api/imports/'+batch['id']+'/confirm',json={'item_ids':['not-this-batch']}).status_code==422
    assert browser.delete('/api/imports/'+batch['id']).status_code==200
    assert browser.get('/api/documents').json()==[]


def test_chatgpt_current_branch_and_claude_roles(ready):
    browser,area,_=ready
    data=[{'title':'Example','current_node':'a','mapping':{
        'u':{'parent':None,'message':{'author':{'role':'user'},'content':{'parts':['Question']}}},
        'a':{'parent':'u','message':{'author':{'role':'assistant'},'content':{'parts':['Answer selected']}}},
        'discarded':{'parent':'u','message':{'author':{'role':'assistant'},'content':{'parts':['Old discarded answer']}}}
    }}]
    batch=upload(browser,area,json.dumps(data).encode(),'conversations.json').json()
    assert batch['items'][0]['kind']=='chatgpt'
    assert '[user' in batch['items'][0]['preview'] and '[assistant' in batch['items'][0]['preview']
    assert 'discarded answer' not in batch['items'][0]['preview']
    confirm(browser,batch)
    claude=[{'name':'Example Claude','chat_messages':[{'sender':'human','text':'Question'},{'sender':'assistant','text':'Answer'}]}]
    batch=upload(browser,area,json.dumps(claude).encode(),'claude.json').json()
    assert batch['items'][0]['kind']=='claude'
    assert '[user' in batch['items'][0]['preview']
    assert upload(browser,area,b'{"email":"private"}','user.json').status_code==422


def test_onboarding_persisted_goal_and_safe_settings_errors(ready):
    browser,area,_=ready
    assert browser.put('/api/onboarding',json={'goal':'Meu objetivo','step':2}).status_code==200
    assert browser.get('/api/onboarding').json()['step']==2
    assert browser.get('/api/onboarding').json()['goal']=='Meu objetivo'
    bad=browser.put('/api/ai/config',json={'endpoint':'http://public.example','api_key':'secret-fixture'})
    assert bad.status_code==422
    assert 'secret-fixture' not in bad.text
