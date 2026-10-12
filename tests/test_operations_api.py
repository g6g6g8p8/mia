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


def test_pending_operation_does_not_accept_mutations_before_commit(client, monkeypatch, tmp_path):
    browser, _ = client
    browser.post('/api/setup', json=setup_payload())
    private_root = tmp_path / 'managed'
    private_root.mkdir()
    journal = private_root / 'journal.json'
    journal.write_text('{"phase":"recovered-starting"}')
    monkeypatch.setenv('MIA_OPERATIONS_ROOT', str(private_root))
    assert browser.get('/health').status_code == 200
    assert browser.get('/api/status').status_code == 200
    assert browser.get('/api/tasks').json() == []
    response = browser.post('/api/tasks', json={'title':'Must wait for commit'})
    assert response.status_code == 503
    assert response.headers['cache-control'] == 'no-store'
    assert browser.get('/api/tasks').json() == []
    journal.unlink()
    assert browser.post('/api/tasks', json={'title':'Committed version'}).status_code == 201
