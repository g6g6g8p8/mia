"""Synthetic migration-to-work browser acceptance; never uses personal files or paid AI.

Run with the development Python and MIA_BROWSER_EXECUTABLE when the environment
provides system Chromium. Figures printed by this script describe this synthetic
corpus only; they do not validate a participant's vault or native Mac/iPhone.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import random
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PASSWORD = "synthetic-browser-password-123"
DECISION = "Decisão confirmada em fonte: manter o projeto Aurora com revisão humana."
PENDING = "Pendente para revisão: conferir a próxima experiência do projeto Aurora."
EXCLUDED = "EXCLUDED_ARCHIVE_MATERIAL"
REVIEW_ONLY = "UNAPPROVED_IMPORT_MATERIAL"


def vault_fixture(notes: int = 1500) -> bytes:
    """Deterministic many-folder corpus with explicit irrelevant/error entries."""
    stream = io.BytesIO()
    randomizer = random.Random(20261013)
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder in ("Vault/", "Vault/Projetos/", "Vault/Projetos/Aurora/", "Vault/Arquivo/"):
            archive.writestr(folder, b"")
        for index in range(notes):
            current = index < (notes * 2 // 3)
            folder = "Vault/Projetos/Aurora" if current else "Vault/Arquivo"
            marker = DECISION if current else EXCLUDED
            # Unique content avoids deduplication disguising the number imported.
            identifier = "".join(randomizer.choice("abcdef0123456789") for _ in range(80))
            text = (f"# {'Aurora' if current else 'Arquivo histórico'} {index:04d}\n\n"
                    f"{marker}\n\n{PENDING if current else 'Material antigo, sem foco confirmado.'}\n\n"
                    f"Identificador sintético {index}: {identifier}\n")
            archive.writestr(f"{folder}/nota-{index:04d}.md", text.encode())
        archive.writestr("Vault/.obsidian/app.json", '{"plugins": []}')
        archive.writestr("Vault/.git/config", "Synthetic ignored metadata")
        archive.writestr("__MACOSX/._vault", b"Synthetic metadata")
        archive.writestr("Vault/Midia/figura.png", b"not a real image")
        archive.writestr("Vault/Drive/documento.gdoc", '{"url":"https://example.test/no-fetch"}')
        archive.writestr("Vault/Erro/invalido.md", b"\xff\xfeinvalid utf8")
    return stream.getvalue()


def chatgpt_fixture() -> bytes:
    data = [{
        "id": "synthetic-chatgpt-1", "title": "Aurora: decisão registrada",
        "create_time": 1893456000, "update_time": 1893456060,
        "current_node": "chosen",
        "mapping": {
            "root": {"id": "root", "parent": None, "children": ["human"], "message": None},
            "human": {"id": "human", "parent": "root", "children": ["chosen", "other"], "message": {
                "id": "human-message", "author": {"role": "user"}, "create_time": 1893456000,
                "content": {"content_type": "text", "parts": [DECISION]}}},
            "chosen": {"id": "chosen", "parent": "human", "children": [], "message": {
                "id": "assistant-message", "author": {"role": "assistant"}, "create_time": 1893456060,
                "content": {"content_type": "text", "parts": ["Hipótese do assistente, não fato confirmado."]}}},
            "other": {"id": "other", "parent": "human", "children": [], "message": {
                "id": "unselected-message", "author": {"role": "assistant"}, "create_time": 1893456061,
                "content": {"content_type": "text", "parts": ["UNSELECTED_CHATGPT_BRANCH"]}}},
        },
    }]
    return json.dumps(data, ensure_ascii=False).encode()


def claude_fixture() -> bytes:
    data = [{
        "uuid": "synthetic-claude-1", "name": "Aurora: questão para revisar",
        "created_at": "2030-01-01T12:00:00Z", "updated_at": "2030-01-01T12:01:00Z",
        "chat_messages": [
            {"uuid": "synthetic-human", "sender": "human", "text": PENDING,
             "created_at": "2030-01-01T12:00:00Z"},
            {"uuid": "synthetic-assistant", "sender": "assistant", "text": "Uma sugestão histórica do assistente.",
             "created_at": "2030-01-01T12:01:00Z"},
        ],
    }]
    return json.dumps(data, ensure_ascii=False).encode()


class SyntheticProvider(BaseHTTPRequestHandler):
    """Actual local HTTP process boundary, deterministic response, no quality claim."""
    received: list[dict] = []

    def log_message(self, *_args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.received.append(body)
        current = json.loads(body["messages"][-1]["content"])
        sources = [source for source in current["context"] if source["source"].startswith("doc:")]
        citation = sources[0]["source"] if sources else ""
        answer = "Retomada sintética do projeto Aurora; confira a fonte. " + citation
        reply = {"choices": [{"finish_reason": "stop", "message": {"content": answer}}],
                 "usage": {"prompt_tokens": 200, "completion_tokens": 30, "total_tokens": 230}}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def wait_job(client, url: str, expected: set[str], timeout: float = 60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(url)
        assert response.status == 200, (response.status, response.text())
        job = response.json()
        if job["state"] in expected:
            return job
        assert job["state"] not in {"failed", "cancelled"}, job
        time.sleep(.1)
    raise AssertionError(f"Migration did not reach {expected}: {job}")


def main():
    from playwright.sync_api import expect, sync_playwright

    SyntheticProvider.received = []
    provider = ThreadingHTTPServer(('127.0.0.1', 0), SyntheticProvider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    with socket.socket() as bound:
        bound.bind(('127.0.0.1', 0))
        port = bound.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    with tempfile.TemporaryDirectory(prefix='mia-experience-synthetic-') as data_dir:
        log_path = Path(data_dir) / 'server.log'
        env = {**os.environ, 'MIA_DATA_DIR': data_dir, 'MIA_COOKIE_SECURE': 'false',
               'MIA_INSTALLATION_MODE': 'remote', 'MIA_AI_ENABLED': 'true',
               'MIA_AI_BASE_URL': f'http://127.0.0.1:{provider.server_port}/v1',
               'MIA_AI_MODEL': 'synthetic-model', 'MIA_AI_API_KEY': '',
               'MIA_AI_DAILY_CALL_LIMIT': '2'}
        env.pop('MIA_OPERATIONS_ROOT', None)
        log = log_path.open('wb')
        server = None
        peak_rss_kib = [0]
        monitoring = threading.Event()

        def launch_server():
            nonlocal server
            server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'mia.app:app',
                                       '--host', '127.0.0.1', '--port', str(port)],
                                      env=env, stdout=log, stderr=log)
            for _ in range(100):
                if server.poll() is not None:
                    raise AssertionError('Synthetic server failed: ' + log_path.read_text()[-4000:])
                try:
                    urllib.request.urlopen(url + '/health', timeout=1).close()
                    return
                except OSError:
                    time.sleep(.1)
            raise AssertionError('Synthetic server never became ready')

        def stop_server():
            if server and server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=10)

        def monitor_rss():
            while not monitoring.wait(.05):
                if server:
                    try:
                        text = Path(f'/proc/{server.pid}/status').read_text()
                        rss = next(line for line in text.splitlines() if line.startswith('VmRSS:'))
                        peak_rss_kib[0] = max(peak_rss_kib[0], int(rss.split()[1]))
                    except (OSError, StopIteration):
                        pass

        try:
            launch_server()
            monitor = threading.Thread(target=monitor_rss, daemon=True)
            monitor.start()
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True, executable_path=os.environ.get('MIA_BROWSER_EXECUTABLE'))
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(url)
                expect(page.get_by_text('No seu servidor', exact=True)).to_be_visible()
                assert page.get_by_label('Primeira área', exact=True).count() == 0
                page.get_by_label('Seu nome', exact=True).fill('Pessoa Sintética')
                page.locator('#setup-form input[name=password]').fill(PASSWORD)
                page.get_by_role('button', name='Criar minha Mia', exact=True).click()
                expect(page.locator('#migration-form')).to_be_visible()
                assert not SyntheticProvider.received, 'Onboarding must not call AI automatically'

                # Browser hashes must match trusted Python SHA-256 at padding
                # boundaries and for actual multi-chunk upload, not just ASCII.
                checksum_cases = [b'', b'a' * 55, b'a' * 56, b'a' * 64,
                                  'contexto com acentos: decisão'.encode(), b'x' * (1024 * 1024 + 67)]
                for payload in checksum_cases:
                    calculated = page.evaluate('''async bytes => {
                        const {fileChecksum} = await import('/assets/upload-files.js');
                        return await fileChecksum(new File([new Uint8Array(bytes)], 'synthetic.md'));
                    }''', list(payload))
                    assert calculated == hashlib.sha256(payload).hexdigest(), 'Browser checksum mismatch'

                raw = vault_fixture()
                begun = time.monotonic()
                page.locator('#migration-form input[name=file]').set_input_files(
                    {'name': 'synthetic-vault.zip', 'mimeType': 'application/zip', 'buffer': raw})
                page.get_by_role('button', name='Conferir material', exact=True).click()
                try:
                    expect(page.locator('#confirm-migration')).to_be_visible(timeout=60000)
                except AssertionError:
                    print('Synthetic migration diagnostic:', errors,
                          page.locator('#migration-transfer').inner_text(),
                          page.locator('#toast').inner_text(),
                          page.request.get(url + '/api/migrations').text()[:8000])
                    raise
                review_seconds = time.monotonic() - begun
                first_job = page.request.get(url + '/api/migrations').json()[0]
                assert page.request.get(url + '/api/documents').json() == []
                expect(page.locator('#migration-items article')).to_have_count(50)
                page.locator('#migration-next').click()
                expect(page.locator('#migration-prev')).to_be_enabled()
                page.locator('#migration-query').fill('nota-0000')
                expect(page.locator('#migration-items article')).to_have_count(1)
                page.locator('#migration-query').fill('')
                expect(page.locator('#migration-items article')).to_have_count(50)
                expect(page.locator('input[name=group][value="Vault/Arquivo"]')).to_be_checked()
                with page.expect_response(lambda response: response.url.endswith('/selection')
                                          and response.request.method == 'PUT'):
                    page.locator('input[name=group][value="Vault/Arquivo"]').uncheck()
                saved_selection = page.request.get(url + '/api/migrations/' + first_job['id']).json()
                assert 'Vault/Arquivo' not in saved_selection['selected_groups']
                page.reload()
                expect(page.locator('#confirm-migration')).to_be_visible()
                expect(page.locator('input[name=group][value="Vault/Arquivo"]')).not_to_be_checked()
                authorized = time.monotonic()
                page.locator('#confirm-migration').click()
                first_ready = None
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    documents = page.request.get(url + '/api/documents').json()
                    if documents and first_ready is None:
                        found = page.request.get(url + '/api/search?q=Aurora').json()['results']
                        if found:
                            first_ready = time.monotonic() - authorized
                    job = page.request.get(url + '/api/migrations/' + first_job['id']).json()
                    if job['state'] in {'completed', 'partial'}:
                        break
                    assert job['state'] != 'failed', job
                    time.sleep(.05)
                assert len(documents) == 1000, (len(documents), job)
                assert first_ready is not None and first_ready <= 60
                index_seconds = time.monotonic() - authorized
                assert page.request.get(url + '/api/search?q=' + EXCLUDED).json()['results'] == []
                assert not SyntheticProvider.received
                page.locator('#guide-next').click()
                expect(page.locator('#ai-form')).to_be_visible()
                page.locator('#guide-next').click()
                expect(page.locator('#focus-form')).to_be_visible()
                page.locator('#focus-title').fill('Aurora: primeiro foco confirmado')
                page.locator('#focus-source-query').fill('nota-0900')
                expect(page.locator('#focus-form input[name=source_ids]')).to_have_count(1)
                page.locator('#focus-form input[name=source_ids]').first.check()
                page.locator('#save-focus').click()
                expect(page.locator('#focus-saved')).to_contain_text('Foco confirmado')
                focused_ids = page.request.get(url + '/api/experience').json()['focus']['source_ids']
                assert len(focused_ids) == 1
                assert page.request.get(url + '/api/documents/' + focused_ids[0]).json()['path'].endswith('nota-0900.md')
                assert page.request.get(url + '/api/tasks').json() == []
                # Advancing must persist edits even when the person does not
                # click the separate save button a second time.
                page.evaluate('''() => {
                    const originalFetch = window.fetch; let delayed = false;
                    window.fetch = async (...args) => {
                        const response = await originalFetch(...args);
                        if (!delayed && String(args[0]) === '/api/focus' && args[1]?.method === 'PUT') {
                            delayed = true;
                            await new Promise(resolve => setTimeout(resolve, 1200));
                        }
                        return response;
                    };
                }''')
                page.locator('#focus-title').fill('Aurora: edição salva durante a digitação')
                page.locator('#save-focus').click()
                page.locator('#focus-title').fill('Retomar o projeto Aurora')
                page.locator('#guide-next').click()
                expect(page.get_by_role('heading', name='1000 fontes disponíveis para usar.')).to_be_visible()
                assert page.request.get(url + '/api/experience').json()['focus']['title'] == 'Retomar o projeto Aurora'
                page.locator('#guide-next').click()
                expect(page.get_by_role('heading', name='Retomar o projeto Aurora', exact=True)).to_be_visible()
                expect(page.get_by_role('heading', name='Minha migração', exact=True)).to_be_visible()
                expect(page.locator('#content')).to_contain_text('pendências')
                page.locator('#content [data-document]').first.click()
                expect(page.locator('#source-dialog')).to_contain_text(DECISION)
                page.get_by_role('button', name='Fechar fonte', exact=True).click()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Desktop overflow'
                screenshots = Path('/tmp/mia-experience-review')
                screenshots.mkdir(exist_ok=True)
                page.screenshot(path=str(screenshots / 'today-desktop.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile Today overflow'
                page.screenshot(path=str(screenshots / 'today-mobile.png'), full_page=True)

                # Actual server-process restart during an incomplete transfer.
                created = page.request.post(url + '/api/migrations', data={
                    'filename': 'resumed-vault.zip', 'size': len(raw),
                    'sha256': hashlib.sha256(raw).hexdigest(), 'source_kind': 'obsidian'})
                assert created.status == 201, created.text()
                resumed = created.json()
                offset = min(len(raw) // 2, 256 * 1024)
                uploaded = page.request.patch(url + '/api/migrations/' + resumed['id'] + '/upload?offset=0',
                                              data=raw[:offset], headers={'Content-Type': 'application/octet-stream'})
                assert uploaded.status == 200, uploaded.text()
                stop_server()
                launch_server()
                assert page.request.get(url + '/api/migrations/' + resumed['id']).json()['received'] == offset
                for position in range(offset, len(raw), 256 * 1024):
                    response = page.request.patch(url + '/api/migrations/' + resumed['id'] + '/upload?offset=' + str(position),
                                                 data=raw[position:position + 256 * 1024],
                                                 headers={'Content-Type': 'application/octet-stream'})
                    assert response.status == 200, response.text()
                assert page.request.post(url + '/api/migrations/' + resumed['id'] + '/finish').status == 200
                wait_job(page.request, url + '/api/migrations/' + resumed['id'], {'review'})
                confirmed = page.request.post(url + '/api/migrations/' + resumed['id'] + '/confirm',
                                              data={'groups': ['Vault/Projetos/Aurora'], 'excluded_ids': []})
                assert confirmed.status == 200, confirmed.text()
                wait_job(page.request, url + '/api/migrations/' + resumed['id'], {'completed', 'partial'})
                assert len(page.request.get(url + '/api/documents').json()) == 1000
                assert page.request.delete(url + '/api/migrations/' + resumed['id']).status == 200
                assert len(page.request.get(url + '/api/documents').json()) == 1000, 'Removing a duplicate batch erased independent sources'

                # Only local deterministic provider, actual HTTP calls. Budget,
                # consent and continuity are product behavior; answer quality is
                # not assessed by this test double.
                config = page.request.put(url + '/api/ai/config', data={
                    'enabled': True, 'endpoint': env['MIA_AI_BASE_URL'], 'model': 'synthetic-model',
                    'api_key': '', 'daily_call_limit': 2, 'daily_budget_usd': '0.04',
                    'input_usd_per_million': '1', 'output_usd_per_million': '2'})
                assert config.status == 200, config.text()
                page.reload()
                page.locator('#today-continue').click()
                page.locator('#conversation-start').click()
                expect(page.locator('#conversation-form')).to_be_visible()
                expect(page.locator('#conversation-form input[name=use_confirmed_focus]')).to_be_checked()
                page.locator('#conversation-form textarea[name=message]').fill('Que decisão foi registrada sobre Aurora?')
                page.locator('#conversation-preview').click()
                expect(page.locator('#conversation-context')).to_contain_text('Aurora')
                expect(page.locator('#conversation-context')).to_contain_text('focus:1')
                expect(page.locator('#conversation-context')).to_contain_text(focused_ids[0])
                assert not SyntheticProvider.received
                page.locator('#conversation-form button[type=submit]').click()
                assert not SyntheticProvider.received, 'Browser consent is required before dispatch'
                page.locator('#conversation-form input[name=consent]').check()
                page.locator('#conversation-form button[type=submit]').click()
                expect(page.locator('#conversation-messages article')).to_have_count(1, timeout=15000)
                assert len(SyntheticProvider.received) == 1
                run = page.request.get(url + '/api/runs').json()[0]
                assert run['state'] == 'completed' and run['cost_status'] == 'estimated'
                thread_id = run['thread_id']
                page.reload()
                page.locator('[data-view=conversations]').click()
                page.locator('[data-thread="' + thread_id + '"]').click()
                expect(page.locator('#conversation-messages article')).to_have_count(1)
                expect(page.locator('#conversation-form input[name=consent]')).not_to_be_checked()
                expect(page.locator('#conversation-form input[name=use_confirmed_focus]')).not_to_be_checked()
                page.locator('#conversation-form textarea[name=message]').fill('E como podemos continuar?')
                page.locator('#conversation-form input[name=use_confirmed_focus]').check()
                page.locator('#conversation-form input[name=consent]').check()
                page.locator('#conversation-form button[type=submit]').click()
                expect(page.locator('#conversation-messages article')).to_have_count(2, timeout=15000)
                assert any(message['role'] == 'assistant' for message in SyntheticProvider.received[-1]['messages'])
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile Conversations overflow'
                page.screenshot(path=str(screenshots / 'conversations-mobile.png'), full_page=True)
                third = page.request.post(url + '/api/runs', data={
                    'thread_id': thread_id, 'request_key': str(__import__('uuid').uuid4()),
                    'message': 'Pedido acima do limite', 'consent': True})
                assert third.status == 429 and len(SyntheticProvider.received) == 2
                # A deliberate test-only policy change permits a final request
                # to audit revocation at the actual HTTP process boundary.
                revised = page.request.put(url + '/api/ai/config', data={
                    'enabled': True, 'endpoint': env['MIA_AI_BASE_URL'], 'model': 'synthetic-model',
                    'api_key': '', 'daily_call_limit': 3, 'daily_budget_usd': '0.04',
                    'input_usd_per_million': '1', 'output_usd_per_million': '2'})
                assert revised.status == 200, revised.text()
                old_runs = page.request.get(url + '/api/conversations/' + thread_id).json()['runs']
                revoked = {source['id'] for turn in old_runs for source in turn['sources']
                           if source['source'].startswith('doc:')}
                assert revoked
                for identity in revoked:
                    assert page.request.put(url + '/api/documents/' + identity + '/state',
                                            data={'active': False}).status == 200
                last = page.request.post(url + '/api/runs', data={
                    'thread_id': thread_id, 'request_key': str(__import__('uuid').uuid4()),
                    'message': 'Continue sem as fontes pausadas', 'consent': True})
                assert last.status == 200 and last.json()['state'] == 'completed', last.text()
                assert len(SyntheticProvider.received) == 3
                assert DECISION not in json.dumps(SyntheticProvider.received[-1]['messages'], ensure_ascii=False)
                assert last.json()['skipped_history_count'] >= 1
                assert page.request.get(url + '/api/tasks').json() == []
                assert not errors, errors
                browser.close()
                print(json.dumps({
                    'corpus': 'synthetic-only', 'notes_received': 1500, 'notes_selected': 1000,
                    'zip_bytes': len(raw), 'upload_to_review_seconds': round(review_seconds, 3),
                    'first_authorized_search_seconds': round(first_ready, 3),
                    'index_seconds': round(index_seconds, 3), 'peak_sampled_api_rss_kib': peak_rss_kib[0],
                    'provider': 'local deterministic HTTP test double, 3 calls',
                    'browser': 'Chromium desktop and 390px mobile viewport, not Safari/iPhone hardware',
                    'checks': ['group selection persists reload', '1500-note inventory',
                               '1000 authorized sources', 'source original opens', 'Today with no tasks',
                               'focus source beyond initial 20 documents', 'partial migration remains visible',
                               'focus edits survive in-flight save + continue',
                               'process restart upload resume', 'dedup + shared-source preservation',
                               'browser SHA256 boundary vectors', 'conversation persistence + per-turn consent',
                               'history continuation', 'paused source + history revocation',
                               'budget call ceiling', 'no horizontal overflow'],
                    'screenshots': str(screenshots),
                }, ensure_ascii=False))
        finally:
            monitoring.set()
            stop_server()
            log.close()
            provider.shutdown()
            provider.server_close()


if __name__ == "__main__":
    main()
