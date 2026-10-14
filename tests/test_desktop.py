"""Desktop approval, private-state and recovery boundaries; no Mac claims."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import sqlite3
from contextlib import closing
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from mia import __version__
from mia import desktop
from mia.desktop import DesktopController, DesktopError, MACHINE_ENV, PRIVATE_MACHINE_ENV
from mia.launcher import runtime_inventory
from mia.operations import Manager, _write


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    resources = tmp_path / "Mia.app/Contents/Resources"
    source = resources / "source"
    (source / "mia").mkdir(parents=True)
    (source / "pyproject.toml").write_text(f'[project]\nname="mia-personal-ai"\nversion="{__version__}"\n')
    (source / "requirements.lock").write_text("synthetic==1.0\n")
    (source / "mia/__init__.py").write_text(f'__version__="{__version__}"\n')
    (source / "mia/operations.py").write_bytes((Path(__file__).resolve().parents[1] / "mia/operations.py").read_bytes())
    runtime = resources / "runtime"
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin/python3").write_text("synthetic runtime; never execute")
    (runtime / "bin/python3").chmod(0o755)
    wheels = resources / "wheelhouse"
    wheels.mkdir()
    (wheels / "synthetic-1.0-py3-none-any.whl").write_text("synthetic wheel; never install")
    common = {"format": 1, "platform": "macos", "architecture": "x86_64", "python_version": "3.12"}
    report = {"runtime_provenance": {**common, "files": runtime_inventory(runtime)}, "wheelhouse_provenance": {**common, "files": runtime_inventory(wheels)},
              "files": {"Contents/Resources/source/" + name: value for name, value in runtime_inventory(source).items()}}
    (resources / "build-report.json").write_text(json.dumps(report))
    monkeypatch.setattr(desktop.platform, "machine", lambda: "x86_64")
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    return resources, home


def darwin(monkeypatch):
    monkeypatch.setattr(desktop.sys, "platform", "darwin")


def mock_install_worker(controller, monkeypatch, *, failure=False):
    def release(manager, source, wheelhouse=None, offline=False):
        assert offline and wheelhouse == controller.resources / "wheelhouse"
        directory = manager.root / "releases" / ("synthetic-" + uuid.uuid4().hex)
        directory.mkdir()
        if failure:
            (directory / "interrupted.txt").write_text("preserved incomplete synthetic release")
            raise RuntimeError("synthetic installer failure")
        return {"release": str(directory.relative_to(manager.root)), "version": __version__}
    monkeypatch.setattr(Manager, "_release", release)
    monkeypatch.setattr(Manager, "_record", lambda _: {})
    def activate(manager, plan, **kwargs):
        assert kwargs["approve_sha256"] == plan["sha256"]
        assert kwargs["home"] == controller.home
        _write(manager.root / "service-registration.json", {"sha256": plan["sha256"]})
        return {"applied": True}
    monkeypatch.setattr(desktop, "apply_service_plan", activate)
    def worker(state, recover):
        stable = controller._runtime(state, recover=recover)
        monkeypatch.setattr(sys, "_base_executable", str(stable / state["bundle"]["python_relative"]))
        desktop._installation_worker(str(controller.resources), str(controller.home), "recover" if recover else "install")
    monkeypatch.setattr(controller, "_worker", worker)


def test_status_is_read_only_and_unknown_privileged_options_rejected(bundle):
    controller = DesktopController(*bundle)
    before = list(controller.home.iterdir())
    result = controller.handle("status", {})
    assert result["protocol"] == 1 and result["local"]["installed"] is False
    assert list(controller.home.iterdir()) == before
    with pytest.raises(DesktopError, match="opções"):
        controller.handle("local_start", {"root": "/tmp/foreign"})
    with pytest.raises(DesktopError, match="não está disponível"):
        controller.handle("shell", {"command": "anything"})


def test_real_platform_and_architecture_gate_precedes_any_install(bundle, monkeypatch):
    controller = DesktopController(*bundle)
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(DesktopError, match="macOS"):
        controller.handle("local_plan", {})
    assert not controller.root.exists()
    darwin(monkeypatch)
    monkeypatch.setattr(desktop.platform, "machine", lambda: "arm64")
    with pytest.raises(DesktopError, match="arquitetura"):
        controller.handle("local_plan", {})
    assert not controller.root.exists()


def test_approval_covers_port_source_runtime_and_exact_service(bundle, monkeypatch):
    darwin(monkeypatch)
    controller = DesktopController(*bundle)
    plan = controller.handle("local_plan", {})
    assert controller.handle("local_plan", {})["sha256"] == plan["sha256"]
    assert plan["details"]["activation"]["commands"][0][0].startswith(str(controller.base / "runtimes"))
    assert plan["details"]["host"] == "127.0.0.1"
    assert "MIA_AI_ENABLED=false" in plan["details"]["machine_env"]
    original = controller.journal.read_bytes()
    monkeypatch.setattr(controller, "_port_available", lambda port: port != plan["details"]["port"])
    with pytest.raises(DesktopError) as error:
        controller.handle("local_install", {"approve_sha256": plan["sha256"]})
    assert error.value.code == "approval_changed"
    assert controller.journal.read_bytes() == original
    assert not controller.root.exists() and not (controller.base / "runtimes").exists()


@pytest.mark.parametrize("component", ["source/mia/operations.py", "runtime/bin/python3", "wheelhouse/synthetic-1.0-py3-none-any.whl"])
def test_mutation_after_review_is_rejected_before_execution(bundle, monkeypatch, component):
    darwin(monkeypatch)
    controller = DesktopController(*bundle)
    plan = controller.handle("local_plan", {})
    with (controller.resources / component).open("a") as output:
        output.write("mutation")
    monkeypatch.setattr(controller, "_worker", lambda *_args, **_kwargs: pytest.fail("must not execute changed artifacts"))
    with pytest.raises(DesktopError) as error:
        controller.handle("local_install", {"approve_sha256": plan["sha256"]})
    assert error.value.code == "invalid_bundle"
    assert not controller.root.exists()


def test_private_home_ancestor_and_metadata_symlinks_are_refused(bundle, tmp_path):
    resources, home = bundle
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (home / "Library").symlink_to(foreign)
    with pytest.raises(DesktopError, match="link simbólico"):
        DesktopController(resources, home)
    assert list(foreign.iterdir()) == []


def test_private_metadata_symlink_never_reads_outside_installation(bundle, tmp_path):
    controller = DesktopController(*bundle)
    controller.root.mkdir(mode=0o700, parents=True)
    private = tmp_path / "foreign-secret.json"
    private.write_text('{"secret":"synthetic-never-disclose"}')
    (controller.root / "installation.json").symlink_to(private)
    with pytest.raises(DesktopError) as error:
        controller.handle("status", {})
    assert error.value.code == "unsafe_path"
    assert "synthetic-never-disclose" not in str(error.value)
    assert private.read_text() == '{"secret":"synthetic-never-disclose"}'


def test_existing_installation_never_becomes_empty_install(bundle, monkeypatch):
    darwin(monkeypatch)
    controller = DesktopController(*bundle)
    controller.root.mkdir(mode=0o700, parents=True)
    (controller.root / "personal-note.md").write_text("private synthetic context")
    with pytest.raises(DesktopError) as error:
        controller.handle("local_plan", {})
    assert error.value.code == "recovery_required"
    assert controller.handle("status", {})["local"]["recovery_required"]
    with pytest.raises(Exception):
        controller.handle("local_recover", {})
    assert (controller.root / "personal-note.md").read_text() == "private synthetic context"


def test_install_uses_stable_runtime_and_explicit_empty_local_configuration(bundle, monkeypatch):
    darwin(monkeypatch)
    controller = DesktopController(*bundle)
    plan = controller.handle("local_plan", {})
    mock_install_worker(controller, monkeypatch)
    monkeypatch.setenv("MIA_AI_ENABLED", "true")
    monkeypatch.setenv("MIA_DATA_DIR", "/tmp/foreign-private-data")
    result = controller.handle("local_install", {"approve_sha256": plan["sha256"]})
    assert result["installed"] and not result["recovery_required"]
    assert result["installation_id"] == plan["details"]["installation_id"]
    assert (controller.root / "machine.env").read_text() == PRIVATE_MACHINE_ENV
    assert (controller.root / "bootstrap-token").stat().st_mode & 0o777 == 0o600
    assert list((controller.root / "data/initial").iterdir()) == []
    configuration = json.loads((controller.root / "installation.json").read_text())
    assert configuration["python"].startswith(str(controller.base / "runtimes"))
    assert configuration["private_bootstrap"] is True
    assert not configuration["python"].startswith(str(controller.resources))
    assert controller.handle("local_bundle_plan", {})["update_available"] is False
    stopped = controller.handle("local_stop", {})
    assert stopped["paused"] and controller.handle("status", {})["local"]["paused"]


def test_bootstrap_secret_only_reaches_native_ipc_for_verified_empty_instance(bundle, monkeypatch):
    darwin(monkeypatch)
    controller = DesktopController(*bundle)
    plan = controller.handle("local_plan", {})
    mock_install_worker(controller, monkeypatch)
    initial = controller.handle("local_install", {"approve_sha256": plan["sha256"]})
    assert "bootstrap_token" not in initial  # No verified ready process yet.
    configuration = json.loads((controller.root / "installation.json").read_text())
    state = {"configured": False, "version": __version__, "installation_id": configuration["installation_id"], "bootstrap_protected": True, "desktop_protocol": 1, "cookie_secure": False, "transport_policy": "private_connection_only", "redirect": False}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if state["redirect"]:
                self.send_response(302)
                self.send_header("Location", "https://example.invalid/")
                self.end_headers()
                return
            value = {"configured": state["configured"], "version": state["version"]} if self.path == "/api/status" else {key: state[key] for key in ("installation_id", "bootstrap_protected", "desktop_protocol", "version", "cookie_secure", "transport_policy")}
            payload = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self, *_args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        configuration["port"] = server.server_port
        _write(controller.root / "installation.json", configuration)
        monkeypatch.setattr(Manager, "_record", lambda _: {"ready": True})
        token = (controller.root / "bootstrap-token").read_text().strip()
        assert controller.handle("status", {})["local"]["bootstrap_token"] == token
        for change in ({"configured": True}, {"installation_id": str(uuid.uuid4())}, {"bootstrap_protected": False}, {"version": "0.0.0"}, {"redirect": True}, {"desktop_protocol": True}, {"desktop_protocol": 1.0}, {"cookie_secure": True}, {"transport_policy": "https_required"}):
            before = dict(state)
            state.update(change)
            response = controller.handle("status", {})
            assert "bootstrap_token" not in response["local"]
            assert token not in json.dumps(response)
            state.update(before)
        (controller.root / "bootstrap-token").chmod(0o644)
        with pytest.raises(DesktopError) as error:
            controller.handle("status", {})
        assert error.value.code == "bootstrap_unavailable" and token not in str(error.value)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("mutation", ["missing", "short", "extra_newline", "unicode", "shared", "symlink", "fifo"])
def test_native_bootstrap_file_reader_refuses_invalid_state_without_disclosing_it(tmp_path, mutation):
    token = tmp_path / "bootstrap-token"
    raw = b"A" * 43 + b"\n"
    token.write_bytes(raw)
    token.chmod(0o600)
    if mutation == "missing":
        token.unlink()
    elif mutation == "short":
        token.write_bytes(b"untrusted private input\n")
    elif mutation == "extra_newline":
        token.write_bytes(raw + b"\n")
    elif mutation == "unicode":
        token.write_bytes(b"A" * 41 + b"\xc3\xa1\n")
    elif mutation == "shared":
        token.chmod(0o644)
    elif mutation == "symlink":
        retained = tmp_path / "retain-token"
        token.rename(retained)
        token.symlink_to(retained)
    elif mutation == "fifo":
        token.unlink()
        os.mkfifo(token, mode=0o600)
    with pytest.raises(DesktopError) as error:
        desktop._private_bootstrap_token(token)
    assert error.value.code in ("bootstrap_unavailable", "unsafe_path")
    assert "A" * 43 not in str(error.value) and "untrusted private input" not in str(error.value)


def test_subprocess_does_not_inherit_secrets_or_python_pip_settings(bundle, monkeypatch):
    darwin(monkeypatch)
    controller = DesktopController(*bundle)
    controller.handle("local_plan", {})
    state = json.loads(controller.journal.read_text())
    captured = {}
    monkeypatch.setenv("MIA_AI_API_KEY", "synthetic-credential")
    monkeypatch.setenv("PYTHONPATH", "/tmp/foreign")
    monkeypatch.setenv("PIP_EXTRA_INDEX_URL", "https://secret@example.invalid")
    def run(command, **kwargs):
        captured.update(command=command, **kwargs)
    monkeypatch.setattr(subprocess, "run", run)
    controller._worker(state, recover=False)
    assert captured["command"][0].startswith(str(controller.base / "runtimes"))
    assert not any(key.startswith("MIA_") for key in captured["env"])
    assert captured["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert "PYTHONPATH" not in captured["env"] and "PYTHONHOME" not in captured["env"]
    assert "PIP_EXTRA_INDEX_URL" not in captured["env"]
    assert captured["env"]["PIP_CONFIG_FILE"] == os.devnull
    assert captured["env"]["PIP_NO_INDEX"] == "1"
    assert "synthetic-credential" not in json.dumps(captured["command"])


def test_failed_partial_install_only_resumes_explicitly_and_preserves_attempt(bundle, monkeypatch):
    darwin(monkeypatch)
    controller = DesktopController(*bundle)
    plan = controller.handle("local_plan", {})
    mock_install_worker(controller, monkeypatch, failure=True)
    with pytest.raises(RuntimeError, match="synthetic"):
        controller.handle("local_install", {"approve_sha256": plan["sha256"]})
    partials = list((controller.root / "releases").glob("*/interrupted.txt"))
    assert len(partials) == 1
    original_configuration = (controller.root / "installation.json").read_bytes()
    original_environment = (controller.root / "machine.env").read_bytes()
    original_token = (controller.root / "bootstrap-token").read_bytes()
    status = controller.handle("status", {})["local"]
    assert not status["installed"] and status["recovery_required"]
    with pytest.raises(DesktopError, match="recuperação"):
        controller.handle("local_start", {})
    mock_install_worker(controller, monkeypatch)
    result = controller.handle("local_recover", {})
    assert result["installed"] and not result["recovery_required"]
    assert partials[0].read_text() == "preserved incomplete synthetic release"
    assert result["installation_id"] == plan["details"]["installation_id"]
    assert (controller.root / "installation.json").read_bytes() == original_configuration
    assert (controller.root / "machine.env").read_bytes() == original_environment
    assert (controller.root / "bootstrap-token").read_bytes() == original_token


def test_partial_recovery_completes_protection_only_before_configuration_publication(bundle, monkeypatch):
    darwin(monkeypatch)
    controller = DesktopController(*bundle)
    plan = controller.handle("local_plan", {})
    mock_install_worker(controller, monkeypatch, failure=True)
    with pytest.raises(RuntimeError):
        controller.handle("local_install", {"approve_sha256": plan["sha256"]})
    # Simulate a kill after the reviewed defaults were copied but before the
    # private flag, token and installation configuration were published.
    (controller.root / "installation.json").unlink()
    (controller.root / "bootstrap-token").unlink()
    (controller.root / "machine.env").write_text(MACHINE_ENV)
    mock_install_worker(controller, monkeypatch)
    result = controller.handle("local_recover", {})
    assert result["installed"] and result["installation_id"] == plan["details"]["installation_id"]
    assert (controller.root / "machine.env").read_text() == PRIVATE_MACHINE_ENV
    assert len(desktop._private_bootstrap_token(controller.root / "bootstrap-token")) == 43


@pytest.mark.parametrize("mutation", ["missing_token", "malformed_token", "shared_token", "token_symlink", "disabled_environment", "changed_configuration"])
def test_partial_recovery_refuses_altered_private_handoff_without_rotating_token(bundle, monkeypatch, mutation):
    darwin(monkeypatch)
    controller = DesktopController(*bundle)
    plan = controller.handle("local_plan", {})
    mock_install_worker(controller, monkeypatch, failure=True)
    with pytest.raises(RuntimeError):
        controller.handle("local_install", {"approve_sha256": plan["sha256"]})
    token = controller.root / "bootstrap-token"
    if mutation == "missing_token":
        token.unlink()
    elif mutation == "malformed_token":
        token.write_bytes(b"malformed private authorization\n")
    elif mutation == "shared_token":
        token.chmod(0o644)
    elif mutation == "token_symlink":
        retained = controller.home / "preserved-private-token"
        token.rename(retained)
        token.symlink_to(retained)
    elif mutation == "disabled_environment":
        (controller.root / "machine.env").write_text(MACHINE_ENV)
    else:
        configuration = json.loads((controller.root / "installation.json").read_text())
        configuration["private_bootstrap"] = False
        _write(controller.root / "installation.json", configuration)
    before_environment = (controller.root / "machine.env").read_bytes()
    before_configuration = (controller.root / "installation.json").read_bytes()
    before_token = token.read_bytes() if token.exists() else None
    releases = sorted(path.name for path in (controller.root / "releases").iterdir())
    mock_install_worker(controller, monkeypatch)
    with pytest.raises(Exception):
        controller.handle("local_recover", {})
    assert (controller.root / "machine.env").read_bytes() == before_environment
    assert (controller.root / "installation.json").read_bytes() == before_configuration
    assert (token.read_bytes() if token.exists() else None) == before_token
    assert sorted(path.name for path in (controller.root / "releases").iterdir()) == releases
    assert not (controller.root / "active.json").exists()


def test_partial_recovery_refuses_user_data_and_changed_bundle(bundle, monkeypatch):
    darwin(monkeypatch)
    controller = DesktopController(*bundle)
    plan = controller.handle("local_plan", {})
    mock_install_worker(controller, monkeypatch, failure=True)
    with pytest.raises(RuntimeError):
        controller.handle("local_install", {"approve_sha256": plan["sha256"]})
    (controller.root / "data/initial/personal-note.md").write_text("retain this synthetic note")
    mock_install_worker(controller, monkeypatch)
    with pytest.raises(Exception, match="Dados existentes"):
        controller.handle("local_recover", {})
    assert (controller.root / "data/initial/personal-note.md").read_text() == "retain this synthetic note"
    report = controller.resources / "build-report.json"
    value = json.loads(report.read_text())
    value["new_build_metadata"] = True
    report.write_text(json.dumps(value))
    with pytest.raises(DesktopError) as error:
        controller.handle("local_recover", {})
    assert error.value.code == "bundle_changed"


def test_native_snapshot_verifies_content_and_excludes_unapproved_uploads(bundle, monkeypatch):
    darwin(monkeypatch)
    controller = DesktopController(*bundle)
    plan = controller.handle("local_plan", {})
    mock_install_worker(controller, monkeypatch)
    controller.handle("local_install", {"approve_sha256": plan["sha256"]})
    data = controller.root / "data/initial"
    monkeypatch.setenv("MIA_DATA_DIR", str(data))
    from mia import db
    db.initialize()
    with closing(db.connect()) as database:
        database.execute("INSERT INTO owner(id,name,email,timezone,password_hash,created_at) VALUES(1,'Synthetic','synthetic@example.test','UTC','synthetic','now')")
    (data / "approved-note.md").write_text("preserve synthetic approved source")
    (data / "migration-staging").mkdir()
    (data / "migration-staging/unapproved.md").write_text("not approved")
    result = controller.handle("local_snapshot", {})
    assert result["verified"] and result["details"]["external_backup"] is False
    manager = Manager(controller.root)
    snapshot = manager._verify_snapshot("snapshots/" + result["snapshot_id"])
    assert (snapshot / "data/approved-note.md").read_text() == "preserve synthetic approved source"
    assert not (snapshot / "data/migration-staging").exists()
    with closing(sqlite3.connect(snapshot / "data/mia.db")) as database:
        assert database.execute("SELECT name FROM owner").fetchone() == ("Synthetic",)
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    (snapshot / "data/approved-note.md").write_text("changed")
    with pytest.raises(Exception, match="alterado"):
        manager._verify_snapshot("snapshots/" + result["snapshot_id"])


def test_already_bundled_update_uses_stable_manager_and_preserves_library(bundle, monkeypatch):
    darwin(monkeypatch)
    controller = DesktopController(*bundle)
    install = controller.handle("local_plan", {})
    mock_install_worker(controller, monkeypatch)
    original = controller.handle("local_install", {"approve_sha256": install["sha256"]})
    controller.handle("local_stop", {})
    (controller.root / "data/initial/approved.md").write_text("keep synthetic context across updates")
    candidate = "0.2.0a99"
    monkeypatch.setattr(desktop, "__version__", candidate)
    (controller.resources / "source/pyproject.toml").write_text(f'[project]\nname="mia-personal-ai"\nversion="{candidate}"\n')
    report_path = controller.resources / "build-report.json"
    report = json.loads(report_path.read_text())
    report["files"] = {"Contents/Resources/source/" + name: value for name, value in runtime_inventory(controller.resources / "source").items()}
    report_path.write_text(json.dumps(report))
    plan = controller.handle("local_bundle_plan", {})
    assert plan["update_available"] and plan["current_version"] == __version__
    calls = []
    def release(manager, source, wheelhouse=None, offline=False):
        assert source == controller.resources / "source" and offline
        directory = manager.root / "releases/candidate"
        directory.mkdir()
        return {"release": "releases/candidate", "version": candidate}
    monkeypatch.setattr(Manager, "_release", release)
    monkeypatch.setattr(Manager, "_start", lambda *_args, **_kwargs: None)
    def run(command, **kwargs):
        calls.append(command)
        assert command[0] == json.loads((controller.root / "installation.json").read_text())["python"]
        assert command[1] == str(controller.root / "manager.py")
        assert "MIA_AI_API_KEY" not in kwargs["env"]
        Manager(controller.root).update(controller.resources / "source", wheelhouse=controller.resources / "wheelhouse", offline=True)
    monkeypatch.setattr(subprocess, "run", run)
    result = controller.handle("local_bundle_update", {"approve_sha256": plan["sha256"]})
    assert len(calls) == 1 and result["version"] == candidate
    assert result["paused"] and not result["running"]
    assert result["installation_id"] == original["installation_id"]
    assert (controller.root / "data/initial/approved.md").read_text() == "keep synthetic context across updates"
    snapshots = list((controller.root / "snapshots").glob("*/data/approved.md"))
    assert len(snapshots) == 1 and snapshots[0].read_text() == "keep synthetic context across updates"


def test_bridge_has_one_bounded_json_response_and_no_sensitive_errors(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/desktop_bridge.py"
    cases = [b"not-json", b'{"action":"status","action":"shell","payload":{}}', b"{" + b"x" * 65536,
             json.dumps({"action": "shell", "payload": {"command": "synthetic-secret-command"}}).encode()]
    for raw in cases:
        result = subprocess.run([sys.executable, "-I", str(script)], input=raw, capture_output=True, env={"HOME": str(tmp_path)}, check=True)
        decoded = json.loads(result.stdout)
        assert decoded["ok"] is False
        assert result.stdout.count(b"\n") == 1
        assert b"synthetic-secret-command" not in result.stdout and result.stderr == b""


def test_packaged_bridge_does_not_change_verified_source_inventory(tmp_path):
    from scripts import package_macos
    from test_macos_launcher import artifacts
    inputs = artifacts(tmp_path)
    output = tmp_path / "Mia.app"
    package_macos.build(output, *inputs)
    resources = output / "Contents/Resources"
    script = resources / "desktop_bridge.py"
    # Legacy builder compatibility may omit the native bridge; copying only the
    # entrypoint here still exercises the actual bundled source import path.
    if not script.exists():
        script.write_bytes((Path(__file__).resolve().parents[1] / "scripts/desktop_bridge.py").read_bytes())
    before = runtime_inventory(resources / "source")
    home = tmp_path / "clean-home"
    home.mkdir(mode=0o700)
    result = subprocess.run([sys.executable, "-I", "-B", str(script)], input=b'{"action":"status","payload":{}}', capture_output=True,
                            env={"HOME": str(home)}, check=True)
    response = json.loads(result.stdout)
    assert response["ok"] is True and response["result"]["local"]["installed"] is False
    assert runtime_inventory(resources / "source") == before
    assert list(home.iterdir()) == []
