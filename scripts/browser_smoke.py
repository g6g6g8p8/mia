"""Disposable empty-install smoke; an explicit URL must also be disposable."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


@contextmanager
def installation():
    if len(sys.argv) > 1:
        yield sys.argv[1]
        return
    with tempfile.TemporaryDirectory(prefix='mia-browser-smoke-fixture-') as data:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = {**os.environ, 'MIA_DATA_DIR': data, 'MIA_AI_ENABLED': 'false',
               'MIA_COOKIE_SECURE': 'false'}
        url = f'http://127.0.0.1:{port}'
        with tempfile.TemporaryFile(mode='w+') as log:
            server = subprocess.Popen(
                [sys.executable, '-m', 'uvicorn', 'mia.app:app', '--host',
                 '127.0.0.1', '--port', str(port)], env=env,
                cwd=Path(__file__).resolve().parent.parent, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if server.poll() is not None:
                        log.seek(0)
                        raise RuntimeError('Fixture failed to start: ' + log.read())
                    try:
                        urllib.request.urlopen(url + '/health', timeout=1).close()
                        break
                    except OSError:
                        time.sleep(.1)
                else:
                    raise RuntimeError('Fixture did not become healthy within 15 seconds')
                yield url
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


with installation() as url:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=os.environ.get('MIA_BROWSER_EXECUTABLE'))
        page = browser.new_page(viewport={'width':1280,'height':900})
        errors=[]
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(url)
        expect(page.get_by_role('heading',name='Sua Mia começa vazia.')).to_be_visible()
        page.get_by_label('Seu nome').fill('Pessoa Teste')
        page.get_by_label('Senha local').fill('senha-teste-local-123')
        page.get_by_label('Primeira área',exact=True).fill('Projetos')
        page.get_by_role('button',name='Criar minha Mia').click()
        page.get_by_role('button',name='Ir para Hoje').click()
        expect(page.get_by_role('heading',name='O que pede atenção')).to_be_visible()
        page.get_by_role('button',name='+ Tarefa').click()
        page.get_by_label('Título',exact=True).fill('Verificar fluxo no navegador')
        page.get_by_role('button',name='Criar tarefa',exact=True).click()
        expect(page.locator('#task-dialog')).not_to_be_visible()
        expect(page.get_by_text('Verificar fluxo no navegador',exact=True)).to_be_visible()
        page.get_by_role('button',name='Áreas',exact=True).click()
        page.get_by_role('button',name='+ Área').click()
        page.locator('#area-form input[name=name]').fill('Estudos')
        page.get_by_role('button',name='Criar área',exact=True).click()
        expect(page.locator('#area-dialog')).not_to_be_visible()
        expect(page.get_by_role('heading',name='Estudos',exact=True)).to_be_visible()
        page.get_by_role('button',name='Busca',exact=True).click()
        page.get_by_placeholder('Busque tarefas e áreas…').fill('navegador')
        expect(page.locator('#results')).to_contain_text('Verificar fluxo no navegador')
        page.get_by_role('button',name='Inteligência',exact=True).click()
        expect(page.get_by_role('button',name='Enviar pedido')).to_be_disabled()
        page.get_by_role('button',name='Ver contexto que será enviado').click()
        expect(page.locator('#context-preview')).to_contain_text('source')
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile overflow'
        page.get_by_role('button',name='Hoje',exact=True).click()
        page.get_by_role('button',name='Concluir tarefa').click()
        expect(page.get_by_text('Nada exige atenção agora.',exact=False)).to_be_visible()
        page.get_by_role('button',name='Sair',exact=True).click()
        page.get_by_label('Senha',exact=True).fill('senha-teste-local-123')
        page.get_by_role('button',name='Entrar',exact=True).click()
        expect(page.get_by_role('heading',name='O que pede atenção')).to_be_visible()
        assert not errors, errors
        print('Browser smoke passed: onboarding, task, area, search, AI disabled, context, mobile, logout/login; no JS errors.')
        browser.close()
