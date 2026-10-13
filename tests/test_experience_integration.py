"""Integration acceptance of synthetic context migration and continuing work.

No participant data is read. A synthetic vault is deliberately larger than the
former 300-entry ceiling; passing it does not validate every real vault/export.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import time
import uuid
import zipfile

import pytest
from fastapi import HTTPException

from fastapi.testclient import TestClient

from scripts.browser_experience import (
    DECISION, EXCLUDED, PENDING, REVIEW_ONLY, chatgpt_fixture, claude_fixture,
    vault_fixture,
)
from test_app import client, setup_payload


def poll_job(browser, job_id, expected, timeout=45):
    deadline = time.monotonic() + timeout
    job = None
    while time.monotonic() < deadline:
        response = browser.get('/api/migrations/' + job_id)
        assert response.status_code == 200, response.text
        job = response.json()
        if job['state'] in expected:
            return job
        assert job['state'] not in {'failed', 'cancelled'}, job
        time.sleep(.02)
    raise AssertionError(f'Migration never reached {expected}: {job}')


def create_migration(browser, raw, filename, source_kind='files'):
    response = browser.post('/api/migrations', json={
        'filename': filename, 'size': len(raw),
        'sha256': hashlib.sha256(raw).hexdigest(), 'source_kind': source_kind,
    })
    assert response.status_code == 201, response.text
    return response.json()


def finish_upload(browser, raw, job_id, start=0):
    for offset in range(start, len(raw), 256 * 1024):
        response = browser.patch('/api/migrations/' + job_id + '/upload',
                                 params={'offset': offset},
                                 content=raw[offset:offset + 256 * 1024],
                                 headers={'Content-Type': 'application/octet-stream'})
        assert response.status_code == 200, response.text
    response = browser.post('/api/migrations/' + job_id + '/finish')
    assert response.status_code in {200, 202}, response.text
    return poll_job(browser, job_id, {'review'})


def confirm(browser, job_id, groups):
    response = browser.post('/api/migrations/' + job_id + '/confirm',
                            json={'groups': groups, 'excluded_ids': []})
    assert response.status_code in {200, 202}, response.text
    return poll_job(browser, job_id, {'completed', 'partial'})


def import_legacy_note(browser, area, filename, content, *, reviewed=True):
    response = browser.post('/api/imports', json={
        'area_id': area, 'filename': filename,
        'content_base64': base64.b64encode(content.encode()).decode(),
    })
    assert response.status_code == 201, response.text
    batch = response.json()
    if reviewed:
        confirmed = browser.post('/api/imports/' + batch['id'] + '/confirm',
                                 json={'item_ids': [item['id'] for item in batch['items']]})
        assert confirmed.status_code == 200, confirmed.text
        return next(doc for doc in browser.get('/api/documents').json()
                    if doc['path'] == filename)
    return batch


def test_large_vault_group_review_upload_resume_and_idempotent_sources(client):
    browser, _path = client
    assert browser.post('/api/setup', json=setup_payload()).status_code == 201
    raw = vault_fixture()
    job = create_migration(browser, raw, 'synthetic-vault.zip', 'obsidian')
    anonymous = TestClient(browser.app)
    assert anonymous.get('/api/migrations/' + job['id']).status_code == 401
    assert browser.patch('/api/migrations/' + job['id'] + '/upload',
                         params={'offset': 0}, content=b'x',
                         headers={'Origin': 'https://evil.example.test'}).status_code == 403
    from mia import migrations
    with pytest.raises(HTTPException) as denied:
        migrations.get_job(job['id'], {'id': 99})
    assert denied.value.status_code == 404
    half = min(len(raw) // 2, 256 * 1024)
    response = browser.patch('/api/migrations/' + job['id'] + '/upload',
                             params={'offset': 0}, content=raw[:half])
    assert response.status_code == 200, response.text

    # An application lifespan ends/restarts while transfer is incomplete.
    with TestClient(browser.app) as restarted:
        assert restarted.post('/api/login', json={'password': setup_payload()['password']}).status_code == 200
        resumable = restarted.get('/api/migrations/' + job['id']).json()
        assert resumable['received'] == half
        assert restarted.get('/api/documents').json() == []
        review = finish_upload(restarted, raw, job['id'], half)
        assert review['state'] == 'review'
        assert len(review['items']) <= 100, 'Inventory must be paginated'
        assert restarted.get('/api/documents').json() == [], 'Inventory is not authorization'
        completed = confirm(restarted, job['id'], ['Vault/Projetos/Aurora'])
        assert completed['state'] in {'completed', 'partial'}
        documents = restarted.get('/api/documents').json()
        assert len(documents) == 1000
        assert all(doc['path'].startswith('Vault/Projetos/Aurora/') for doc in documents)
        assert restarted.get('/api/search', params={'q': EXCLUDED}).json()['results'] == []
        assert restarted.get('/api/search', params={'q': 'Aurora'}).json()['results']
        assert restarted.get('/api/tasks').json() == [], 'Imports do not infer tasks'
        replay = restarted.post('/api/migrations/' + job['id'] + '/confirm',
                                json={'groups': ['Vault/Projetos/Aurora'], 'excluded_ids': []})
        assert replay.status_code == 200, replay.text
        assert len(restarted.get('/api/documents').json()) == 1000


def test_export_adapters_preserve_selected_conversation_roles_and_dates(client):
    browser, _path = client
    browser.post('/api/setup', json=setup_payload())
    job_ids = []
    for filename, raw, kind in [('conversations.json', chatgpt_fixture(), 'chatgpt'),
                                ('claude.json', claude_fixture(), 'claude')]:
        job = create_migration(browser, raw, filename, kind)
        job_ids.append(job['id'])
        finish_upload(browser, raw, job['id'])
        confirm(browser, job['id'], ['*'])
    documents = browser.get('/api/documents').json()
    assert {doc['kind'] for doc in documents} == {'chatgpt', 'claude'}
    content = [browser.get('/api/documents/' + doc['id']).json()['content'] for doc in documents]
    combined = '\n'.join(content)
    assert DECISION in combined and PENDING in combined
    assert '[user' in combined and '[assistant' in combined
    assert '2030' in combined or '1893456000' in combined
    assert 'UNSELECTED_CHATGPT_BRANCH' not in combined
    assert browser.get('/api/tasks').json() == []
    exported = browser.get('/api/export')
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        payload = json.loads(archive.read('mia-export.json'))
    metadata = [json.loads(item['metadata_json']) for item in payload['migration_provenance']]
    by_format = {item['source']['format']: item for item in metadata}
    chatgpt = by_format['chatgpt']
    assert chatgpt['source']['ids']['id'] == 'synthetic-chatgpt-1'
    assert chatgpt['branch']['current_node'] == 'chosen'
    assert chatgpt['branch']['omitted_node_ids'] == ['other']
    assert [message['role'] for message in chatgpt['messages']] == ['user', 'assistant']
    assert [message['id'] for message in chatgpt['messages']] == ['human-message', 'assistant-message']
    assert chatgpt['messages'][0]['dates']['create_time'] == 1893456000
    claude = by_format['claude']
    assert claude['source']['ids']['uuid'] == 'synthetic-claude-1'
    assert claude['messages'][0]['original_role'] == 'human'
    assert claude['messages'][0]['dates']['created_at'] == '2030-01-01T12:00:00Z'
    legacy_ids = {batch['id'] for batch in browser.get('/api/imports').json()}
    assert not legacy_ids.intersection(job_ids), 'Current migrations were mislabeled as legacy imports'
    old_delete = browser.delete('/api/imports/' + job_ids[0])
    assert old_delete.status_code in {200, 409}, old_delete.text
    if old_delete.status_code == 200:
        assert browser.get('/api/migrations/' + job_ids[0]).status_code == 404
        assert len(browser.get('/api/documents').json()) == 1
    else:
        assert browser.get('/api/migrations/' + job_ids[0]).status_code == 200
        assert len(browser.get('/api/documents').json()) == 2


def test_continuation_consent_and_revocation_keep_unapproved_sources_out(client, monkeypatch):
    from mia import harness
    browser, _path = client
    browser.post('/api/setup', json=setup_payload())
    area = browser.get('/api/areas').json()[0]['id']
    doc = import_legacy_note(browser, area, 'aurora.md', '# Aurora\n' + DECISION)
    import_legacy_note(browser, area, 'not-approved.md', '# Segredo\n' + REVIEW_ONLY, reviewed=False)
    monkeypatch.setenv('MIA_AI_ENABLED', 'true')
    monkeypatch.setenv('MIA_AI_BASE_URL', 'https://synthetic-provider.example.test/v1')
    monkeypatch.setenv('MIA_AI_API_KEY', 'synthetic-not-a-real-key')
    monkeypatch.setenv('MIA_AI_MODEL', 'synthetic')
    monkeypatch.setenv('MIA_AI_DAILY_CALL_LIMIT', '3')
    seen = []

    async def fake_provider(_settings, messages, _schema):
        seen.append(messages)
        return {'choices': [{'finish_reason': 'stop', 'message': {
            'content': 'Resposta sintética: ' + DECISION + ' doc:' + doc['id']}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}}

    monkeypatch.setattr(harness, 'call_provider', fake_provider)
    thread = browser.post('/api/conversations', json={'title': 'Retomar Aurora'}).json()
    from mia import conversations, knowledge
    with pytest.raises(HTTPException) as denied:
        conversations.scope(thread['id'], {'id': 99})
    assert denied.value.status_code == 404
    assert knowledge.retrieve({'id': 99}, None, 'Aurora') == []
    payload = {'thread_id': thread['id'], 'message': 'Retomar Aurora com fontes',
               'consent': False, 'request_key': str(uuid.uuid4())}
    assert browser.post('/api/runs', json=payload).status_code == 422
    assert not seen
    payload['consent'] = True
    first = browser.post('/api/runs', json=payload)
    assert first.status_code == 200, first.text
    assert first.json()['state'] == 'completed'
    assert first.json()['citations'] == ['doc:' + doc['id']]
    assert DECISION in json.dumps(seen, ensure_ascii=False)
    assert REVIEW_ONLY not in json.dumps(seen)
    replay = browser.post('/api/runs', json=payload)
    assert replay.json()['id'] == first.json()['id'] and len(seen) == 1
    assert browser.get('/api/tasks').json() == []

    browser.put('/api/documents/' + doc['id'] + '/state', json={'active': False})
    second = browser.post('/api/runs', json={**payload, 'message': 'Continue sem a fonte pausada',
                                          'request_key': str(uuid.uuid4())})
    assert second.status_code == 200, second.text
    assert DECISION not in json.dumps(seen[-1], ensure_ascii=False), 'Revoked source leaked through previous model answer'
    assert REVIEW_ONLY not in json.dumps(seen[-1]), 'Unreviewed source entered the conversation'
    assert not any(source['source'] == 'doc:' + doc['id'] for source in second.json()['sources'])
    conversation = browser.get('/api/conversations/' + thread['id']).json()
    assert len(conversation['runs']) == 2
    anonymous = TestClient(browser.app)
    assert anonymous.get('/api/conversations/' + thread['id']).status_code == 401
    assert browser.patch('/api/conversations/' + thread['id'], json={'title': 'Denied'},
                         headers={'Origin': 'https://evil.example.test'}).status_code == 403


def test_today_with_confirmed_focus_needs_no_inferred_tasks(client):
    browser, _path = client
    browser.post('/api/setup', json=setup_payload())
    area = browser.get('/api/areas').json()[0]['id']
    doc = import_legacy_note(browser, area, 'aurora-focus.md', '# Aurora\n' + DECISION + '\n' + PENDING)
    initial = browser.get('/api/experience').json()
    response = browser.put('/api/focus', json={
        'title': 'Continuar Aurora', 'source_ids': [doc['id']],
        'expected_revision': initial['focus']['revision'],
    })
    assert response.status_code == 200, response.text
    assert response.json()['source_ids'] == [doc['id']]
    assert browser.get('/api/tasks').json() == []
    today = browser.get('/api/today').json()
    assert browser.get('/api/experience').json()['focus']['title'] == 'Continuar Aurora'
    assert today['tasks'] == []
    stale = browser.put('/api/focus', json={
        'title': 'Stale edit', 'source_ids': [],
        'expected_revision': initial['focus']['revision'],
    })
    assert stale.status_code == 409, 'Concurrent focus edits must preserve the reviewed state'
    browser.put('/api/documents/' + doc['id'] + '/state', json={'active': False})
    focus = browser.get('/api/experience').json()['focus']
    assert focus['source_ids'] == [] and focus['unavailable_sources'] == 1
    anonymous = TestClient(browser.app)
    assert anonymous.get('/api/experience').status_code == 401
    assert browser.put('/api/focus', json={
        'title': 'Cross-origin', 'source_ids': [], 'expected_revision': focus['revision'],
    }, headers={'Origin': 'https://evil.example.test'}).status_code == 403
