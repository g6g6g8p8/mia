import httpx
import pytest
from fastapi.testclient import TestClient

from test_app import client, setup_payload
from mia import connection


@pytest.fixture
def configured(client, monkeypatch):
    browser, _ = client
    browser.post('/api/setup', json=setup_payload())
    values = {'endpoint': 'https://provider.example.test/v1', 'model': 'test-model'}
    browser.put('/api/ai/config', json={**values, 'api_key': 'private-test-secret'})
    calls = []
    original = httpx.AsyncClient
    def install(handler):
        def inspect(request):
            calls.append(request)
            return handler(request)
        def factory(**kwargs):
            assert kwargs['follow_redirects'] is False
            assert kwargs['trust_env'] is False
            return original(**kwargs, transport=httpx.MockTransport(inspect))
        monkeypatch.setattr(connection.httpx, 'AsyncClient', factory)
    return browser, values, calls, install


def test_probe_is_authenticated_metadata_only_and_does_not_create_runs(configured):
    browser, values, calls, install = configured
    install(lambda r: httpx.Response(200, json={'data': [{'id': 'test-model'}]}))
    assert TestClient(browser.app).post('/api/ai/connection', json=values).status_code == 401
    assert browser.post('/api/ai/connection', json=values, headers={'Origin': 'https://wrong.example'}).status_code == 403
    assert browser.post('/api/ai/connection', json={**values, 'endpoint': 'https://other.example'}).status_code == 409
    assert calls == []
    response = browser.post('/api/ai/connection', json=values)
    assert response.json()['status'] == 'listed'
    assert 'private-test-secret' not in response.text
    assert len(calls) == 1
    request = calls[0]
    assert request.method == 'GET' and str(request.url) == values['endpoint'] + '/models'
    assert request.content == b''
    assert request.headers['authorization'] == 'Bearer private-test-secret'
    assert browser.get('/api/runs').json() == []
    assert browser.get('/api/ai/config').json()['enabled'] is False


@pytest.mark.parametrize('code,body,status', [
    (401, {'error': 'private-test-secret'}, 'denied'),
    (403, {}, 'denied'), (404, {}, 'unsupported'), (429, {}, 'unavailable'),
    (302, {}, 'unavailable'), (200, {'data': [{'id': 'other'}]}, 'not_listed'),
    (200, {'unexpected': 'private-test-secret'}, 'unsupported'),
])
def test_probe_safe_failures_and_alias_uncertainty(configured, code, body, status):
    browser, values, calls, install = configured
    install(lambda r: httpx.Response(code, json=body, headers={'Location': 'https://other.example/models'}))
    result = browser.post('/api/ai/connection', json=values)
    assert result.json()['status'] == status
    assert 'private-test-secret' not in result.text
    assert len(calls) == 1


@pytest.mark.parametrize('kind', ['timeout', 'invalid', 'large'])
def test_probe_bounded_and_sanitized(configured, kind):
    browser, values, calls, install = configured
    def reply(request):
        if kind == 'timeout':
            raise httpx.ReadTimeout('private-test-secret')
        return httpx.Response(200, content=b'x' * (2 * 1024 * 1024 + 1) if kind == 'large' else b'private-test-secret')
    install(reply)
    result = browser.post('/api/ai/connection', json=values)
    assert result.json()['status'] in {'unavailable', 'unsupported'}
    assert 'private-test-secret' not in result.text
    assert len(calls) == 1
