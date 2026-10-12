import base64

import pytest
from fastapi.testclient import TestClient

from test_app import client,setup_payload
from mia.backup import snapshot,restore


def test_snapshot_restore_in_empty_install_preserves_knowledge_and_login(client,monkeypatch,tmp_path):
    browser,data=client
    browser.post('/api/setup',json=setup_payload())
    area=browser.get('/api/areas').json()[0]['id']
    browser.post('/api/tasks',json={'title':'Tarefa preservada','area_id':area})
    batch=browser.post('/api/imports',json={'filename':'fonte.md','area_id':area,'content_base64':base64.b64encode(b'# Source\nBackup proof').decode()}).json()
    browser.post('/api/imports/'+batch['id']+'/confirm',json={'item_ids':[batch['items'][0]['id']]})
    browser.put('/api/onboarding',json={'goal':'Objetivo preservado','completed':True,'step':3})
    browser.put('/api/personalization',json={'text':'Contexto confirmado preservado','expected_revision':0})
    backup=tmp_path/'snapshot.db';snapshot(backup)
    assert backup.stat().st_mode&0o777==0o600
    target=tmp_path/'restored';restore(backup,target)
    with pytest.raises(ValueError):restore(backup,target)
    monkeypatch.setenv('MIA_DATA_DIR',str(target))
    with TestClient(browser.app) as restarted:
        assert restarted.get('/api/me').status_code==401
        assert restarted.post('/api/login',json={'password':'senha-forte-123'}).status_code==200
        assert restarted.get('/api/tasks').json()[0]['title']=='Tarefa preservada'
        assert restarted.get('/api/documents').json()[0]['title']=='Source'
        assert restarted.get('/api/onboarding').json()['goal']=='Objetivo preservado'
        assert restarted.get('/api/personalization').json()['text']=='Contexto confirmado preservado'
        assert restarted.get('/api/personalization').json()['revision']==1
