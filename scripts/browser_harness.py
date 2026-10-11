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
        if body['tools'][0]['function']['name']=='propose_organization':
            assert len(context['context'])==1 and context['context'][0]['kind']=='markdown'
            result['choices'][0]['message']['tool_calls'][0]['function']={'name':'propose_organization','arguments':json.dumps({'areas':[{'name':'Pesquisa','description':'Notas para pesquisar plantas.','document_ids':[context['context'][0]['id']]}]})}
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
            page.set_viewport_size({'width':390,'height':844})
            page.get_by_role('button',name='Áreas',exact=True).click()
            page.get_by_role('button',name='Fontes',exact=True).click()
            page.get_by_label('Escolher arquivo').set_input_files({'name':'plantas.md','mimeType':'text/markdown','buffer':b'# Pesquisa de plantas\n\nEstudar as plantas do jardim.'})
            page.get_by_role('button',name='Preparar importação').click()
            page.locator('input[name=item]').check()
            page.get_by_role('button',name='Confirmar selecionados').click()
            expect(page.get_by_role('heading',name='Fontes disponíveis (1)')).to_be_visible()
            page.get_by_role('button',name='Organizar minhas fontes',exact=True).click()
            page.locator('input[name=source]').check()
            page.get_by_role('button',name='Ver trechos que serão enviados').click()
            expect(page.locator('#organization-context')).to_contain_text('plantas do jardim')
            assert 'Tarefa confirmada' not in page.locator('#organization-context').inner_text()
            page.locator('input[name=consent]').check()
            page.get_by_role('button',name='Gerar sugestões de áreas').click()
            expect(page.get_by_text('Aguardando revisão',exact=True)).to_be_visible()
            assert len(page.request.get(url+'/api/areas').json())==1
            page.reload()
            page.get_by_role('button',name='Áreas',exact=True).click()
            page.get_by_role('button',name='Fontes',exact=True).click()
            page.get_by_role('button',name='Organizar minhas fontes',exact=True).click()
            page.get_by_label('Nome da área sugerida').fill('Pesquisa aplicada')
            page.get_by_label('Aplicar esta área').check()
            page.get_by_role('button',name='Conferir fonte',exact=True).click()
            expect(page.locator('#source-dialog')).to_contain_text('plantas do jardim')
            page.get_by_role('button',name='Fechar fonte').click()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Organization mobile overflow'
            page.get_by_role('button',name='Confirmar organização selecionada').click()
            expect(page.get_by_text('Áreas criadas: Pesquisa aplicada.',exact=True)).to_be_visible()
            areas=page.request.get(url+'/api/areas').json()
            assert len(areas)==2
            new=next(a for a in areas if a['name']=='Pesquisa aplicada')
            assert page.request.get(url+'/api/documents').json()[0]['area_id']==new['id']
            assert len(page.request.get(url+'/api/tasks').json())==1
            page.get_by_role('button',name='Áreas',exact=True).click()
            page.locator('article.area').filter(has=page.get_by_role('heading',name='Pesquisa aplicada',exact=True)).get_by_role('button',name='Editar área').click()
            page.locator('#area-dialog').get_by_label('Descrição').fill('Contexto revisado pelo usuário de teste.')
            page.get_by_role('button',name='Salvar área',exact=True).click()
            expect(page.get_by_text('Contexto revisado pelo usuário de teste.',exact=True)).to_be_visible()
            context=page.request.get(url+'/api/ai/context?area_id='+new['id']+'&q=plantas').json()
            assert context[0]['description']=='Contexto revisado pelo usuário de teste.'
            assert not errors, errors
            browser.close()
            print('Browser harness passed: HTTP test double, task confirmation/rejection, mobile organization preview, persisted proposal, edited confirmation, source moved, no automatic task.')
    finally:
        server.terminate()
        server.wait(timeout=10)
        provider.shutdown()
