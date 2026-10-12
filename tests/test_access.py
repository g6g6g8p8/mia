import pytest
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
