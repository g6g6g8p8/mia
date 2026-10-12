import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor

from test_harness import ready, request, reply
from test_app import client
from mia import harness
from mia.backup import snapshot, restore


def test_review_keeps_original_scope_and_applies_once_after_restore(ready, monkeypatch, tmp_path):
    browser, area, data = ready
    async def provider(*args):
        return reply(area)
    monkeypatch.setattr(harness, 'call_provider', provider)
    run = browser.post('/api/runs', json=request(area)).json()
    url = '/api/runs/' + run['id'] + '/approve'
    edits = {'title': '  Tarefa revisada  ', 'notes': 'Escolha do proprietário', 'due_date': '2030-12-01', 'priority': 3}
    assert browser.post(url, json={'edits': {**edits, 'area_id': 'another'}}).status_code == 422
    assert browser.post(url, json={'edits': edits}, headers={'Origin': 'https://wrong.example'}).status_code == 403
    assert browser.get('/api/tasks').json() == []
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: browser.post(url, json={'edits': edits}), range(2)))
    assert all(result.status_code == 200 for result in results)
    assert results[0].json()['task_id'] == results[1].json()['task_id']
    original = results[0].json()['proposal']
    assert original['title'] == 'Tarefa de teste'
    applied = results[0].json()['task_result']
    assert applied == {**edits, 'title': 'Tarefa revisada', 'area_id': area}
    replay = browser.post(url, json={'edits': {**edits, 'title': 'Alteração posterior'}}).json()
    assert replay['task_result'] == applied
    tasks = browser.get('/api/tasks').json()
    assert len(tasks) == 1 and tasks[0]['title'] == 'Tarefa revisada'
    with zipfile.ZipFile(io.BytesIO(browser.get('/api/export').content)) as archive:
        exported = json.loads(archive.read('mia-export.json'))
    assert exported['runs'][0]['proposal'] == original
    assert exported['runs'][0]['task_result'] == applied
    snapshot(tmp_path / 'review.db')
    restore(tmp_path / 'review.db', tmp_path / 'restored')
    monkeypatch.setenv('MIA_DATA_DIR', str(tmp_path / 'restored'))
    from fastapi.testclient import TestClient
    with TestClient(browser.app) as restored:
        assert restored.get('/api/me').status_code == 401
        assert restored.post('/api/login', json={'password': 'senha-forte-123'}).status_code == 200
        assert restored.post(url).json()['task_result'] == applied
        assert len(restored.get('/api/tasks').json()) == 1


def test_review_validates_content_before_effect(ready, monkeypatch):
    browser, area, _ = ready
    async def provider(*args):
        return reply(area)
    monkeypatch.setattr(harness, 'call_provider', provider)
    run = browser.post('/api/runs', json=request(area)).json()
    url = '/api/runs/' + run['id'] + '/approve'
    for edits in ({'title': '   '}, {'title': 'Valid title', 'priority': 4}, {'title': 'Valid title', 'due_date': 'bad'}):
        assert browser.post(url, json={'edits': edits}).status_code == 422
    assert browser.get('/api/tasks').json() == []
    assert browser.post(url, json={}).json()['proposal']['title'] == 'Tarefa de teste'
