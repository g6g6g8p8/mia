"""Synthetic fixture for cross-machine backup validation. Never use real data."""
import argparse
import base64
import os
from pathlib import Path

from fastapi.testclient import TestClient

from mia.app import app
from mia.backup import snapshot,restore

parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['create','verify']);parser.add_argument('directory',type=Path)
args=parser.parse_args()
os.environ['MIA_AI_ENABLED']='false'
if args.mode=='create':
    if args.directory.exists(): raise SystemExit('Use um diretório novo')
    os.environ['MIA_DATA_DIR']=str(args.directory/'source')
    with TestClient(app) as client:
        assert client.post('/api/setup',json={'name':'Pessoa Sintética','password':'fixture-password-only','area_name':'Teste'}).status_code==201
        area=client.get('/api/areas').json()[0]['id']
        assert client.post('/api/tasks',json={'title':'Tarefa de restauração','area_id':area}).status_code==201
        batch=client.post('/api/imports',json={'filename':'nota.md','area_id':area,'content_base64':base64.b64encode(b'# Synthetic\nRestore evidence').decode()}).json()
        assert client.post('/api/imports/'+batch['id']+'/confirm',json={'item_ids':[batch['items'][0]['id']]}).status_code==200
    snapshot(args.directory/'snapshot.db')
    print('Synthetic snapshot ready')
else:
    target=args.directory/'restored';restore(args.directory/'snapshot.db',target)
    os.environ['MIA_DATA_DIR']=str(target)
    with TestClient(app) as client:
        assert client.get('/api/me').status_code==401
        assert client.post('/api/login',json={'password':'fixture-password-only'}).status_code==200
        assert client.get('/api/tasks').json()[0]['title']=='Tarefa de restauração'
        assert client.get('/api/documents').json()[0]['title']=='Synthetic'
    print('Cross-machine restoration passed: identity, tasks, knowledge, session reset.')
