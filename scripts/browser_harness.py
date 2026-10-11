"""Deterministic HTTP test double, NOT a model quality benchmark or a real provider."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright, expect


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        context=json.loads(body['messages'][1]['content'])
        result={'choices':[{'finish_reason':'tool_calls','message':{'content':'Proposta de teste, ainda não executada.', 'tool_calls':[{'id':'test-call','type':'function','function':{'name':'propose_task','arguments':json.dumps({'title':'Tarefa confirmada pelo navegador','area_id':context['area_id']})}}]}}], 'usage':{'total_tokens':123}}
        data=json.dumps(result).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)


provider=ThreadingHTTPServer(('127.0.0.1',0),Provider)
threading.Thread(target=provider.serve_forever,daemon=True).start()
with socket.socket() as s:
    s.bind(('127.0.0.1',0))
    port=s.getsockname()[1]
with tempfile.TemporaryDirectory(prefix='mia-browser-fixture-') as data_dir:
    env={**os.environ,'MIA_DATA_DIR':data_dir,'MIA_AI_ENABLED':'true','MIA_AI_BASE_URL':f'http://127.0.0.1:{provider.server_port}/v1','MIA_AI_MODEL':'test-double','MIA_AI_API_KEY':'','MIA_AI_DAILY_CALL_LIMIT':'5'}
    server=subprocess.Popen([sys.executable,'-m','uvicorn','mia.app:app','--host','127.0.0.1','--port',str(port)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        url=f'http://127.0.0.1:{port}'
        for _ in range(50):
            try:
                urllib.request.urlopen(url+'/health',timeout=1).close()
                break
            except OSError: time.sleep(.1)
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page()
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(url)
            page.get_by_label('Seu nome').fill('Pessoa Teste')
            page.get_by_label('Senha local').fill('senha-teste-local-123')
            page.get_by_label('Primeira área',exact=True).fill('Projetos')
            page.get_by_role('button',name='Criar minha Mia').click()
            page.get_by_role('button',name='Inteligência',exact=True).click()
            page.get_by_label('Seu pedido').fill('Proponha uma tarefa')
            page.locator('input[name=consent]').check()
            page.get_by_role('button',name='Enviar pedido').click()
            confirm=page.get_by_role('button',name='Confirmar e criar tarefa')
            expect(confirm).to_be_visible()
            assert page.request.get(url+'/api/tasks').json()==[]
            page.reload()
            page.get_by_role('button',name='Inteligência',exact=True).click()
            page.get_by_role('button',name='Confirmar e criar tarefa').click()
            expect(page.get_by_text('Concluída',exact=True)).to_be_visible()
            assert len(page.request.get(url+'/api/tasks').json())==1
            page.get_by_label('Seu pedido').fill('Proponha outra tarefa')
            page.locator('input[name=consent]').check()
            page.get_by_role('button',name='Enviar pedido').click()
            page.get_by_role('button',name='Recusar',exact=True).click()
            expect(page.get_by_text('Recusada',exact=True)).to_be_visible()
            assert len(page.request.get(url+'/api/tasks').json())==1
            assert not errors, errors
            browser.close()
            print('Browser harness passed: real HTTP adapter against test double, proposal persisted, confirmation, rejection, no duplicate effects.')
    finally:
        server.terminate()
        server.wait(timeout=10)
        provider.shutdown()
