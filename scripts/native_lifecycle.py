"""Real native-package lifecycle rehearsal with disposable, synthetic installations.

Runs installed packages over loopback HTTP, with new per-release environments.
Downloads pinned wheels from TLS-verified PyPI unless --wheelhouse is given;
all installation/update phases then use that wheelhouse with --no-index.
Does not alter a live installation, host services, networking, or tracked files.
This is a process/package rehearsal, not a fresh OS or power-loss test.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import closing, contextmanager
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import tomllib
import urllib.error
import urllib.request
import uuid

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))
from mia import operations
from mia.operations import Manager, OperationError

PASSWORD = 'synthetic-native-lifecycle-password'
PROFILE = 'Synthetic context chosen by the fixture owner.'
GOAL = 'Preserve synthetic lifecycle evidence.'


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def stage(message):
    print(message, flush=True)


class API:
    def __init__(self, origin):
        self.origin = origin
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(self.cookies))
        self.headers = None

    def call(self, method, path, payload=None, expected=200, headers=None):
        body = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(self.origin + path, data=body, method=method,
                                        headers={'Content-Type': 'application/json', 'Origin': self.origin, **(headers or {})})
        try:
            response = self.opener.open(request, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            code, raw, self.headers = response.code, response.read(), response.headers
        check(code == expected, f'{method} {path}: expected {expected}, received {code}: {raw[:500]!r}')
        return json.loads(raw) if raw else None

    def get(self, path, expected=200):
        return self.call('GET', path, expected=expected)

    def asset(self, path):
        with self.opener.open(self.origin + path, timeout=10) as response:
            check(response.code == 200 and bool(response.read()), 'Installed asset unavailable: ' + path)

    def login(self):
        self.cookies.clear()
        self.call('POST', '/api/login', {'password': PASSWORD})


@contextmanager
def hostile_inherited_environment(root):
    replacements = {'MIA_DATA_DIR': str(root / 'must-not-be-used'), 'MIA_AI_ENABLED': 'true',
                    'MIA_AI_BASE_URL': 'http://127.0.0.1:1/v1', 'MIA_AI_MODEL': 'must-not-be-used',
                    'MIA_AI_API_KEY': 'synthetic-not-a-real-key', 'MIA_COOKIE_SECURE': 'true',
                    'MIA_OPERATIONS_ROOT': str(root / 'wrong-manager'), 'MIA_BIND': '0.0.0.0'}
    previous = {name: os.environ.get(name) for name in replacements}
    os.environ.update(replacements)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def public_source(destination):
    """Copy only the public build inputs, never checkout configuration or data."""
    destination.mkdir()
    for name in ('pyproject.toml', 'requirements.lock', 'README.md', 'MANIFEST.in', 'LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md'):
        path = REPOSITORY / name
        if path.exists():
            check(path.is_file() and not path.is_symlink(), 'Public build input must be a regular file')
            shutil.copyfile(path, destination / name)
    notices = REPOSITORY / 'THIRD_PARTY_LICENSES'
    if notices.is_dir():
        operations._copy_private(notices, destination / notices.name)
    package = destination / 'mia'
    package.mkdir()
    for path in (REPOSITORY / 'mia').rglob('*'):
        relative = path.relative_to(REPOSITORY / 'mia')
        check(not path.is_symlink(), 'Package inputs cannot be symlinks')
        if '__pycache__' not in relative.parts and path.is_file() and (path.suffix == '.py' or relative.parts[0] == 'static'):
            output = package / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, output)


def git_source(destination, reference, temporary):
    archive = temporary / 'baseline.tar'
    subprocess.run(['git', 'archive', '--format=tar', '--output', str(archive), reference],
                   cwd=REPOSITORY, check=True)
    with tarfile.open(archive) as handle:
        handle.extractall(destination, filter='data')


def version(source):
    return tomllib.loads((source / 'pyproject.toml').read_text())['project']['version']


def wheelhouse(root, supplied, sources):
    if supplied:
        check(supplied.is_dir(), '--wheelhouse must be a trusted existing directory')
        return supplied.resolve()
    target = root / 'wheels'
    target.mkdir()
    command = [sys.executable, '-m', 'pip', 'download', '--only-binary=:all:',
               '--index-url', 'https://pypi.org/simple', '--dest', str(target)]
    verified_env = {name: value for name, value in os.environ.items() if not name.startswith('PIP_')}
    verified_env.update(PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK='1',
                        PIP_CACHE_DIR=str(root / 'pip-cache'))
    subprocess.run([*command, *operations.BOOTSTRAP], cwd=root, env=verified_env, check=True)
    # Separate resolutions allow a previous version to pin different dependencies.
    for source in sources:
        subprocess.run([*command, '-r', str(source / 'requirements.lock')], cwd=root, env=verified_env, check=True)
    return target


def data_directory(manager):
    return manager._path(manager.active()['data'])


def task_titles(database):
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        return {row[0] for row in db.execute('SELECT title FROM tasks')}


def table_exists(database, name):
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        return bool(db.execute('SELECT name FROM sqlite_master WHERE type="table" AND name=?', (name,)).fetchone())


def verify_identity(api, area, expected_tasks):
    check(api.get('/api/me')['name'] == 'Synthetic Native Owner', 'Owner identity changed')
    check({task['title'] for task in api.get('/api/tasks')} == set(expected_tasks), 'Task set changed')
    documents = api.get('/api/documents')
    check(len(documents) == 1 and documents[0]['title'] == 'Lifecycle Evidence', 'Imported source changed')
    check(api.get('/api/onboarding')['goal'] == GOAL, 'Onboarding goal changed')
    check(api.get('/api/personalization')['text'] == PROFILE, 'Confirmed personal context changed')
    check(api.get('/api/access/config')['mode'] == 'computer', 'Access preference changed')
    runs = api.get('/api/runs')
    interrupted = next(run for run in runs if run['id'] == 'synthetic-interrupted-run')
    check(interrupted['state'] == 'failed' and interrupted['charged_micro'] == 25, 'Interrupted run retried or reservation lost')
    check(api.get('/api/areas')[0]['id'] == area, 'Area identity changed')


def populate(api, manager):
    check(api.get('/api/status')['configured'] is False, 'Installation must start empty')
    api.get('/api/me', expected=401)
    api.call('POST', '/api/setup', {'name': 'Synthetic Native Owner', 'password': PASSWORD,
                                  'area_name': 'Lifecycle', 'timezone': 'UTC'}, expected=201)
    check('Secure' not in api.headers.get('Set-Cookie', ''), 'Inherited secure-cookie variable overrode machine.env')
    check(api.get('/api/ai/config')['enabled'] is False, 'Inherited AI variables enabled a provider')
    area = api.get('/api/areas')[0]['id']
    api.call('POST', '/api/tasks', {'title': 'Preserve baseline task', 'area_id': area}, expected=201)
    batch = api.call('POST', '/api/imports', {'filename': 'lifecycle.md', 'area_id': area,
                     'content_base64': base64.b64encode(b'# Lifecycle Evidence\n\nSynthetic lifecycle proof for restoration.').decode()}, expected=201)
    check(api.get('/api/documents') == [], 'Import wrote sources before approval')
    api.call('POST', '/api/imports/' + batch['id'] + '/confirm', {'item_ids': [batch['items'][0]['id']]})
    api.call('PUT', '/api/onboarding', {'goal': GOAL, 'step': 3, 'completed': True})
    api.call('PUT', '/api/personalization', {'text': PROFILE, 'expected_revision': 0})
    api.call('PUT', '/api/access/config', {'mode': 'computer', 'address': ''})
    manager.stop()
    with closing(sqlite3.connect(data_directory(manager) / 'mia.db')) as db, db:
        db.execute("INSERT INTO runs(id,owner_id,request_key,request_json,state,model,endpoint,sources_json,created_at,updated_at,reserved_micro,charged_micro,cost_status) VALUES('synthetic-interrupted-run',1,'synthetic-interrupted-key','{}','running','synthetic','http://127.0.0.1:1','[]','2030-01-01','2030-01-01',25,25,'reserved')")
    manager.start()
    verify_identity(api, area, ['Preserve baseline task'])
    return area


@contextmanager
def local_provider():
    calls = []
    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            context = json.loads(body['messages'][1]['content'])
            calls.append(context)
            document = next(item for item in context['context'] if item['source'].startswith('doc:'))
            response = {'choices': [{'finish_reason': 'tool_calls', 'message': {
                'content': 'Synthetic proposal grounded in [' + document['source'] + '].',
                'tool_calls': [{'type': 'function', 'function': {'name': 'propose_task', 'arguments': json.dumps({
                    'title': 'Original synthetic proposal', 'area_id': context['area_id']})}}]}}],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}}
            raw = json.dumps(response).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def edited_proposal(api, area):
    context = api.get('/api/ai/context?area_id=' + area + '&q=lifecycle')
    check(not any(item['source'] == 'profile:1' for item in context), 'Personal context included without permission')
    allowed = api.get('/api/ai/context?area_id=' + area + '&q=lifecycle&include_personal_context=true')
    check(any(item['source'] == 'profile:1' and item['text'] == PROFILE for item in allowed), 'Explicit personal context was not included')
    with local_provider() as (endpoint, calls):
        settings = {'enabled': True, 'endpoint': endpoint, 'model': 'synthetic-local-model',
                    'api_key': '', 'daily_call_limit': 2}
        api.call('PUT', '/api/ai/config', settings)
        request = {'request_key': str(uuid.uuid4()), 'message': 'Proponha tarefa usando synthetic lifecycle proof',
                   'area_id': area, 'consent': True}
        run = api.call('POST', '/api/runs', request)
        check(run['state'] == 'awaiting_confirmation' and len(calls) == 1, 'Local proposal did not await approval')
        check(run['citations'] and not run['invalid_citations'], 'Grounded local citation missing')
        check(len(api.get('/api/tasks')) == 1, 'Proposal wrote a task before approval')
        check(not any(item['source'] == 'profile:1' for item in calls[0]['context']), 'Unapproved personal context sent to provider')
        check(api.call('POST', '/api/runs', request)['id'] == run['id'] and len(calls) == 1, 'Replay called provider again')
        path = '/api/runs/' + run['id'] + '/approve'
        edits = {'title': 'Preserve reviewed task', 'notes': 'Synthetic owner chose these fields.',
                 'due_date': '2030-12-01', 'priority': 3}
        applied = api.call('POST', path, {'edits': edits})
        check(applied['proposal']['title'] == 'Original synthetic proposal', 'Original proposal changed')
        check(applied['task_result']['title'] == edits['title'], 'Reviewed title was not applied')
        repeated = api.call('POST', path, {'edits': {**edits, 'title': 'Do not overwrite on replay'}})
        check(repeated['task_id'] == applied['task_id'] and repeated['task_result'] == applied['task_result'], 'Approval replay changed effects')
        check(len(api.get('/api/tasks')) == 2 and len(calls) == 1, 'Duplicate task/provider call')
        api.call('PUT', '/api/ai/config', {**settings, 'enabled': False})
        return run['id']


def failed_source(candidate, target):
    shutil.copytree(candidate, target)
    original = version(candidate)
    failing = original + '+startupfail'
    manifest = target / 'pyproject.toml'
    manifest.write_text(manifest.read_text().replace('version = "' + original + '"', 'version = "' + failing + '"', 1))
    package = target / 'mia/__init__.py'
    package.write_text(package.read_text().replace('__version__ = "' + original + '"', '__version__ = "' + failing + '"', 1))
    with (target / 'mia/app.py').open('a') as handle:
        handle.write('\n# Intentional failure artifact, only inside this disposable rehearsal.\n'
                     '_fixture_directory = Path(os.environ["MIA_DATA_DIR"])\n'
                     '(_fixture_directory / "failed-startup-output.txt").write_text("Synthetic failed attempt retained")\n'
                     'with sqlite3.connect(_fixture_directory / "mia.db") as _fixture_database:\n'
                     '    _fixture_database.execute("CREATE TABLE failed_startup_probe(value TEXT)")\n'
                     'raise RuntimeError("Intentional synthetic startup failure")\n')
    check(version(target) == failing, 'Failure artifact version was not changed')


def installed_package(manager):
    path = subprocess.check_output([str(manager._python(manager.active())), '-I', '-c',
                                    'import mia; print(mia.__file__)'], cwd=manager.root, text=True).strip()
    check(Path(path).is_relative_to(manager.root / manager.active()['release'] / 'venv'), 'Server package is not installed outside source')
    check(not Path(path).is_relative_to(REPOSITORY), 'Source checkout shadowed installed package')



def cleanup_fixture(manager):
    """Never delete fixture data while a verified worker still holds its lock."""
    try:
        manager.stop()
    except Exception as error:
        # Only this temporary installation's durable, birth-verified identities.
        # A changed/unverifiable PID is never signalled, and its files are retained.
        record = operations._read(manager.root / 'process.json')
        for pid_key, birth_key in (('pid', 'birth'), ('child_pid', 'child_birth')):
            pid, birth = record.get(pid_key), record.get(birth_key)
            if pid and pid != os.getpid() and birth and operations._birth(pid) == birth:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass
        deadline = time.monotonic() + 5
        while operations._busy(manager.root / 'service.lock') and time.monotonic() < deadline:
            time.sleep(.05)
        if operations._busy(manager.root / 'service.lock'):
            raise OperationError('Fixture exit could not be verified; preserve its directory for inspection') from error
        raise OperationError('Normal fixture teardown failed; verified fixture processes were stopped forcibly') from error


def run(root, baseline, candidate, wheels):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    manager = Manager(root / 'installation')
    api = API(f'http://127.0.0.1:{port}')
    old_version, new_version = version(baseline), version(candidate)
    check(old_version != new_version, 'Baseline and candidate must be different identified versions')
    stage(f'Installing baseline {old_version} in a fresh native environment; installation phases offline.')
    try:
        with hostile_inherited_environment(root):
            manager.install(baseline, port=port, wheelhouse=wheels, offline=True)
            check(list(data_directory(manager).iterdir()) == [], 'Installer did not start with empty data')
            check(manager.root.stat().st_mode & 0o077 == 0, 'Installation is not private')
            manager.start()
            installed_package(manager)
            area = populate(api, manager)
            check(not (root / 'must-not-be-used').exists(), 'Inherited data directory was used')
            stage('PASS baseline: empty setup, reviewed import, identity, goal/profile, restart and interrupted budget without resend.')
            manager.update(candidate, wheelhouse=wheels, offline=True)
            check(api.get('/health')['version'] == new_version, 'HTTP did not report the candidate version')
            installed_package(manager)
            for asset in ('/', '/assets/app.js', '/assets/app.css', '/assets/operations.js', '/assets/access.js'):
                api.asset(asset)
            verify_identity(api, area, ['Preserve baseline task'])
            reviewed_run = edited_proposal(api, area)
            manager.stop()
            manager.start()
            verify_identity(api, area, ['Preserve baseline task', 'Preserve reviewed task'])
            check(next(run for run in api.get('/api/runs') if run['id'] == reviewed_run)['task_result']['title'] == 'Preserve reviewed task', 'Edited approval was not persistent')
            check(api.get('/api/operations')['managed'] is True, 'Managed API status unavailable')
            stage(f'PASS update {old_version} -> {new_version}: installed HTTP/assets, reviewed task/replay, opt-in context and restart.')

            broken = root / 'startup-failure-source'
            failed_source(candidate, broken)
            failed_data = data_directory(manager)
            try:
                manager.update(broken, wheelhouse=wheels, offline=True)
            except OperationError as error:
                check('versão anterior restaurada' in str(error), 'Failed startup did not recover automatically')
            else:
                raise AssertionError('Broken release unexpectedly started')
            check(api.get('/health')['version'] == new_version, 'Automatic recovery did not serve the previous version')
            check(data_directory(manager) != failed_data, 'Automatic recovery reused the attempted database')
            check((failed_data / 'failed-startup-output.txt').exists() and table_exists(failed_data / 'mia.db', 'failed_startup_probe'), 'Failed attempt data was not preserved')
            check(not (data_directory(manager) / 'failed-startup-output.txt').exists(), 'Recovery copied failed attempt output')
            api.get('/api/me', expected=401)
            api.login()
            verify_identity(api, area, ['Preserve baseline task', 'Preserve reviewed task'])
            stage('PASS startup failure: real faulty artifact failed, previous HTTP service restored into fresh data, attempt retained, sessions invalidated.')

            attempt_data = data_directory(manager)
            original_write = operations._write
            previous_release = manager.active()['release']
            def interrupted_write(path, value):
                original_write(path, value)
                if path == manager.root / 'active.json' and value['release'] != previous_release:
                    raise KeyboardInterrupt('Simulated interruption after durable active switch')
            operations._write = interrupted_write
            try:
                try:
                    manager.update(candidate, wheelhouse=wheels, offline=True)
                except KeyboardInterrupt:
                    pass
                else:
                    raise AssertionError('Simulated interruption did not occur')
            finally:
                operations._write = original_write
            check(manager.status()['recovery_required'], 'Interrupted update did not leave a recovery journal')
            try:
                manager.start()
            except OperationError as error:
                check('recover' in str(error), 'Pending recovery did not block start')
            else:
                raise AssertionError('Start bypassed pending recovery')
            with closing(sqlite3.connect(attempt_data / 'mia.db')) as db, db:
                db.execute('CREATE TABLE interrupted_attempt_probe(value TEXT)')
            manager.recover()
            recovered = manager.active()
            check(data_directory(manager) != attempt_data, 'Interrupted recovery reused attempt data')
            check(table_exists(attempt_data / 'mia.db', 'interrupted_attempt_probe'), 'Interrupted attempt was discarded')
            check(not table_exists(data_directory(manager) / 'mia.db', 'interrupted_attempt_probe'), 'Recovered data contains interrupted migration')
            api.get('/api/me', expected=401)
            api.login()
            verify_identity(api, area, ['Preserve baseline task', 'Preserve reviewed task'])
            manager.recover()
            check(manager.active() == recovered and not manager.status()['recovery_required'], 'Recovery was not idempotent')
            stage('PASS simulated interruption: durable switch/journal, start blocked, explicit fresh-data recovery and safe repeat.')

            post_update = data_directory(manager)
            try:
                manager.rollback()
            except OperationError as error:
                check('alterações posteriores' in str(error), 'Rollback acknowledgement requirement was unclear')
            else:
                raise AssertionError('Rollback proceeded without acknowledgement')
            check(api.get('/health')['version'] == new_version, 'Refused rollback altered the running service')
            manager.rollback(acknowledge_post_update_loss=True)
            check(api.get('/health')['version'] == old_version, 'Rollback did not restore the baseline HTTP version')
            api.get('/api/me', expected=401)
            api.login()
            verify_identity(api, area, ['Preserve baseline task'])
            check(task_titles(post_update / 'mia.db') == {'Preserve baseline task', 'Preserve reviewed task'}, 'Post-update original data was lost')
            retained = list((manager.root / 'snapshots').glob('before-rollback-*'))
            check(len(retained) == 1, 'Rollback did not retain the post-update snapshot')
            retained_path = str(retained[0].relative_to(manager.root))
            manager._verify_snapshot(retained_path)
            check(task_titles(retained[0] / 'data/mia.db') == {'Preserve baseline task', 'Preserve reviewed task'}, 'Retained post-update task set changed')
            with closing(sqlite3.connect((retained[0] / 'data/mia.db').as_uri() + '?mode=ro', uri=True)) as db:
                check(db.execute('SELECT task_result_json FROM runs WHERE id=?', (reviewed_run,)).fetchone()[0] is not None, 'Reviewed result missing from retained snapshot')
            manager._verify_snapshot(retained_path)
            check(data_directory(manager) != post_update, 'Old code was started on migrated attempt data')
            stage('PASS rollback: explicit acknowledgement, previous package/new data, post-update task/result retained separately.')

            record = operations._read(manager.root / 'process.json')
            check(record.get('child_birth') and record.get('birth'), 'Real supervisor/worker identities absent')
            os.kill(record['pid'], signal.SIGKILL)
            os.waitpid(record['pid'], 0)  # This fixture owns and reaps its killed supervisor.
            orphan = manager._record()
            check(orphan['pid'] == record['child_pid'] and orphan['birth'] == record['child_birth'], 'Living orphan worker was not identified')
            check(api.get('/health')['ok'] is True, 'Orphan worker did not retain HTTP service')
            manager.stop()
            check(not operations._busy(manager.root / 'service.lock'), 'Orphan stop did not release service lock')
            manager.start()
            api.login()
            verify_identity(api, area, ['Preserve baseline task'])
            stage('PASS supervisor SIGKILL: living worker identity retained, explicit stop releases lock, restart preserves data.')
    finally:
        if (manager.root / 'active.json').exists():
            primary_error = sys.exc_info()[1]
            try:
                cleanup_fixture(manager)
            except Exception as cleanup_error:
                if primary_error is None:
                    raise
                primary_error.add_note('Fixture teardown also failed: ' + str(cleanup_error))
    stage('PASS native lifecycle complete; only disposable synthetic data, loopback HTTP and one deterministic local provider call. No live installation or host service changed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', default='7a026c2', help='Trusted earlier Git revision; default public 0.2.0a10')
    parser.add_argument('--wheelhouse', type=Path, help='Existing trusted wheels for this Python/platform; no downloads when supplied')
    parser.add_argument('--keep-on-failure', action='store_true', help='Preserve disposable synthetic fixture after a failed rehearsal for diagnosis; processes are still stopped')
    args = parser.parse_args()
    check(sys.version_info >= (3, 12), 'Python 3.12+ required')
    root = Path(tempfile.mkdtemp(prefix='mia-native-lifecycle-'))
    failed = False
    try:
        baseline, candidate = root / 'baseline-source', root / 'candidate-source'
        git_source(baseline, args.baseline_ref, root)
        public_source(candidate)
        wheels = wheelhouse(root, args.wheelhouse, (baseline, candidate))
        run(root, baseline, candidate, wheels)
    except BaseException:
        failed = True
        raise
    finally:
        installation = root / 'installation'
        if failed and args.keep_on_failure:
            print('Failed synthetic fixture retained for diagnosis: ' + str(root), file=sys.stderr)
        elif installation.exists() and operations._busy(installation / 'service.lock'):
            print('Fixture retained because process exit was not verified: ' + str(root), file=sys.stderr)
        else:
            shutil.rmtree(root)


if __name__ == '__main__':
    main()
