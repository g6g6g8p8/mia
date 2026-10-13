import json
import socket
import subprocess
import sys

from pydantic import ValidationError
import pytest
from mia import access
from test_app import client, setup_payload


def test_access_preferences_are_private_and_persist(client):
    browser, data = client
    assert browser.get('/api/access/config').status_code == 401
    assert browser.put('/api/access/config', json={'mode':'remote'}).status_code == 401
    browser.post('/api/setup', json=setup_payload())
    assert browser.get('/api/access/config').json()['mode'] == 'computer'
    payload = {'mode':'remote','address':'https://mia.example.test:8443/'}
    assert browser.put('/api/access/config', json=payload).status_code == 200
    assert browser.get('/api/access/config').json()['address'] == 'https://mia.example.test:8443'
    assert (data/'access-settings.json').stat().st_mode & 0o777 == 0o600
    assert browser.put('/api/access/config',json=payload,headers={'Origin':'https://untrusted.example'}).status_code == 403


@pytest.mark.parametrize('address', ['http://mia.example','https://user:password@mia.example','https://mia.example/path','https://mia.example?secret=1','https://mia.example:invalid','javascript:alert(1)'])
def test_access_rejects_unsafe_addresses(client,address):
    browser,_ = client
    browser.post('/api/setup',json=setup_payload())
    assert browser.put('/api/access/config',json={'mode':'remote','address':address}).status_code == 422
    assert browser.get('/api/access/config').json()['address'] == ''


@pytest.mark.parametrize('address', [
    'https://mia.example{tls}', 'https://mia.example;evil', 'https://0.0.0.0',
    'https://[::]', 'https://224.0.0.1', 'https://[fe80::1%eth0]',
    'https://mia..example', 'https://-mia.example', 'https://mia.example:0',
    'https://mia.example:65536', 'https://mia.example\\evil',
])
def test_addresses_cannot_inject_proxy_configuration(address):
    with pytest.raises(ValidationError):
        access.AccessSettings(address=address)


def test_plan_previews_exact_changes_without_writes_or_network(tmp_path, monkeypatch):
    monkeypatch.setenv('MIA_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(access, 'save', lambda _: pytest.fail('Plan must not save preferences'))
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs: pytest.fail('Plan must not resolve DNS'))
    monkeypatch.setattr(socket, 'create_connection', lambda *args, **kwargs: pytest.fail('Plan must not connect'))
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('Plan must not start processes'))
    plan = access.prepare(access.AccessPlanInput(mode='lan', address='https://MIA.home:9443/',
                                               listen_address='192.168.1.20'))
    assert list(tmp_path.iterdir()) == []
    assert plan['status'] == {'plan':'prepared', 'infrastructure':'not_checked', 'access':'not_proven'}
    assert plan['address'] == 'https://mia.home:9443'
    config = plan['files']['Caddyfile']
    assert 'bind 192.168.1.20' in config
    assert 'https://localhost:8443' in config and 'bind 127.0.0.1' in config
    assert 'reverse_proxy 127.0.0.1:8123' in config
    assert 'skip_install_trust' in config and 'admin off' in config
    assert plan['files']['mia-access.env'] == 'MIA_COOKIE_SECURE=true\n'
    backend = plan['commands'][1]
    assert backend['argv'][-2:] == ['--forwarded-allow-ips', '127.0.0.1']
    assert backend['environment_additions'] == {'MIA_COOKIE_SECURE':'true'}


def test_computer_plan_does_not_reconfigure_existing_remote_access():
    plan = access.prepare(access.AccessPlanInput(mode='computer'))
    assert plan['changes'] == [] and plan['files'] == {} and plan['commands'] == []
    assert any('não desativa' in warning for warning in plan['warnings'])


@pytest.mark.parametrize('fields', [
    {'mode':'lan'}, {'mode':'remote','address':'https://mia.example.org','listen_address':'$(evil)'},
    {'mode':'remote','address':'https://mia.example.org','listen_address':'fe80::1%evil{'},
    {'mode':'remote','address':'https://mia.example.org','listen_address':'224.0.0.1'},
    {'mode':'lan','address':'https://mia.example:8123'},
    {'mode':'lan','address':'https://mia.example:8443'},
    {'mode':'lan','address':'https://mia.example','upstream_port':8443},
    {'mode':'lan','address':'https://mia.example','upstream_port':True},
    {'mode':'remote','address':'https://192.168.1.20','certificate':'public'},
    {'mode':'remote','address':'https://mia.local','certificate':'public'},
    {'mode':'remote','address':'https://mia.example.org','command':'touch /tmp/evil'},
])
def test_plan_rejects_ambiguous_or_executable_inputs(fields):
    with pytest.raises(ValidationError):
        access.AccessPlanInput.model_validate(fields)


def test_public_plan_uses_domain_validation_without_http_listener():
    plan = access.prepare(access.AccessPlanInput(mode='remote', address='https://mia.example.org',
                                               listen_address='0.0.0.0', certificate='public'))
    assert 'disable_http_challenge' in plan['files']['Caddyfile']
    assert 'auto_https disable_redirects' in plan['files']['Caddyfile']
    assert any('todas as interfaces' in item for item in plan['warnings'])
    assert any('CGNAT' in item for item in plan['warnings'])


def test_cli_exports_private_artifacts_and_never_overwrites(tmp_path):
    output = tmp_path / 'plan'
    args = [sys.executable, '-m', 'mia.access', '--mode', 'lan', '--address',
            'https://mia.local:9443', '--output-dir', str(output)]
    first = subprocess.run(args, capture_output=True, text=True, check=True)
    assert first.stdout == ''
    assert output.stat().st_mode & 0o777 == 0o700
    assert {file.name for file in output.iterdir()} == {'plan.json', 'Caddyfile', 'mia-access.env'}
    assert all(file.stat().st_mode & 0o777 == 0o600 for file in output.iterdir())
    original = (output / 'Caddyfile').read_text()
    assert json.loads((output / 'plan.json').read_text())['status']['access'] == 'not_proven'
    second = subprocess.run(args, capture_output=True, text=True)
    assert second.returncode != 0
    assert (output / 'Caddyfile').read_text() == original


def test_plan_endpoint_is_owner_only_and_origin_protected(client):
    browser, data = client
    payload = {'mode':'lan', 'address':'https://mia.local:9443'}
    assert browser.post('/api/access/plan', json=payload).status_code == 401
    browser.post('/api/setup', json=setup_payload())
    result = browser.post('/api/access/plan', json=payload)
    assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
    assert result.json()['status']['infrastructure'] == 'not_checked'
    assert browser.get('/api/access/config').json()['mode'] == 'computer'
    assert not (data / 'access-settings.json').exists()
    assert browser.post('/api/access/plan', json=payload,
                        headers={'Origin':'https://untrusted.example'}).status_code == 403
