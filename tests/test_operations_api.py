from test_app import client, setup_payload


def test_operational_status_is_read_only_private_and_uncached(client, monkeypatch):
    browser, _ = client
    monkeypatch.delenv('MIA_OPERATIONS_ROOT', raising=False)
    assert browser.get('/api/operations').status_code == 401
    browser.post('/api/setup', json=setup_payload())
    response = browser.get('/api/operations')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['managed'] is False
    assert response.json()['app_version']
    assert browser.post('/api/operations', json={'command':'rm -rf /'}).status_code == 405


def test_unavailable_manager_state_is_explicit_without_paths(client, monkeypatch, tmp_path):
    browser, _ = client
    browser.post('/api/setup', json=setup_payload())
    private_root = tmp_path / 'private-installation'
    monkeypatch.setenv('MIA_OPERATIONS_ROOT', str(private_root))
    response = browser.get('/api/operations')
    assert response.json()['recovery_required'] is True
    assert str(private_root) not in response.text
