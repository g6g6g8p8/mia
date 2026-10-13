"""Confirmed first-work context survives export and restore without inference."""
import base64
import io
import json
import zipfile

from fastapi.testclient import TestClient

from mia.backup import restore, snapshot
from test_app import client, setup_payload


def source(browser):
    area = browser.get('/api/areas').json()[0]['id']
    batch = browser.post('/api/imports', json={
        'area_id':area, 'filename':'projeto.md',
        'content_base64':base64.b64encode('# Projeto\nDecisão: revisar o desenho.\nPendente: confirmar o prazo.'.encode()).decode(),
    }).json()
    assert browser.post('/api/imports/' + batch['id'] + '/confirm', json={'item_ids':[item['id'] for item in batch['items']]}).status_code == 200
    return browser.get('/api/documents').json()[0]


def test_first_setup_and_location_are_explicit_without_required_area(client, monkeypatch):
    browser, _ = client
    monkeypatch.delenv('MIA_INSTALLATION_MODE', raising=False)
    installation = browser.get('/api/installation').json()
    assert installation['mode'] == 'unknown'
    assert 'description' in installation and 'model_disclosure' in installation
    payload = setup_payload()
    payload.pop('area_name')
    payload.pop('area_description')
    assert browser.post('/api/setup', json=payload).status_code == 201
    assert browser.get('/api/areas').json()[0]['name'] == 'Minha biblioteca'
    assert browser.get('/api/experience').json()['library']['total'] == 0
    for mode in ('remote', 'local'):
        response = browser.put('/api/location', json={'mode':mode})
        assert response.status_code == 200
        assert browser.get('/api/experience').json()['location']['mode'] == mode
    assert browser.put('/api/location', json={'mode':'automatic'}).status_code == 422
    assert TestClient(browser.app).get('/api/experience').status_code == 401
    assert browser.put('/api/location', json={'mode':'local'}, headers={'Origin':'https://other.example.test'}).status_code == 403


def test_confirmed_focus_revision_and_revocation_preserve_provenance(client):
    browser, _ = client
    browser.post('/api/setup', json=setup_payload())
    doc = source(browser)
    payload = {'title':'Retomar o projeto', 'source_ids':[doc['id']], 'expected_revision':0}
    assert browser.put('/api/focus', json=payload).status_code == 200
    assert browser.put('/api/focus', json=payload).status_code == 409
    assert browser.get('/api/tasks').json() == []
    assert browser.get('/api/experience').json()['sources'][0]['id'] == doc['id']
    assert 'Decisão: revisar o desenho.' in browser.get('/api/experience').json()['sources'][0]['evidence_excerpt']
    browser.put('/api/documents/' + doc['id'] + '/state', json={'active':False})
    state = browser.get('/api/experience').json()
    assert state['focus']['title'] == 'Retomar o projeto'
    assert state['focus']['source_ids'] == [] and state['focus']['unavailable_sources'] == 1
    assert state['sources'] == [] and state['library']['paused'] == 1
    with zipfile.ZipFile(io.BytesIO(browser.get('/api/export').content)) as archive:
        exported = json.loads(archive.read('mia-export.json'))
    assert exported['focus']['source_ids'] == [doc['id']]
    assert exported['focus']['available_source_ids'] == []
    assert browser.put('/api/focus', json={**payload, 'expected_revision':1}).status_code == 409
    assert browser.put('/api/focus', json={**payload, 'expected_revision':1, 'source_ids':['other-owner-or-missing']}).status_code == 409


def test_focus_conversations_and_sources_survive_export_and_restore(client, tmp_path, monkeypatch):
    browser, _ = client
    browser.post('/api/setup', json=setup_payload())
    doc = source(browser)
    browser.put('/api/focus', json={'title':'Continuar o projeto', 'source_ids':[doc['id']], 'expected_revision':0})
    thread = browser.post('/api/conversations', json={'title':'Decisões do projeto'}).json()
    exported = browser.get('/api/export')
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        payload = json.loads(archive.read('mia-export.json'))
    assert payload['focus']['source_ids'] == [doc['id']]
    assert payload['conversations'][0]['id'] == thread['id']
    backup = tmp_path / 'saved.db'
    snapshot(backup)
    target = tmp_path / 'restored'
    restore(backup, target)
    monkeypatch.setenv('MIA_DATA_DIR', str(target))
    with TestClient(browser.app) as restored:
        assert restored.get('/api/experience').status_code == 401
        assert restored.post('/api/login', json={'password':setup_payload()['password']}).status_code == 200
        assert restored.get('/api/experience').json()['focus']['source_ids'] == [doc['id']]
        assert restored.get('/api/conversations/' + thread['id']).json()['title'] == 'Decisões do projeto'
        assert restored.get('/api/search', params={'q':'revisar desenho'}).json()['results']
