"""Validate a generated access plan on loopback with verified TLS and synthetic data.

Run with the Mia interpreter and a separately installed, trusted Caddy executable:
    .venv/bin/python scripts/https_access_rehearsal.py --caddy /path/to/caddy
No public listeners, DNS changes, installed trust roots, or real installation data.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import time

import httpx

# Permit running the source script from outside the checkout as well.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mia.access import AccessPlanInput, prepare


def ports(count: int) -> list[int]:
    held = []
    try:
        for _ in range(count):
            server = socket.socket()
            server.bind(('127.0.0.1', 0))
            held.append(server)
        return [server.getsockname()[1] for server in held]
    finally:
        for server in held:
            server.close()


def await_ready(check, processes, timeout=20):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        for process in processes:
            if process.poll() is not None:
                raise RuntimeError(f'Process exited unexpectedly: {process.returncode}')
        try:
            if check():
                return
        except (OSError, httpx.HTTPError) as exc:
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(f'Isolated service did not become ready: {last_error}')


def rehearse(caddy: Path) -> dict:
    backend_port, proxy_port, recovery_port = ports(3)
    plan = prepare(AccessPlanInput(mode='lan', address=f'https://localhost:{proxy_port}',
                                  upstream_port=backend_port, recovery_port=recovery_port))
    report = {'scenario': 'isolated-loopback-https', 'tls_verification': True,
              'public_access_tested': False, 'global_trust_changed': False, 'checks': []}
    with tempfile.TemporaryDirectory(prefix='mia-https-rehearsal-') as directory:
        root = Path(directory)
        env = {**os.environ, 'MIA_DATA_DIR': str(root / 'data'), 'MIA_COOKIE_SECURE': 'true',
               'MIA_AI_ENABLED': 'false', 'XDG_DATA_HOME': str(root / 'caddy-data'),
               'XDG_CONFIG_HOME': str(root / 'caddy-config')}
        config = root / 'Caddyfile'
        config.write_text(plan['files']['Caddyfile'])
        config.chmod(0o600)
        validation = subprocess.run([str(caddy), 'validate', '--config', str(config), '--adapter', 'caddyfile'],
                                    env=env, capture_output=True, text=True, timeout=30)
        if validation.returncode:
            raise RuntimeError(validation.stderr)
        report['checks'].append('generated Caddyfile validates')
        report['caddy_version'] = subprocess.check_output([str(caddy), 'version'], text=True).strip()
        logs = root / 'processes.log'
        processes = []
        try:
            with logs.open('w') as output:
                backend = [sys.executable, *plan['commands'][1]['argv'][1:]]
                processes.append(subprocess.Popen(backend, env=env, stdout=output, stderr=output))
                local = f'http://127.0.0.1:{backend_port}'
                await_ready(lambda: httpx.get(local + '/health', timeout=1).status_code == 200, processes)
                processes.append(subprocess.Popen([str(caddy), 'run', '--config', str(config), '--adapter', 'caddyfile'],
                                                  env=env, stdout=output, stderr=output))
                ca = root / 'caddy-data/caddy/pki/authorities/local/root.crt'
                await_ready(lambda: ca.exists(), processes)
                trust = ssl.create_default_context(cafile=str(ca))
                origin = f'https://localhost:{proxy_port}'
                with httpx.Client(base_url=origin, verify=trust, trust_env=False, timeout=3) as browser:
                    await_ready(lambda: browser.get('/health').status_code == 200, processes)
                    assert browser.get('/api/status').json()['configured'] is False
                    assert browser.get('/api/access/config').status_code == 401
                    payload = {'name': 'Ensaio HTTPS', 'email': 'https@example.test',
                               'timezone': 'America/Sao_Paulo', 'password': 'senha-sintetica-https',
                               'area_name': 'Ensaio', 'area_description': 'Somente fontes sintéticas'}
                    result = browser.post('/api/setup', json=payload, headers={'Origin': origin})
                    assert result.status_code == 201, result.text
                    cookie = result.headers['set-cookie'].lower()
                    assert 'secure' in cookie and 'httponly' in cookie and 'samesite=strict' in cookie
                    assert browser.get('/api/me').status_code == 200
                    report['checks'].append('empty setup and authenticated HTTPS session with Secure cookie')
                    saved = {'mode': 'lan', 'address': origin}
                    assert browser.put('/api/access/config', json=saved, headers={'Origin': origin}).status_code == 200
                    assert browser.put('/api/access/config', json=saved,
                                       headers={'Origin': 'https://untrusted.example'}).status_code == 403
                    assert browser.post('/api/access/plan', json={**saved, 'upstream_port': backend_port,
                                                                'recovery_port': recovery_port},
                                        headers={'Origin': origin}).status_code == 200
                    report['checks'].append('forwarded HTTPS origin permits same origin and rejects foreign origin')
                    assert browser.get(local + '/api/me').status_code == 401
                    report['checks'].append('Secure cookie is not sent to local HTTP backend')
                    recovery = f'https://localhost:{recovery_port}'
                    assert browser.get(recovery + '/api/me').status_code == 200
                    assert browser.post(recovery + '/api/logout', headers={'Origin': recovery}).status_code == 200
                    assert browser.get('/api/me').status_code == 401
                    result = browser.post('/api/login', json={'password': payload['password']}, headers={'Origin': origin})
                    assert result.status_code == 200 and browser.get('/api/me').status_code == 200
                    report['checks'].append('HTTPS loopback recovery, logout and login work')
                try:
                    httpx.get(origin + '/health', trust_env=False, timeout=3)
                except httpx.ConnectError as exc:
                    assert 'CERTIFICATE_VERIFY_FAILED' in str(exc)
                    report['checks'].append('untrusted certificate is rejected without explicit local CA trust')
                else:
                    raise AssertionError('Private CA was unexpectedly trusted globally')
        except Exception as exc:
            raise RuntimeError(f'{exc}\nIsolated process logs:\n{logs.read_text()}') from exc
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
        report['checks'].append('temporary processes stopped and installation data isolated')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--caddy', type=Path, required=True, help='Executável Caddy instalado e verificado separadamente')
    args = parser.parse_args()
    print(json.dumps(rehearse(args.caddy.resolve()), ensure_ascii=False, indent=2))
