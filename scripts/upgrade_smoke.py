"""Offline upgrade/rollback rehearsal using isolated Git snapshots and synthetic data.

Run from a development environment with pytest/httpx dependencies installed:
python scripts/upgrade_smoke.py --baseline-ref <previous-commit>
Does not install dependencies or modify the live installation.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile


PHASE = r'''
import base64, os
from pathlib import Path
from fastapi.testclient import TestClient
from mia.app import app
from mia.backup import snapshot, restore
from mia.db import connect

phase=os.environ['MIA_TEST_PHASE']
root=Path(os.environ['MIA_TEST_ROOT'])
password='synthetic-upgrade-password'
if phase=='restore':
    restore(root/'before.db',root/'restored')
    print('Restored pre-upgrade snapshot into a separate empty directory')
    raise SystemExit(0)
with TestClient(app) as client:
    if phase=='create':
        assert client.post('/api/setup',json={'name':'Synthetic Upgrade','password':password,'area_name':'Pilot'}).status_code==201
        area=client.get('/api/areas').json()[0]['id']
        assert client.post('/api/tasks',json={'title':'Preserve this task','area_id':area}).status_code==201
        batch=client.post('/api/imports',json={'filename':'source.md','area_id':area,'content_base64':base64.b64encode(b'# Evidence\nSynthetic upgrade proof').decode()}).json()
        assert client.post('/api/imports/'+batch['id']+'/confirm',json={'item_ids':[batch['items'][0]['id']]}).status_code==200
        assert client.put('/api/onboarding',json={'goal':'Preserve this goal','step':3,'completed':True}).status_code==200
        (root/'session.txt').write_text(client.cookies.get('mia_session'))
        with connect() as db:
            db.execute("INSERT INTO runs(id,owner_id,request_key,request_json,state,model,endpoint,sources_json,created_at,updated_at,reserved_micro,charged_micro,cost_status) VALUES('interrupted',1,'synthetic-request','{}','running','synthetic','https://unused.example','[]','2030-01-01','2030-01-01',25,25,'reserved')")
        snapshot(root/'before.db')
        print('Baseline created: task, source, goal, session and interrupted reservation')
    else:
        if phase=='rollback':
            client.cookies.set('mia_session',(root/'session.txt').read_text())
            assert client.get('/api/me').status_code==401
            client.cookies.clear()
        assert client.post('/api/login',json={'password':password}).status_code==200
        assert len(client.get('/api/tasks').json())==1
        assert client.get('/api/tasks').json()[0]['title']=='Preserve this task'
        assert client.get('/api/documents').json()[0]['title']=='Evidence'
        assert client.get('/api/onboarding').json()['goal']=='Preserve this goal'
        with connect() as db:
            run=db.execute("SELECT * FROM runs WHERE id='interrupted'").fetchone()
            assert run['state']=='failed' and run['charged_micro']==25
            assert db.execute('SELECT count(*) FROM runs').fetchone()[0]==1
        if phase=='upgrade':
            assert client.put('/api/personalization',json={'text':'Synthetic confirmed context','expected_revision':0}).status_code==200
        if phase=='restart':
            assert client.get('/api/personalization').json()['text']=='Synthetic confirmed context'
        if phase=='rollback':
            with connect() as db:
                assert not db.execute("SELECT name FROM sqlite_master WHERE name='personal_context'").fetchone()
        print(phase+': identity, knowledge, goal, task count and interrupted budget verified')
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref',required=True,help='Commit of 0.2.0a3, before personal_context migration')
    args=parser.parse_args()
    repository=Path(__file__).resolve().parents[1]
    # Resolve dependencies before subprocess cwd changes; no network needed.
    dependency_paths=[str(Path(p).resolve()) for p in sys.path if p and Path(p).resolve()!=repository]
    with tempfile.TemporaryDirectory(prefix='mia-upgrade-') as temporary:
        root=Path(temporary)
        for name,ref in [('old',args.baseline_ref),('new','HEAD')]:
            archive=root/(name+'.tar')
            subprocess.run(['git','archive','--format=tar','--output',str(archive),ref],cwd=repository,check=True)
            with tarfile.open(archive) as source:
                source.extractall(root/name,filter='data')
        env={**os.environ,'MIA_AI_ENABLED':'false','MIA_COOKIE_SECURE':'false','MIA_TEST_ROOT':str(root)}
        for phase,version,directory in [('create','old','data'),('upgrade','new','data'),('restart','new','data'),('restore','new','unused'),('rollback','old','restored')]:
            env.update(MIA_TEST_PHASE=phase,MIA_DATA_DIR=str(root/directory),PYTHONPATH=os.pathsep.join([str(root/version),*dependency_paths]))
            subprocess.run([sys.executable,'-c',PHASE],cwd=root/version,env=env,check=True)
        print('PASS: isolated upgrade, restart and rollback; no live installation changed.')


if __name__=='__main__':
    main()
