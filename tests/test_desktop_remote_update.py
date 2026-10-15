"""Remote operations: approval faults plus real embedded stable-Manager journals.

All homes, SSH pins, owner records and libraries below are synthetic. These tests
never contact a user's server or change host services.
"""
import base64
from contextlib import closing, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from types import SimpleNamespace
import uuid

import pytest

from mia import desktop_remote as remote
from mia import operations
from mia.desktop import REMOTE_ACTIONS

KEY = base64.b64encode(b"synthetic-server-public-key-not-secret").decode()
PIN = remote._fingerprint(KEY)
IDENTITY = "5cdd414b-7271-4503-b817-f764cbd0b900"
TOKEN = "synthetic-private-bootstrap-authority-00000"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def make_artifact(resources, version="0.2.0a14"):
    payload = resources / "remote-runtime/payload"
    contents = {
        "runtime/bin/python3": b"synthetic-runtime\n",
        "source/mia/operations.py": Path(operations.__file__).read_bytes(),
        "source/pyproject.toml": f'[project]\nname="mia-personal-ai"\nversion="{version}"\n'.encode(),
        "source/requirements.lock": b"synthetic==1.0\n",
        "source/LICENSE": b"Apache-2.0\n", "source/NOTICE": b"Synthetic\n",
        "source/THIRD_PARTY_NOTICES.md": b"Synthetic dependency notices\n",
        "wheelhouse/example-1.0-py3-none-any.whl": b"synthetic-wheel\n",
    }
    for name, body in contents.items():
        path = payload / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(body)
        path.chmod(0o700 if name.startswith("runtime/") else 0o600)
    return rebuild_artifact(resources, version)


def rebuild_artifact(resources, version="0.2.0a14"):
    payload = resources / "remote-runtime/payload"
    inventory = {}
    for path in sorted(payload.rglob("*")):
        if path.is_file():
            inventory[path.relative_to(payload).as_posix()] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "executable": bool(path.stat().st_mode & 0o111)}
    manifest = {"format": 1, "platform": "ubuntu24.04", "architecture": "amd64", "python_version": "3.12", "version": version, "files": inventory}
    for kind, origin in (("runtime", "https://github.com/astral-sh/python-build-standalone/releases/download/reviewed/fixture.tar.gz"), ("wheelhouse", "https://pypi.org/")):
        manifest[kind + "_provenance"] = {"format": 1, "platform": "linux", "architecture": "x86_64", "python_version": "3.12", "source_url": origin, "files": {name[len(kind) + 1:]: entry for name, entry in inventory.items() if name.startswith(kind + "/")}}
    (resources / "remote-runtime/manifest.json").write_text(json.dumps(manifest))
    return manifest, payload


class OperationSSH:
    def __init__(self, manifest):
        self.key = KEY
        self.calls = []
        self.fail = None
        self.result_failure = None
        runtime = {name[len("runtime/"):]: entry for name, entry in manifest["files"].items() if name.startswith("runtime/")}
        self.state = {"sha256": "a" * 64, "installation_id": IDENTITY, "version": "0.2.0a13", "paused": True, "running": False, "recovery_required": False, "runtime_sha256": digest(runtime), "manager_sha256": "b" * 64, "manager_protocol": 2, "source_sha256": "c" * 64, "outer": {}, "journal_pending": False}

    def scan(self, config):
        self.calls.append("scan")
        return self.key

    def known(self, config, key):
        return True, False

    def operation(self, config, pin, request, payload=None):
        self.calls.append(request)
        if self.fail:
            raise remote.RemoteError(self.fail, "synthetic failure")
        if self.result_failure:
            return {"ok": False, "code": self.result_failure}
        if request["action"] == "inspect":
            return {"ok": True, "state": dict(self.state)}
        if request["expected_state_sha256"] != self.state["sha256"]:
            return {"ok": False, "code": "approval_changed"}
        if request["action"] == "update":
            self.state["version"] = request["manifest"]["version"]
            return {"ok": True, "updated": True, "state": dict(self.state)}
        if request["action"] == "snapshot":
            return {"ok": True, "snapshot_id": "desktop-remote-" + "d" * 32, "verified": True, "state": dict(self.state)}
        self.state["recovery_required"] = False
        self.state["journal_pending"] = False
        return {"ok": True, "recovered": False, "recovery_confirmed": True, "state": dict(self.state)}

    def birth(self, pid):
        return None

    def stop(self, record):
        self.calls.append("stop")


@pytest.fixture
def controller(tmp_path):
    home, resources = tmp_path / "home", tmp_path / "resources"
    home.mkdir(mode=0o700)
    resources.mkdir()
    manifest, _ = make_artifact(resources)
    ssh = OperationSSH(manifest)
    client = remote.RemoteController(resources, home, adapter=ssh)
    config = {"host": "server.example", "user": "tester", "port": 22, "remote_port": 8123}
    identity = client._identity(config)
    directory = client._directory(identity)
    remote._write(directory / "connection.json", {**config, "mode": "ssh", "connection_id": identity, "installation_id": IDENTITY, "version": "0.2.0a13", "url": "http://127.0.0.1:54321/", "host_key_fingerprint": PIN, "configured": True, "bootstrap_protected": True})
    return client, {"connection_id": identity}


@pytest.mark.parametrize("plan_action,apply_action", [("remote_bundle_plan", "remote_bundle_update"), ("remote_snapshot_plan", "remote_snapshot"), ("remote_recovery_plan", "remote_recover")])
def test_all_operations_require_review_and_bind_selected_destination(controller, plan_action, apply_action):
    client, selected = controller
    with pytest.raises(remote.RemoteError, match="confirme") as error:
        client.handle(apply_action, {**selected, "approve_sha256": "0" * 64})
    assert error.value.code == "plan_approval_required"
    plan = client.handle(plan_action, selected)
    assert plan["installation_id"] == IDENTITY
    assert plan["host_key_fingerprint"] == PIN
    assert plan["sha256"]
    result = client.handle(apply_action, {**selected, "approve_sha256": plan["sha256"]})
    assert result["installation_id"] == IDENTITY
    assert result["connection_id"] == selected["connection_id"]
    assert result["host_key_fingerprint"] == PIN
    if apply_action != "remote_snapshot":
        assert result["paused"] and not result["running"]
        assert result["url"] == "http://127.0.0.1:54321/"
    if apply_action == "remote_recover":
        assert result["recovery_confirmed"] is True
        assert result["recovered"] is False
    assert "spawn" not in client.adapter.calls
    assert set((plan_action, apply_action)) <= REMOTE_ACTIONS


@pytest.mark.parametrize("change", ["state", "artifact", "connection", "host_pin"])
def test_changed_approval_is_rejected_before_update(controller, change):
    client, selected = controller
    plan = client.remote_bundle_plan(selected)
    if change == "state":
        client.adapter.state["sha256"] = "e" * 64
    elif change == "artifact":
        path = client.resources / "remote-runtime/payload/source/NOTICE"
        path.write_text("Changed candidate\n")
        rebuild_artifact(client.resources)
    elif change == "connection":
        path = client._directory(selected["connection_id"]) / "connection.json"
        value = json.loads(path.read_text())
        value["installation_id"] = str(uuid.uuid4())
        remote._write(path, value)
    else:
        client.adapter.key = base64.b64encode(b"changed-server-public-key-not-secret").decode()
    with pytest.raises(remote.RemoteError) as error:
        client.remote_bundle_update({**selected, "approve_sha256": plan["sha256"]})
    assert error.value.code in ("approval_changed", "host_key_changed")
    assert client.adapter.state["version"] == "0.2.0a13"


def test_lost_update_response_requires_review_not_automatic_retry(controller):
    client, selected = controller
    plan = client.remote_bundle_plan(selected)
    client.adapter.fail = "ssh_unavailable"
    with pytest.raises(remote.RemoteError) as error:
        client.remote_bundle_update({**selected, "approve_sha256": plan["sha256"]})
    assert error.value.code == "operation_result_unknown"
    assert sum(isinstance(call, dict) and call["action"] == "update" for call in client.adapter.calls) == 1


@pytest.mark.parametrize("action", ["remote_bundle_plan", "remote_snapshot_plan", "remote_recovery_plan"])
def test_https_connections_are_never_adopted_for_server_operations(controller, action):
    client, selected = controller
    path = client._directory(selected["connection_id"]) / "connection.json"
    value = json.loads(path.read_text()); value["mode"] = "https"; remote._write(path, value)
    with pytest.raises(remote.RemoteError) as error:
        client.handle(action, selected)
    assert error.value.code == "managed_ssh_required"
    assert not any(isinstance(call, dict) for call in client.adapter.calls)


@pytest.mark.parametrize("secret_code", ["unrecognized-key-value", "unsafe_path", "manager_changed", "service_changed"])
def test_server_failure_returns_only_sanitized_codes_and_messages(controller, secret_code):
    client, selected = controller
    client.adapter.result_failure = secret_code
    with pytest.raises(remote.RemoteError) as error:
        client.remote_recovery_plan(selected)
    assert secret_code not in str(error.value)
    assert TOKEN not in str(error.value)


def test_pending_recovery_blocks_snapshot_and_update(controller):
    client, selected = controller
    client.adapter.state["recovery_required"] = True
    client.adapter.state["journal_pending"] = True
    for action in ("remote_bundle_plan", "remote_snapshot_plan"):
        with pytest.raises(remote.RemoteError) as error:
            client.handle(action, selected)
        assert error.value.code == "recovery_required"
    plan = client.remote_recovery_plan(selected)
    assert plan["recovery_required"] is True


# The fixture Manager keeps actual snapshot, SQLite verification, journals,
# source-copy identities and fresh-data restoration. Only builds/process/OS
# service transport are simulated; none of these tests claims a real SSH host.
MANAGER_TEST_ADAPTER = '''
def _fixture_release(self, source, wheelhouse=None, offline=False):
    version=tomllib.loads((source/'pyproject.toml').read_text())['project']['version']
    relative='releases/'+version+'-'+uuid.uuid4().hex[:12]
    release=self.root/relative;release.mkdir(mode=0o700)
    (release/'venv').mkdir(mode=0o700)
    shutil.copytree(source,release/'source',ignore=shutil.ignore_patterns('__pycache__'))
    for directory in (release/'source',*(path for path in (release/'source').rglob('*') if path.is_dir())): directory.chmod(0o700)
    _write(release/'release.json',{'version':version,'source_sha256':hashlib.sha256(json.dumps(_manifest(release/'source'),sort_keys=True).encode()).hexdigest()})
    return {'release':relative,'version':version}
def _fixture_record(self):
    return {'pid':12345} if (self.root/'fixture-running').exists() else {}
def _fixture_stop(self):
    (self.root/'fixture-running').unlink(missing_ok=True)
def _fixture_start(self,**kwargs):
    if (self.root/'fixture-interrupt').exists(): raise KeyboardInterrupt('synthetic worker interruption')
    (self.root/'fixture-running').touch(mode=0o600)
Manager._release=_fixture_release
Manager._record=_fixture_record
Manager._stop=_fixture_stop
Manager._start=_fixture_start
'''


@pytest.fixture
def embedded(tmp_path, monkeypatch):
    home = tmp_path / "server-home"; home.mkdir(mode=0o700)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    actual_read_text = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, *args, **kwargs: 'ID=ubuntu\nVERSION_ID="24.04"\n' if self == Path("/etc/os-release") else actual_read_text(self, *args, **kwargs))
    resources = tmp_path / "resources"; resources.mkdir()
    manifest, payload = make_artifact(resources)
    base = home / ".local/share/mia-demo"
    for path in (home / ".local", home / ".local/share", base, base / "artifacts", base / "installations"):
        path.mkdir(mode=0o700, exist_ok=True)
    original = base / "artifacts" / IDENTITY
    shutil.copytree(payload, original)
    for directory in (original, *(path for path in original.rglob("*") if path.is_dir())):
        directory.chmod(0o700)
    old_project = original / "source/pyproject.toml"
    old_project.write_text(old_project.read_text().replace("0.2.0a14", "0.2.0a13"))
    old_manager = original / "source/mia/operations.py"
    old_manager.write_text(old_manager.read_text() + MANAGER_TEST_ADAPTER)
    spec = importlib.util.spec_from_file_location("fixture_stable_manager", old_manager)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    root = base / "installations" / IDENTITY
    manager = module.Manager(root)
    manager.install(original / "source", installation_id=IDENTITY, private_bootstrap=True)
    # install copies this exact reviewed fixture manager implementation.
    config = json.loads((root / "installation.json").read_text())
    config["python"] = str(original / "runtime/bin/python3")
    remote._write(root / "installation.json", config)
    remote._write(base / ("install-" + IDENTITY + ".json"), {"phase": "complete", "installation_id": IDENTITY})
    unit = home / ".config/systemd/user" / ("mia-" + hashlib.sha256(str(root).encode()).hexdigest()[:12] + ".service")
    unit.parent.mkdir(mode=0o700, parents=True)
    unit.write_text(manager.service_template(kind="systemd")); unit.chmod(0o600)
    remote._write(root / "service-registration.json", {"kind": "systemd", "destination": str(unit), "sha256": "a" * 64})
    real_is_file = Path.is_file
    linger = Path("/var/lib/systemd/linger") / __import__("pwd").getpwuid(os.getuid()).pw_name
    monkeypatch.setattr(Path, "is_file", lambda self: True if self == linger else real_is_file(self))
    real_run = subprocess.run
    real_read_bytes = Path.read_bytes
    service_pid = os.getpid()
    process_cmdline = Path('/proc') / str(service_pid) / 'cmdline'
    synthetic_argv = [config['python'], '-I', '-B', str(root / 'manager.py'), '--root', str(root), 'service-run']
    monkeypatch.setattr(Path, 'read_bytes', lambda self: ('\0'.join(synthetic_argv) + '\0').encode() if self == process_cmdline else real_read_bytes(self))
    def service_run(command, **kwargs):
        if command[:3] == ["/usr/bin/systemctl", "--user", "show"]:
            stdout = f"FragmentPath={unit}\nUnitFileState=enabled\nLoadState=loaded\nActiveState=active\nMainPID={service_pid}\n".encode()
            return SimpleNamespace(returncode=0, stdout=stdout)
        return real_run(command, **kwargs)
    monkeypatch.setattr(subprocess, "run", service_run)
    data = manager._path(manager.active()["data"])
    from mia.db import SCHEMA
    with closing(sqlite3.connect(data / "mia.db")) as database:
        database.executescript(SCHEMA)
        database.execute("INSERT INTO owner(id,name,email,timezone,password_hash,created_at) VALUES(1,'Synthetic','owner@example.test','UTC','synthetic-hash','2026-10-14')")
        database.execute("INSERT INTO areas(id,owner_id,name,created_at,updated_at) VALUES('synthetic-area',1,'Project','2026-10-14','2026-10-14')")
        database.execute("INSERT INTO tasks(id,owner_id,area_id,title,created_at,updated_at) VALUES('synthetic-task',1,'synthetic-area','Preserve decision','2026-10-14','2026-10-14')")
        database.execute("INSERT INTO sessions(token_hash,owner_id,created_at,expires_at,last_seen_at) VALUES('synthetic-session',1,'2026-10-14','2099-01-01','2026-10-14')")
        database.commit()
    (data / "notes").mkdir(mode=0o700)
    (data / "notes/decision.md").write_text("Synthetic decision must survive\n")
    (root / "paused.json").write_text('{"reason":"operator-stop"}'); (root / "paused.json").chmod(0o600)
    return SimpleNamespace(home=home, resources=resources, base=base, root=root, manifest=manifest, payload=payload, manager=manager)


def invoke_runner(fixture, action, *, expected=None, archive=None, manifest=None, review_id=None):
    request = {"action": action, "identity": IDENTITY, "remote_port": 8123, "manifest": manifest or fixture.manifest}
    if action != "inspect": request["review_id"] = review_id or uuid.uuid4().hex
    if action == "snapshot": request["candidate_sha256"] = digest(request["manifest"])
    if expected is not None: request["expected_state_sha256"] = expected
    if action == "update": request["candidate_sha256"] = digest(request["manifest"])
    body = io.BytesIO(json.dumps(request).encode() + b"\n")
    body.seek(0, io.SEEK_END)
    if action == "update":
        with tarfile.open(fileobj=body, mode="w") as tar:
            if archive is None:
                for name in sorted(request["manifest"]["files"]):
                    if name.startswith(("source/", "wheelhouse/")):
                        tar.add(fixture.payload / name, arcname=name, recursive=False)
            else:
                for name, value in archive:
                    entry = tarfile.TarInfo(name); entry.size = len(value)
                    tar.addfile(entry, io.BytesIO(value))
    body.seek(0)
    old_stdin = sys.stdin
    sys.stdin = SimpleNamespace(buffer=body)
    output = io.StringIO()
    try:
        with redirect_stdout(output):
            exec(compile(remote._REMOTE_OPERATION_RUNNER, "<fixed-remote-runner>", "exec"), {})
    finally:
        sys.stdin = old_stdin
    return json.loads(output.getvalue())


def test_embedded_update_preserves_library_owner_config_pause_and_stable_manager(embedded):
    before = invoke_runner(embedded, "inspect")
    assert before["ok"] is True, before
    original = {name: (embedded.root / name).read_bytes() for name in ("manager.py", "installation.json", "machine.env", "bootstrap-token")}
    original_pause = json.loads((embedded.root / "paused.json").read_text())
    result = invoke_runner(embedded, "update", expected=before["state"]["sha256"])
    assert result["ok"] is True, result
    assert result["state"]["version"] == "0.2.0a14"
    assert result["state"]["paused"] is True
    assert result["state"]["running"] is False
    assert result["state"]["recovery_required"] is False
    assert (embedded.manager._path(embedded.manager.active()["data"]) / "notes/decision.md").read_text().startswith("Synthetic decision")
    with closing(sqlite3.connect(embedded.manager._path(embedded.manager.active()["data"]) / "mia.db")) as database:
        assert database.execute("SELECT email,password_hash FROM owner").fetchone() == ("owner@example.test", "synthetic-hash")
        assert database.execute("SELECT title FROM tasks").fetchone() == ("Preserve decision",)
        assert database.execute("SELECT COUNT(*) FROM sessions").fetchone() == (1,)
    assert all((embedded.root / name).read_bytes() == value for name, value in original.items())
    assert json.loads((embedded.root / "paused.json").read_text()) == original_pause
    assert list((embedded.root / "snapshots").glob("*/snapshot.json"))
    assert "MIA_" not in json.dumps(result)
    assert TOKEN not in json.dumps(result)


def test_embedded_snapshot_is_verified_and_preserves_pause(embedded):
    before = invoke_runner(embedded, "inspect")
    result = invoke_runner(embedded, "snapshot", expected=before["state"]["sha256"])
    assert result["ok"] and result["verified"], result
    assert result["state"]["paused"] and not result["state"]["running"]
    embedded.manager._verify_snapshot("snapshots/" + result["snapshot_id"])


@pytest.mark.parametrize("changed", ["machine.env", "bootstrap-token", "active.json", "manager.py", "runtime", "service"])
def test_embedded_changed_inputs_refuse_before_version_switch(embedded, changed):
    before = invoke_runner(embedded, "inspect")
    if changed == "runtime":
        (embedded.base / "artifacts" / IDENTITY / "runtime/bin/python3").write_bytes(b"changed runtime")
    elif changed == "service":
        next((embedded.home / ".config/systemd/user").glob("*.service")).write_text("foreign unit\n")
    elif changed == "active.json":
        (embedded.root / changed).write_text('{"release":"releases/foreign","version":"0.2.0a13","data":"data/initial"}')
    elif changed == "machine.env":
        (embedded.root / changed).write_text("MIA_AI_ENABLED=true\n")
    else:
        with (embedded.root / changed).open("ab") as handle: handle.write(b"changed")
    result = invoke_runner(embedded, "update", expected=before["state"]["sha256"])
    assert result["ok"] is False, result
    assert result["code"] in ("approval_changed", "service_changed", "manager_changed", "bootstrap_changed", "managed_installation_required")
    assert not (embedded.root / "journal.json").exists()


def test_partial_transfer_leaves_durable_recovery_then_discards_only_unexecuted_stage(embedded):
    before = invoke_runner(embedded, "inspect")
    result = invoke_runner(embedded, "update", expected=before["state"]["sha256"], archive=[("source/NOTICE", b"wrong bytes")])
    assert result == {"ok": False, "code": "artifact_invalid"}
    journal = json.loads((embedded.root / "desktop-remote.json").read_text())
    stage = embedded.base / journal["stage"]
    assert stage.exists()
    pending = invoke_runner(embedded, "inspect")
    assert pending["state"]["recovery_required"]
    recovered = invoke_runner(embedded, "recover", expected=pending["state"]["sha256"])
    assert recovered["ok"] and recovered["recovery_confirmed"]
    assert not stage.exists()
    assert not (embedded.root / "desktop-remote.json").exists()
    assert recovered["state"]["version"] == "0.2.0a13"
    assert recovered["state"]["paused"]


def test_worker_interruption_recovers_old_release_into_fresh_data_and_retains_attempt(embedded):
    before = invoke_runner(embedded, "inspect")
    old_data = embedded.manager._path(embedded.manager.active()["data"])
    (embedded.root / "fixture-interrupt").touch()
    with pytest.raises(KeyboardInterrupt):
        invoke_runner(embedded, "update", expected=before["state"]["sha256"])
    assert (embedded.root / "journal.json").exists()
    attempted_data = embedded.manager._path(embedded.manager.active()["data"])
    (attempted_data / "notes/after-attempt.md").write_text("Preserved failed attempt\n")
    (embedded.root / "fixture-interrupt").unlink()
    pending = invoke_runner(embedded, "inspect")
    recovered = invoke_runner(embedded, "recover", expected=pending["state"]["sha256"])
    assert recovered["ok"] and recovered["recovery_confirmed"] and recovered["recovered"], recovered
    active = embedded.manager.active()
    assert active["version"] == "0.2.0a13"
    assert embedded.manager._path(active["data"]) != old_data
    assert (attempted_data / "notes/after-attempt.md").read_text().startswith("Preserved failed attempt")
    assert not (embedded.manager._path(active["data"]) / "notes/after-attempt.md").exists()
    assert (embedded.manager._path(active["data"]) / "notes/decision.md").read_text().startswith("Synthetic decision")
    with closing(sqlite3.connect(embedded.manager._path(active["data"]) / "mia.db")) as database:
        assert database.execute("SELECT email,password_hash FROM owner").fetchone() == ("owner@example.test", "synthetic-hash")
        assert database.execute("SELECT title FROM tasks").fetchone() == ("Preserve decision",)
        assert database.execute("SELECT COUNT(*) FROM sessions").fetchone() == (0,)
    assert recovered["state"]["paused"] and not recovered["state"]["running"]


def test_clean_recovery_confirms_without_starting_stopped_destination(embedded):
    before = invoke_runner(embedded, "inspect")
    result = invoke_runner(embedded, "recover", expected=before["state"]["sha256"])
    assert result["ok"] and result["recovery_confirmed"] and not result["recovered"]
    assert result["state"]["sha256"] == before["state"]["sha256"]


def test_embedded_archive_traversal_refused_and_original_data_unchanged(embedded):
    before = invoke_runner(embedded, "inspect")
    result = invoke_runner(embedded, "update", expected=before["state"]["sha256"], archive=[("../../escaped", b"bad")])
    assert result == {"ok": False, "code": "artifact_invalid"}
    assert not (embedded.base / "escaped").exists()
    assert embedded.manager.active()["version"] == "0.2.0a13"


def test_dispatcher_rejects_changed_runtime_before_any_execution(embedded, monkeypatch):
    (embedded.base / "artifacts" / IDENTITY / "runtime/bin/python3").write_bytes(b"unknown runtime executable")
    executed = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: executed.append(args) or SimpleNamespace(returncode=0, stdout=b"{}"))
    request = {"action": "inspect", "identity": IDENTITY, "remote_port": 8123, "manifest": embedded.manifest}
    old_stdin = sys.stdin; sys.stdin = SimpleNamespace(buffer=io.BytesIO(json.dumps(request).encode() + b"\n"))
    output = io.StringIO()
    try:
        with redirect_stdout(output):
            exec(compile(remote._REMOTE_OPERATION, "<fixed-runtime-dispatcher>", "exec"), {})
    finally:
        sys.stdin = old_stdin
    assert json.loads(output.getvalue()) == {"ok": False, "code": "runtime_changed"}
    assert executed == []


def test_systemssh_sends_only_authenticated_source_and_wheels_as_structured_stdin(embedded, monkeypatch):
    adapter = remote.SystemSSH(embedded.home)
    observed = {}
    def program(config, known, code, incoming, timeout):
        observed["code"] = code; observed["timeout"] = timeout
        request = json.loads(incoming.readline())
        observed["request"] = request
        with tarfile.open(fileobj=incoming, mode="r|") as archive:
            observed["names"] = [entry.name for entry in archive]
        return {"ok": True}
    monkeypatch.setattr(adapter, "_program", program)
    request = {"action": "update", "identity": IDENTITY, "remote_port": 8123, "manifest": embedded.manifest, "candidate_sha256": digest(embedded.manifest), "expected_state_sha256": "a" * 64}
    assert adapter.operation({"host": "server.example", "user": "tester", "port": 22}, embedded.home / "known-hosts", request, embedded.payload) == {"ok": True}
    assert observed["code"] == remote._REMOTE_OPERATION
    assert observed["timeout"] == 900
    assert observed["request"] == request
    assert set(observed["names"]) == {name for name in embedded.manifest["files"] if name.startswith(("source/", "wheelhouse/"))}
    assert all(not name.startswith("runtime/") for name in observed["names"])


def test_pause_is_not_reported_running_just_because_tunnel_is_alive(controller, monkeypatch):
    client, selected = controller
    directory = client._directory(selected["connection_id"])
    value = json.loads((directory / "connection.json").read_text()); value["paused"] = True
    remote._write(directory / "connection.json", value)
    monkeypatch.setattr(client, "_record", lambda path: {"ready": True})
    assert client.connections()[0]["running"] is False


def test_loaded_foreign_service_process_is_refused_even_when_unit_file_matches(embedded, monkeypatch):
    previous_read = Path.read_bytes
    process_cmdline = Path('/proc') / str(os.getpid()) / 'cmdline'
    monkeypatch.setattr(Path, 'read_bytes', lambda self: b'/foreign/python\0/foreign/worker.py\0' if self == process_cmdline else previous_read(self))
    result = invoke_runner(embedded, 'inspect')
    assert result == {'ok': False, 'code': 'service_changed'}


def test_changed_installed_venv_invalidates_previously_approved_update(embedded):
    before = invoke_runner(embedded, 'inspect')
    venv = embedded.manager._path(embedded.manager.active()['release']) / 'venv'
    (venv / 'foreign-code.py').write_text('raise RuntimeError("synthetic foreign package")\n')
    result = invoke_runner(embedded, 'update', expected=before['state']['sha256'])
    assert result == {'ok': False, 'code': 'approval_changed'}
    assert embedded.manager.active()['version'] == '0.2.0a13'


def test_fifo_private_operation_log_is_refused_without_blocking(embedded):
    before = invoke_runner(embedded, 'inspect')
    os.mkfifo(embedded.root / 'desktop-remote.log', mode=0o600)
    result = invoke_runner(embedded, 'update', expected=before['state']['sha256'])
    assert result['ok'] is False
    assert embedded.manager.active()['version'] == '0.2.0a13'


def test_same_snapshot_review_replayed_after_lost_response_returns_identical_copy(embedded):
    before = invoke_runner(embedded, 'inspect')
    review_id = uuid.uuid4().hex
    first = invoke_runner(embedded, 'snapshot', expected=before['state']['sha256'], review_id=review_id)
    # A response can be lost while the participant continues changing notes.
    # Replaying the exact reviewed operation confirms its original copy.
    data = embedded.manager._path(embedded.manager.active()['data'])
    (data / 'notes/after-snapshot.md').write_text('New synthetic work\n')
    repeated = invoke_runner(embedded, 'snapshot', expected=before['state']['sha256'], review_id=review_id)
    assert repeated['snapshot_id'] == first['snapshot_id']
    assert len(list((embedded.root / 'snapshots').glob('*/snapshot.json'))) == 1
    original = embedded.manager._verify_snapshot('snapshots/' + first['snapshot_id'])
    assert not (original / 'data/notes/after-snapshot.md').exists()
    # A newly reviewed action is a new intended copy, even without changes to
    # runtime/config. It must include the work created since the earlier copy.
    current = invoke_runner(embedded, 'inspect')
    fresh = invoke_runner(embedded, 'snapshot', expected=current['state']['sha256'], review_id=uuid.uuid4().hex)
    assert fresh['snapshot_id'] != first['snapshot_id']
    assert len(list((embedded.root / 'snapshots').glob('*/snapshot.json'))) == 2
    fresh_copy = embedded.manager._verify_snapshot('snapshots/' + fresh['snapshot_id'])
    assert (fresh_copy / 'data/notes/after-snapshot.md').read_text() == 'New synthetic work\n'


def test_snapshot_review_id_cannot_authorize_another_approval(embedded):
    before = invoke_runner(embedded, 'inspect')
    review_id = uuid.uuid4().hex
    invoke_runner(embedded, 'snapshot', expected=before['state']['sha256'], review_id=review_id)
    repeated = invoke_runner(embedded, 'snapshot', expected='0' * 64, review_id=review_id)
    assert repeated == {'ok': False, 'code': 'approval_changed'}
    assert len(list((embedded.root / 'snapshots').glob('*/snapshot.json'))) == 1


@pytest.mark.parametrize('interruption', ['before_complete_receipt', 'before_outer_cleanup'])
def test_interrupted_snapshot_confirmation_recovers_without_copying_newer_work(embedded, monkeypatch, interruption):
    before = invoke_runner(embedded, 'inspect')
    review_id = uuid.uuid4().hex
    receipt_path = embedded.root / 'desktop-receipts' / (review_id + '.json')
    original_replace, original_unlink = os.replace, Path.unlink

    def interrupted_replace(source, destination):
        if Path(destination) == receipt_path and json.loads(Path(source).read_text()).get('phase') == 'complete':
            raise KeyboardInterrupt('synthetic loss before snapshot receipt')
        return original_replace(source, destination)

    def interrupted_unlink(path, *args, **kwargs):
        if path == embedded.root / 'desktop-remote.json':
            raise KeyboardInterrupt('synthetic loss before journal cleanup')
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as fault:
        if interruption == 'before_complete_receipt':
            fault.setattr(os, 'replace', interrupted_replace)
        else:
            fault.setattr(Path, 'unlink', interrupted_unlink)
        with pytest.raises(KeyboardInterrupt):
            invoke_runner(embedded, 'snapshot', expected=before['state']['sha256'], review_id=review_id)

    identifier = 'desktop-remote-' + review_id
    embedded.manager._verify_snapshot('snapshots/' + identifier)
    data = embedded.manager._path(embedded.manager.active()['data'])
    (data / 'notes/newer-work.md').write_text('Must not enter the earlier reviewed copy\n')
    pending = invoke_runner(embedded, 'inspect')
    assert pending['state']['recovery_required'] is True
    retry_before_recovery = invoke_runner(embedded, 'snapshot', expected=before['state']['sha256'], review_id=review_id)
    assert retry_before_recovery == {'ok': False, 'code': 'recovery_required'} or retry_before_recovery.get('state', {}).get('recovery_required') is True
    assert len(list((embedded.root / 'snapshots').glob('*/snapshot.json'))) == 1
    recovered = invoke_runner(embedded, 'recover', expected=pending['state']['sha256'])
    assert recovered['ok'] and recovered['recovery_confirmed']
    assert recovered['state']['recovery_required'] is False
    repeated = invoke_runner(embedded, 'snapshot', expected=before['state']['sha256'], review_id=review_id)
    assert repeated['ok'] and repeated['verified'], repeated
    assert repeated['snapshot_id'] == identifier
    assert json.loads(receipt_path.read_text())['phase'] == 'complete'
    assert len(list((embedded.root / 'snapshots').glob('*/snapshot.json'))) == 1
    assert not (embedded.root / 'snapshots' / identifier / 'data/notes/newer-work.md').exists()


def test_receipt_cannot_adopt_a_different_verified_snapshot(embedded):
    before = invoke_runner(embedded, 'inspect')
    first_review, second_review = uuid.uuid4().hex, uuid.uuid4().hex
    first = invoke_runner(embedded, 'snapshot', expected=before['state']['sha256'], review_id=first_review)
    invoke_runner(embedded, 'snapshot', expected=before['state']['sha256'], review_id=second_review)
    receipt_path = embedded.root / 'desktop-receipts' / (first_review + '.json')
    receipt = json.loads(receipt_path.read_text())
    receipt['snapshot_id'] = 'desktop-remote-' + second_review
    remote._write(receipt_path, receipt)
    repeated = invoke_runner(embedded, 'snapshot', expected=before['state']['sha256'], review_id=first_review)
    assert repeated == {'ok': False, 'code': 'invalid_state'}
    assert first['snapshot_id'] == 'desktop-remote-' + first_review
    assert len(list((embedded.root / 'snapshots').glob('*/snapshot.json'))) == 2
