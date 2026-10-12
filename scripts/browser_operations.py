"""Browser validation of operation/access controls using disposable synthetic state.

Operational metadata is a rendering fixture, not a native-update lifecycle test.
No application commands, networking changes, real sources, or model calls run.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import contextmanager

from playwright.sync_api import sync_playwright, expect


@contextmanager
def installation(operation_mode):
    with tempfile.TemporaryDirectory(prefix='mia-operations-browser-fixture-') as directory:
        root = Path(directory)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = {**os.environ, 'MIA_DATA_DIR': str(root / 'data'),
               'MIA_AI_ENABLED': 'false', 'MIA_COOKIE_SECURE': 'false'}
        env.pop('MIA_OPERATIONS_ROOT', None)
        if operation_mode != 'manual':
            operations = root / 'operations'
            operations.mkdir(mode=0o700)
            env['MIA_OPERATIONS_ROOT'] = str(operations)
            if operation_mode == 'managed':
                (operations / 'installation.json').write_text('{}')
                (operations / 'active.json').write_text(json.dumps({
                    'version': '0.2.0a10', 'release': 'releases/0.2.0a10-synthetic-browser-fixture',
                    'data': 'data/initial'}))
            else:
                (operations / 'installation.json').write_text('malformed synthetic state')
        with tempfile.TemporaryFile(mode='w+') as log:
            server = subprocess.Popen(
                [sys.executable, '-m', 'uvicorn', 'mia.app:app', '--host',
                 '127.0.0.1', '--port', str(port)], env=env,
                cwd=Path(__file__).resolve().parent.parent, stdout=log, stderr=log)
            url = f'http://127.0.0.1:{port}'
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


def operation_flow(page, url, mode):
    assert page.request.get(url + '/api/status').json()['configured'] is False
    assert page.request.get(url + '/api/operations').status == 401
    assert page.request.post(url + '/api/access/plan', data={'mode': 'computer'}).status == 401
    page.goto(url)
    page.get_by_label('Seu nome').fill('Pessoa Operações')
    page.get_by_label('Senha local').fill('senha-teste-local-123')
    page.get_by_label('Primeira área', exact=True).fill('Projetos')
    page.get_by_role('button', name='Criar minha Mia').click()
    page.get_by_role('button', name='Sistema', exact=True).click()
    page.get_by_role('button', name='Operação e atualização', exact=True).click()
    panel = page.locator('#operations-panel')
    expect(panel).to_contain_text('Versão em execução:')
    expect(panel).to_contain_text('As alterações posteriores ficam preservadas em separado')
    expect(panel).to_contain_text('Snapshots de operação incluem configuração e possíveis credenciais')
    response = page.request.get(url + '/api/operations')
    assert response.status == 200 and response.headers['cache-control'] == 'no-store'
    status = response.json()
    assert '/tmp/' not in response.text() and '/workspace/' not in response.text()
    if mode == 'manual':
        assert not status['managed'] and not status['recovery_required']
        expect(panel).to_contain_text('Instalação manual ou Docker.')
    elif mode == 'managed':
        assert status['managed'] and status['version'] == '0.2.0a10' and not status['recovery_required']
        expect(panel).to_contain_text('0.2.0a10-synthetic-browser-fixture')
        expect(panel).to_contain_text('Instalação nativa gerenciada.')
    else:
        assert status['managed'] and status['recovery_required'] and status['operation'] == 'state-unavailable'
        expect(panel.get_by_role('alert')).to_contain_text('operação incompleta ou estado indisponível')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Operations mobile overflow'
    page.get_by_role('button', name='Atualizar estado', exact=True).click()
    expect(page.locator('#operations-panel')).to_contain_text('Versão em execução:')
    assert page.request.post(url + '/api/operations', data={'command': 'never execute'}).status == 405
    assert page.request.get(url + '/api/tasks').json() == []
    assert page.request.get(url + '/api/runs').json() == []



def access_flow(page, url):
    page.get_by_role('button', name='Sistema', exact=True).click()
    page.get_by_role('button', name='Acesso à Mia', exact=True).click()
    preview = page.locator('#access-plan-preview')
    status = page.locator('#access-plan-result')
    prepare = page.get_by_role('button', name='Preparar plano sem aplicar', exact=True)
    prepare.click()
    expect(preview).to_contain_text('Nenhuma mudança de rede proposta')
    expect(preview).to_contain_text('acesso ainda não comprovado')
    page.get_by_label('Forma de acesso').select_option('lan')
    page.get_by_label('Endereço HTTPS preparado (opcional)').fill('https://192.0.2.10:9443')
    page.get_by_label('IP da interface onde o proxy escutará').fill('192.0.2.10')
    prepare.click()
    expect(status).to_contain_text('Prévia gerada.')
    expect(preview).to_contain_text('https://192.0.2.10:9443')
    expect(preview).to_contain_text('https://localhost:8443')
    expect(preview).to_contain_text('MIA_COOKIE_SECURE=true')
    expect(preview).to_contain_text('CA privada')
    assert page.request.get(url + '/api/access/config').json()['mode'] == 'computer', 'Preparing must not save preferences'
    with page.expect_download() as downloaded:
        page.get_by_role('button', name='Baixar plano completo', exact=True).click()
    plan = json.loads(Path(downloaded.value.path()).read_text())
    assert plan['status']['access'] == 'not_proven' and plan['status']['infrastructure'] == 'not_checked'
    assert plan['address'] == 'https://192.0.2.10:9443' and plan['mode'] == 'lan'
    assert 'bind 192.0.2.10' in plan['files']['Caddyfile']
    assert 'bind 127.0.0.1' in plan['files']['Caddyfile']
    assert plan['files']['mia-access.env'] == 'MIA_COOKIE_SECURE=true\n'
    with page.expect_download() as downloaded:
        page.get_by_role('button', name='Baixar Caddyfile', exact=True).click()
    assert Path(downloaded.value.path()).read_text() == plan['files']['Caddyfile']
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'LAN plan mobile overflow'
    page.get_by_role('button', name='Salvar preferência de acesso', exact=True).click()
    expect(page.locator('#access-saved')).to_contain_text('A rede não foi alterada.')
    page.get_by_role('button', name='Sistema', exact=True).click()
    page.get_by_role('button', name='Acesso à Mia', exact=True).click()
    expect(page.get_by_label('Forma de acesso')).to_have_value('lan')
    expect(page.get_by_label('Endereço HTTPS preparado (opcional)')).to_have_value('https://192.0.2.10:9443')
    page.get_by_label('Forma de acesso').select_option('remote')
    page.get_by_label('Endereço HTTPS preparado (opcional)').fill('https://mia.example.com')
    page.get_by_label('Certificado do endereço de destino').select_option('public')
    page.get_by_label('IP da interface onde o proxy escutará').fill('0.0.0.0')
    page.get_by_role('button', name='Preparar plano sem aplicar', exact=True).click()
    expect(page.locator('#access-plan-preview')).to_contain_text('CGNAT exige outra rota')
    expect(page.locator('#access-plan-preview')).to_contain_text('todas as interfaces')
    expect(page.locator('#access-plan-preview')).to_contain_text('ACME/TLS-ALPN')
    assert page.request.get(url + '/api/access/config').json()['mode'] == 'lan', 'Remote plan must not mutate saved preference'
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Remote plan mobile overflow'
    payload = {'mode': 'lan', 'address': 'https://192.0.2.10:9443'}
    response = page.request.post(url + '/api/access/plan', data=payload)
    assert response.status == 200 and response.headers['cache-control'] == 'no-store'
    assert page.request.post(url + '/api/access/plan', data=payload, headers={'Origin': 'https://unrelated.example'}).status == 403
    page.get_by_label('Porta HTTPS de recuperação local').fill('8123')
    page.get_by_role('button', name='Preparar plano sem aplicar', exact=True).click()
    expect(page.locator('#access-plan-result')).to_contain_text('Não foi possível preparar')
    expect(page.locator('#access-plan-preview')).to_be_empty()
    assert page.request.get(url + '/api/tasks').json() == []
    assert page.request.get(url + '/api/runs').json() == []


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get('MIA_BROWSER_EXECUTABLE'))
        try:
            for mode in ('manual', 'managed', 'corrupt'):
                with installation(mode) as url:
                    context = browser.new_context(viewport={'width': 390, 'height': 844})
                    try:
                        page = context.new_page()
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        operation_flow(page, url, mode)
                        if mode == 'manual':
                            access_flow(page, url)
                        assert not errors, errors
                    finally:
                        context.close()
        finally:
            browser.close()
    print('Operations browser passed: mobile manual/managed/corrupt status, recovery instructions, refresh, authentication, read-only API; LAN/public plans, downloads, preference isolation, conflicts/origin protection; no network changes and synthetic metadata only.')


if __name__ == '__main__':
    main()
