from datetime import datetime, timedelta, timezone

import pytest
import time
from fastapi.testclient import TestClient

from test_app import client, setup_payload
from mia import backup_jobs
from mia.backup import restore


def test_enabled_schedule_runs_after_restart(monkeypatch,tmp_path):
    monkeypatch.setenv('MIA_DATA_DIR',str(tmp_path))
    from mia.app import app
    with TestClient(app) as browser:
        browser.post('/api/setup',json=setup_payload())
    backup_jobs.configure(backup_jobs.Policy(enabled=True,keep=2))
    with TestClient(app):
        for _ in range(50):
            if backup_jobs.status()['files']:
                break
            time.sleep(.02)
        assert len(backup_jobs.status()['files'])==1
    with TestClient(app):
        assert len(backup_jobs.status()['files'])==1


def test_backup_api_private_and_restorable(client,tmp_path):
    browser,data=client
    assert browser.get('/api/backups').status_code==401
    assert browser.post('/api/backups').status_code==401
    browser.post('/api/setup',json=setup_payload())
    assert browser.get('/api/backups').json()['enabled'] is False
    assert browser.put('/api/backups',json={'enabled':True,'keep':0}).status_code==422
    assert browser.put('/api/backups',json={'enabled':True},headers={'Origin':'https://wrong.example'}).status_code==403
    result=browser.post('/api/backups');assert result.status_code==200
    name=result.json()['files'][0]['name']
    response=browser.get('/api/backups/'+name)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    downloaded=tmp_path/'downloaded.db';downloaded.write_bytes(response.content)
    restore(downloaded,tmp_path/'restored')
    assert (tmp_path/'restored'/'mia.db').exists()
    assert browser.get('/api/backups/not-a-backup.db').status_code==404
    browser.post('/api/logout')
    assert browser.get('/api/backups/'+name).status_code==401


def test_schedule_retention_and_failed_copy_preserve_backups(client,monkeypatch):
    browser,data=client
    browser.post('/api/setup',json=setup_payload())
    start=datetime(2030,1,1,tzinfo=timezone.utc)
    assert backup_jobs.run(clock=start) is False
    backup_jobs.configure(backup_jobs.Policy(enabled=True,keep=2))
    assert backup_jobs.run(clock=start)
    assert not backup_jobs.run(clock=start+timedelta(hours=23))
    assert backup_jobs.run(clock=start+timedelta(days=1))
    unrelated=data/'auto-backups'/'manual.db';unrelated.write_bytes(b'untouched')
    assert backup_jobs.run(clock=start+timedelta(days=2))
    before=backup_jobs.status()['files']
    assert len(before)==2 and unrelated.read_bytes()==b'untouched'
    def fail(path): raise OSError('Synthetic disk failure')
    monkeypatch.setattr(backup_jobs,'snapshot',fail)
    with pytest.raises(OSError):backup_jobs.run(clock=start+timedelta(days=3))
    state=backup_jobs.status()
    assert state['error'] and state['files']==before
    assert state['last_success']==(start+timedelta(days=2)).isoformat()
    assert not backup_jobs.run(clock=start+timedelta(days=3,minutes=30))
    assert not list((data/'auto-backups').glob('.pending-*'))
    backup_jobs.configure(backup_jobs.Policy(enabled=False,keep=2))
    assert not backup_jobs.run(clock=start+timedelta(days=4))
