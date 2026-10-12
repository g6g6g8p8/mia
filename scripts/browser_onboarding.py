"""Disposable browser test for M3 with synthetic knowledge; no real model or data."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright,expect

metadata_requests = []
class Catalog(BaseHTTPRequestHandler):
    def do_GET(self):
        metadata_requests.append(self.path)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"data":[{"id":"synthetic-local-model"}]}')
    def log_message(self, *args):
        pass

catalog = ThreadingHTTPServer(('127.0.0.1', 0), Catalog)
threading.Thread(target=catalog.serve_forever, daemon=True).start()

with socket.socket() as s:
    s.bind(('127.0.0.1',0));port=s.getsockname()[1]
with tempfile.TemporaryDirectory(prefix='mia-onboarding-fixture-') as data:
    env={**os.environ,'MIA_DATA_DIR':data,'MIA_AI_ENABLED':'false','MIA_COOKIE_SECURE':'false'}
    server=subprocess.Popen([sys.executable,'-m','uvicorn','mia.app:app','--host','127.0.0.1','--port',str(port)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        url=f'http://127.0.0.1:{port}'
        for _ in range(50):
            try: urllib.request.urlopen(url+'/health',timeout=1).close();break
            except OSError: time.sleep(.1)
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':390,'height':844})
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(url)
            page.get_by_label('Seu nome').fill('Pessoa Piloto')
            page.get_by_label('Senha local').fill('senha-teste-local-123')
            page.get_by_label('Primeira área',exact=True).fill('Projetos')
            page.get_by_role('button',name='Criar minha Mia').click()
            page.get_by_label('Seu primeiro objetivo').fill('Preparar lançamento')
            page.get_by_role('button',name='Continuar',exact=True).click()
            page.get_by_label('Escolher arquivo').set_input_files({'name':'plano.md','mimeType':'text/markdown','buffer':b'# Plano de teste\n\nO lancamento sera em novembro.'})
            page.get_by_role('button',name='Preparar importação').click()
            expect(page.locator('input[name=item]')).to_have_count(1)
            assert page.request.get(url+'/api/documents').json()==[]
            page.locator('input[name=item]').check()
            page.get_by_role('button',name='Confirmar selecionados').click()
            expect(page.get_by_text('1 novos · 0 duplicados · 0 não selecionados')).to_be_visible()
            page.get_by_role('button',name='Continuar',exact=True).click()
            page.reload()
            expect(page.get_by_role('heading',name='Escolha como usar a IA.')).to_be_visible()
            connection=page.get_by_label('Como você quer conectar a IA?')
            connection.select_option('openai')
            expect(page.get_by_label('Endereço base da API')).to_have_value('https://api.openai.com/v1')
            page.get_by_label('Modelo',exact=True).fill('synthetic-model')
            page.get_by_label('Chave própria').fill('synthetic-secret')
            connection.select_option('local')
            expect(page.get_by_label('Chave própria')).to_have_value('')
            expect(page.get_by_label('Modelo',exact=True)).to_have_value('')
            page.get_by_label('Endereço base da API').fill(f'http://127.0.0.1:{catalog.server_port}/v1')
            page.get_by_label('Modelo',exact=True).fill('synthetic-local-model')
            expect(page.get_by_role('button',name='Verificar conexão salva')).to_be_disabled()
            page.get_by_role('button',name='Salvar configuração').click()
            expect(page.get_by_text('Configuração salva. Nenhuma chamada foi feita.')).to_be_visible()
            assert metadata_requests == []
            page.get_by_role('button',name='Verificar conexão salva').click()
            expect(page.locator('#ai-check-result')).to_contain_text('identificador do modelo encontrado')
            assert metadata_requests == ['/v1/models']
            assert page.request.get(url+'/api/runs').json() == []
            page.reload()
            expect(connection).to_have_value('local')
            expect(page.get_by_label('Modelo',exact=True)).to_have_value('synthetic-local-model')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'AI setup mobile overflow'
            connection.select_option('none')
            page.get_by_role('button',name='Salvar configuração').click()
            expect(page.get_by_text('Configuração salva. Nenhuma chamada foi feita.')).to_be_visible()
            assert not page.request.get(url+'/api/ai/config').json()['enabled']
            page.get_by_role('button',name='Continuar',exact=True).click()
            expect(page.get_by_text('1 fontes disponíveis.',exact=False)).to_be_visible()
            page.get_by_role('button',name='Buscar nas minhas fontes').click()
            page.get_by_placeholder('Busque tarefas e áreas…').fill('novembro')
            expect(page.locator('#results')).to_contain_text('Plano de teste')
            page.get_by_role('button',name='Abrir fonte',exact=True).click()
            expect(page.locator('#source-dialog')).to_contain_text('novembro')
            page.get_by_role('button',name='Fechar fonte').click()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile overflow'
            page.get_by_role('button',name='Áreas',exact=True).click()
            page.get_by_role('button',name='Fontes',exact=True).click()
            page.get_by_label('Escolher arquivo').set_input_files({'name':'plano.md','mimeType':'text/markdown','buffer':b'# Plano revisado\n\nO lancamento sera em dezembro.'})
            page.get_by_role('button',name='Preparar importação').click()
            expect(page.get_by_text('Mesmo caminho, conteúdo diferente.',exact=False)).to_be_visible()
            page.get_by_role('button',name='Comparar com Plano de teste',exact=True).click()
            expect(page.locator('#source-dialog')).to_contain_text('novembro')
            page.get_by_role('button',name='Fechar fonte').click()
            page.on('dialog',lambda dialog:dialog.accept())
            page.get_by_role('button',name='Cancelar lote',exact=True).click()
            expect(page.get_by_role('button',name='Cancelar lote',exact=True)).to_have_count(0)
            page.get_by_role('button',name='Pausar fonte',exact=True).click()
            expect(page.get_by_role('heading',name='Fontes disponíveis (0)')).to_be_visible()
            assert not page.request.get(url+'/api/search?q=novembro').json()['results']
            page.reload()
            page.get_by_role('button',name='Áreas',exact=True).click()
            page.get_by_role('button',name='Fontes',exact=True).click()
            page.get_by_role('button',name='Reativar fonte',exact=True).click()
            expect(page.get_by_role('heading',name='Fontes disponíveis (1)')).to_be_visible()
            assert page.request.get(url+'/api/search?q=novembro').json()['results']
            page.get_by_role('button',name='Excluir lote e suas fontes').click()
            expect(page.get_by_role('heading',name='Fontes disponíveis (0)')).to_be_visible()
            page.get_by_role('button',name='Sistema',exact=True).click()
            page.get_by_role('button',name='Acesso à Mia',exact=True).click()
            page.get_by_label('Forma de acesso').select_option('remote')
            page.get_by_label('Endereço HTTPS preparado (opcional)').fill('https://mia.example.test')
            page.get_by_role('button',name='Salvar preferência de acesso').click()
            expect(page.get_by_text('Preferência salva. A rede não foi alterada.')).to_be_visible()
            page.get_by_role('button',name='Verificar conexão atual').click()
            expect(page.locator('#access-result')).to_contain_text('sessão autenticada')
            page.get_by_role('button',name='Sistema',exact=True).click()
            page.get_by_role('button',name='Acesso à Mia',exact=True).click()
            expect(page.get_by_label('Forma de acesso')).to_have_value('remote')
            expect(page.get_by_label('Endereço HTTPS preparado (opcional)')).to_have_value('https://mia.example.test')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Access mobile overflow'
            page.get_by_role('button',name='Sistema',exact=True).click()
            page.get_by_role('button',name='Backups',exact=True).click()
            page.get_by_label('Fazer backup automático a cada 24 horas').check()
            page.get_by_label('Quantas cópias manter').fill('2')
            page.get_by_role('button',name='Salvar política de backup').click()
            expect(page.get_by_label('Fazer backup automático a cada 24 horas')).to_be_checked()
            page.get_by_role('button',name='Criar backup agora').click()
            download=page.locator('a[href^="/api/backups/"]').first
            expect(download).to_be_visible()
            response=page.request.get(url+download.get_attribute('href'))
            assert response.status==200 and response.body().startswith(b'SQLite format 3')
            page.get_by_label('Fazer backup automático a cada 24 horas').uncheck()
            page.get_by_role('button',name='Salvar política de backup').click()
            expect(page.get_by_label('Fazer backup automático a cada 24 horas')).not_to_be_checked()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Backup mobile overflow'
            assert not errors,errors
            browser.close()
            print('M3 browser passed: mobile onboarding, persisted goal/step, import preview, conflicts/comparison, pause/resume, selection, local search, original source, AI disabled config, deletion.')
    finally:
        server.terminate();server.wait(timeout=10)
        catalog.shutdown();catalog.server_close()
