"""Disposable browser test for M3 with synthetic knowledge; no real model or data."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright,expect

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
            assert not errors,errors
            browser.close()
            print('M3 browser passed: mobile onboarding, persisted goal/step, import preview, conflicts/comparison, pause/resume, selection, local search, original source, AI disabled config, deletion.')
    finally:
        server.terminate();server.wait(timeout=10)
