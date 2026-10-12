import base64
import sqlite3

import pytest
from fastapi.testclient import TestClient

from test_app import client,setup_payload
from mia.backup import snapshot,restore,verify,copy_database


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
    verify(backup)
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


def test_invalid_database_is_rejected_without_partial_backup(tmp_path):
    source=sqlite3.connect(':memory:')
    try:
        with pytest.raises(ValueError,match='não é um backup'):
            copy_database(source,tmp_path/'invalid.db')
        assert not (tmp_path/'invalid.db').exists()
    finally:
        source.close()


def test_verify_rejects_broken_references(client,tmp_path):
    browser,_=client
    browser.post('/api/setup',json=setup_payload())
    backup=tmp_path/'broken.db';snapshot(backup)
    with sqlite3.connect(backup) as database:
        database.execute('UPDATE areas SET owner_id=999')
    with pytest.raises(ValueError,match='referências'):
        verify(backup)
    with pytest.raises(ValueError):
        restore(backup,tmp_path/'rejected')
    assert not (tmp_path/'rejected').exists()


def test_failed_restore_leaves_empty_destination(client,tmp_path,monkeypatch):
    browser,_=client
    browser.post('/api/setup',json=setup_payload())
    backup=tmp_path/'snapshot.db';snapshot(backup)
    def fail_link(*args):
        raise OSError('Simulated publication failure')
    monkeypatch.setattr('mia.backup.os.link',fail_link)
    target=tmp_path/'restored'
    with pytest.raises(OSError):restore(backup,target)
    assert list(target.iterdir())==[]
    verify(backup)


def test_snapshot_never_overwrites_existing_file(client,tmp_path):
    browser,_=client
    browser.post('/api/setup',json=setup_payload())
    existing=tmp_path/'existing.db';existing.write_bytes(b'keep')
    with pytest.raises(FileExistsError):snapshot(existing)
    assert existing.read_bytes()==b'keep'
