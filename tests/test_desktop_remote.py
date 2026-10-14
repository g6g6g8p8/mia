"""Native remote boundary tests with an adapter; never contact personal hosts."""
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from mia.desktop_remote import RemoteController, RemoteError, SystemSSH, _fingerprint, _write, artifact


KEY = base64.b64encode(b"fixture-server-ed25519-public-key-not-a-secret").decode()
FINGERPRINT = _fingerprint(KEY)
IDENTITY = "5cdd414b-7271-4503-b817-f764cbd0b900"
HOST = {"host": "my-server.example", "user": "tester"}


def backend(identity=IDENTITY, secure=False, configured=False):
    return {"health": {"ok": True, "version": "0.2.0a13"}, "status": {"configured": configured, "version": "0.2.0a13"}, "installation": {"installation_id": identity, "version": "0.2.0a13", "desktop_protocol": 1, "cookie_secure": secure, "transport_policy": "https_required" if secure else "private_connection_only"}}


class FixtureSSH:
    def __init__(self):
        self.key = KEY
        self.known_host = False
        self.changed = False
        self.calls = []
        self.liveness = {}
        self.server = backend()
        self.http_server = self.server
        self.offline = False
        self.probe_result = {"platform": "ubuntu", "platform_version": "24.04", "architecture": "x86_64", "home_safe": True, "free_bytes": 10 * 1024**3, "user_service": True, "linger": True, "port_available": True, "backend": None}

    def scan(self, config):
        self.calls.append("scan")
        return self.key

    def known(self, config, key):
        self.calls.append("known")
        return self.known_host, self.changed

    def probe(self, config, pin):
        self.calls.append("authenticated_probe")
        return dict(self.probe_result)

    def install(self, config, pin, manifest, directory, identity):
        self.calls.append("install")
        self.probe_result.update(port_available=False, backend=self.server)
        return {"ok": True, "version": manifest["version"], "root_id": identity, "installation_id": IDENTITY, "service_activated": True}

    def spawn(self, state, resources):
        self.calls.append("spawn")
        self.liveness.update({3400: "fixture-birth", 3401: "fixture-child-birth"})
        _write(state.parent / "process.json", {"pid": 3400, "birth": "fixture-birth", "child_pid": 3401, "child_birth": "fixture-child-birth", "ready": True})

    def birth(self, pid):
        return self.liveness.get(pid)

    def stop(self, record):
        for prefix in ("", "child_"):
            pid, birth = record.get(prefix + "pid"), record.get(prefix + "birth")
            if pid and birth and self.birth(pid) == birth:
                self.calls.append(("stop", pid))
                self.liveness.pop(pid)

    def http(self, url):
        self.calls.append(("http", url))
        if self.offline:
            raise RemoteError("connection_offline", "Servidor indisponível.")
        path = "health" if url.endswith("/health") else "status" if url.endswith("/api/status") else "installation"
        return dict(self.http_server[path])


@pytest.fixture
def controller(tmp_path):
    home, resources = tmp_path / "home", tmp_path / "resources"
    home.mkdir()
    resources.mkdir()
    ssh = FixtureSSH()
    return RemoteController(resources, home, adapter=ssh)


def add_artifact(resources):
    root = resources / "remote-runtime"
    payload = root / "payload"
    files = {"runtime/bin/python3": b"fixture executable\n", "source/mia/operations.py": b"# fixture\n", "source/requirements.lock": b"", "source/LICENSE": b"Apache-2.0\n", "source/NOTICE": b"Mia\n", "source/THIRD_PARTY_NOTICES.md": b"fixture\n", "source/pyproject.toml": b'[project]\nname="mia-personal-ai"\nversion="0.2.0a13"\n', "wheelhouse/example-1.0-py3-none-any.whl": b"fixture wheel\n"}
    inventory = {}
    for name, content in files.items():
        path = payload / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(0o755 if name == "runtime/bin/python3" else 0o644)
        inventory[name] = {"sha256": hashlib.sha256(content).hexdigest(), "executable": name == "runtime/bin/python3"}
    manifest = {"format": 1, "platform": "ubuntu24.04", "architecture": "amd64", "python_version": "3.12", "version": "0.2.0a13", "files": inventory}
    for kind, origin in (("runtime", "https://github.com/astral-sh/python-build-standalone/releases/download/reviewed/fixture.tar.gz"), ("wheelhouse", "https://pypi.org/")):
        manifest[kind + "_provenance"] = {"format": 1, "platform": "linux", "architecture": "x86_64", "python_version": "3.12", "source_url": origin, "files": {name[len(kind) + 1:]: details for name, details in inventory.items() if name.startswith(kind + "/")}}
    (root / "manifest.json").write_text(json.dumps(manifest))
    return root, payload


def approved(**extra):
    return {**HOST, "approved_host_fingerprint": FINGERPRINT, **extra}


def test_unknown_host_never_sends_authenticated_command(controller):
    result = controller.handle("remote_preflight", HOST)
    assert result["host_key_fingerprint"] == FINGERPRINT
    assert result["approval_required"] is True
    assert result["install_ready"] is False
    assert controller.adapter.calls == ["scan", "known"]
    with pytest.raises(RemoteError, match="Confirme") as error:
        controller.handle("remote_connect", HOST)
    assert error.value.code == "host_approval_required"
    assert "authenticated_probe" not in controller.adapter.calls


def test_exact_approval_is_pinned_and_changed_host_cannot_be_reapproved(controller):
    controller.handle("remote_preflight", approved())
    assert "authenticated_probe" in controller.adapter.calls
    controller.adapter.calls.clear()
    controller.adapter.key = base64.b64encode(b"different-server-key" * 3).decode()
    with pytest.raises(RemoteError) as error:
        controller.handle("remote_preflight", {**HOST, "approved_host_fingerprint": _fingerprint(controller.adapter.key)})
    assert error.value.code == "host_key_changed"
    assert "authenticated_probe" not in controller.adapter.calls


@pytest.mark.parametrize("value", [{"host": "server; rm -rf /", "user": "tester"}, {"host": "$(secret)", "user": "tester"}, {"host": "-oProxyCommand=echo", "user": "tester"}, {"host": "example.org", "user": "tester;id"}, {"host": "example.org", "user": "tester", "port": True}, {"host": "example.org", "user": "tester", "remote_port": 65536}])
def test_host_user_and_port_injections_rejected_before_transport(controller, value):
    with pytest.raises(RemoteError):
        controller.handle("remote_preflight", value)
    assert controller.adapter.calls == []


def test_key_symlinks_and_shared_permissions_rejected(controller):
    key = controller.home / "ssh-key"
    key.write_text("must never read or log this private key")
    key.chmod(0o644)
    with pytest.raises(RemoteError) as error:
        controller.handle("remote_preflight", approved(key_path=str(key)))
    assert error.value.code == "unsafe_path"
    key.chmod(0o600)
    link = controller.home / "link"
    link.symlink_to(key)
    with pytest.raises(RemoteError):
        controller.handle("remote_preflight", approved(key_path=str(link)))
    assert controller.adapter.calls == []


def test_missing_artifact_never_claims_installation_ready(controller):
    result = controller.handle("remote_preflight", approved())
    assert result["supported"] is True
    assert result["install_ready"] is False
    assert result["artifact_state"] == "artifact_unavailable"
    assert "plan_sha256" not in result
    assert "install" not in controller.adapter.calls


def test_full_install_uses_approved_exact_artifact_then_checks_identity(controller):
    add_artifact(controller.resources)
    plan = controller.handle("remote_preflight", approved())
    assert plan["install_ready"] is True
    stable_plan = controller.handle("remote_preflight", approved())
    assert stable_plan["plan_sha256"] == plan["plan_sha256"]
    result = controller.handle("remote_install", approved(approve_sha256=plan["plan_sha256"]))
    assert result["mode"] == "ssh" and result["running"] is True
    assert result["installation_id"] == IDENTITY and result["configured"] is False
    assert controller.adapter.calls.count("install") == 1
    assert controller.adapter.calls.count("spawn") == 1
    # One short-lived bridge can be replaced by another without creating a new
    # backend, session identity or tunnel when the verified process is alive.
    replacement = RemoteController(controller.resources, controller.home, adapter=controller.adapter)
    connected = replacement.handle("remote_connect", approved())
    assert connected["connection_id"] == result["connection_id"] and connected["url"] == result["url"]
    assert controller.adapter.calls.count("spawn") == 1


def test_artifact_mutation_after_approval_stops_before_remote_install(controller):
    _, payload = add_artifact(controller.resources)
    plan = controller.handle("remote_preflight", approved())
    (payload / "runtime/bin/python3").write_bytes(b"tampered executable")
    with pytest.raises(RemoteError) as error:
        controller.handle("remote_install", approved(approve_sha256=plan["plan_sha256"]))
    assert error.value.code == "artifact_invalid"
    assert "install" not in controller.adapter.calls


def test_payload_ancestry_and_runtime_link_cannot_escape_bundle(controller):
    _, payload = add_artifact(controller.resources)
    external = controller.home / "external"
    external.write_text("external")
    (payload / "runtime/external").symlink_to(external)
    with pytest.raises(RemoteError) as error:
        artifact(controller.resources)
    assert error.value.code == "artifact_invalid"


def test_modified_plan_and_changed_server_never_install(controller):
    add_artifact(controller.resources)
    result = controller.handle("remote_preflight", approved())
    plan_path = next(controller.base.glob("*.plan.json"))
    plan = json.loads(plan_path.read_text())
    plan["summary"].append("not approved")
    _write(plan_path, plan)
    with pytest.raises(RemoteError) as error:
        controller.handle("remote_install", approved(approve_sha256=result["plan_sha256"]))
    assert error.value.code == "plan_approval_required"
    result = controller.handle("remote_preflight", approved())
    controller.adapter.probe_result["port_available"] = False
    with pytest.raises(RemoteError) as error:
        controller.handle("remote_install", approved(approve_sha256=result["plan_sha256"]))
    assert error.value.code == "preflight_changed"
    assert "install" not in controller.adapter.calls


@pytest.mark.parametrize("key,value", [("linger", False), ("user_service", False), ("home_safe", False), ("free_bytes", 1024), ("architecture", "aarch64"), ("port_available", False)])
def test_unsupported_conditions_are_real_gates(controller, key, value):
    add_artifact(controller.resources)
    controller.adapter.probe_result[key] = value
    result = controller.handle("remote_preflight", approved())
    assert result["install_ready"] is False
    assert "plan_sha256" not in result


def test_secure_existing_installation_is_not_downgraded_for_ssh(controller):
    controller.adapter.probe_result.update(port_available=False, backend=backend(secure=True))
    with pytest.raises(RemoteError) as error:
        controller.handle("remote_connect", approved())
    assert error.value.code == "https_required"
    assert "spawn" not in controller.adapter.calls and "install" not in controller.adapter.calls


def test_pid_reuse_is_never_signalled_and_remote_backend_is_preserved(controller):
    controller.adapter.probe_result.update(port_available=False, backend=backend())
    result = controller.handle("remote_connect", approved())
    controller.adapter.liveness = {3400: "unrelated-reused-pid", 3401: "unrelated-reused-child"}
    controller.adapter.calls.clear()
    stopped = controller.handle("remote_disconnect", {"connection_id": result["connection_id"]})
    assert stopped["running"] is False
    assert not any(isinstance(call, tuple) and call[0] == "stop" for call in controller.adapter.calls)
    assert "authenticated_probe" not in controller.adapter.calls and "install" not in controller.adapter.calls
    assert controller.connections()[0]["installation_id"] == IDENTITY


def test_offline_https_preserves_connection_no_reinstall_and_changed_identity_refused(controller):
    connected = controller.handle("https_connect", {"url": "https://mia.example/"})
    assert connected["running"] is True
    controller.adapter.offline = True
    with pytest.raises(RemoteError) as error:
        controller.handle("https_connect", {"url": "https://mia.example/"})
    assert error.value.code == "connection_offline"
    assert controller.connections()[0]["installation_id"] == IDENTITY
    controller.adapter.offline = False
    controller.adapter.http_server = backend(identity=str(uuid.uuid4()))
    with pytest.raises(RemoteError) as error:
        controller.handle("https_connect", {"url": "https://mia.example/"})
    assert error.value.code == "installation_changed"
    assert "install" not in controller.adapter.calls


def test_reopening_dead_tunnel_preserves_identity_and_port(controller):
    controller.adapter.probe_result.update(port_available=False, backend=backend())
    first = controller.handle("remote_connect", approved())
    controller.adapter.liveness.clear()
    second = controller.handle("remote_connect", approved())
    assert second["connection_id"] == first["connection_id"]
    assert second["installation_id"] == first["installation_id"]
    assert second["url"] == first["url"]
    assert controller.adapter.calls.count("spawn") == 2
    assert "install" not in controller.adapter.calls


def test_reconnect_by_connection_id_uses_private_stored_key_without_returning_it(controller):
    controller.adapter.probe_result.update(port_available=False, backend=backend())
    key = controller.home / "private-key"
    key.write_text("fixture secret must never be returned")
    key.chmod(0o600)
    first = controller.handle("remote_connect", approved(key_path=str(key)))
    assert "key_path" not in first
    controller.adapter.liveness.clear()
    second = controller.handle("remote_connect", {"connection_id": first["connection_id"]})
    assert second["url"] == first["url"] and "key_path" not in second
    assert controller.adapter.calls.count("spawn") == 2


def test_destination_change_refuses_tunnel_reuse(controller):
    controller.adapter.probe_result.update(port_available=False, backend=backend())
    first = controller.handle("remote_connect", approved())
    controller.adapter.probe_result["backend"] = backend(identity=str(uuid.uuid4()))
    with pytest.raises(RemoteError) as error:
        controller.handle("remote_connect", approved())
    assert error.value.code == "installation_changed"
    assert controller.adapter.calls.count("spawn") == 1
    assert controller.connections()[0]["installation_id"] == first["installation_id"]


def test_dead_ssh_child_is_not_reported_alive_when_supervisor_pid_survives(controller):
    controller.adapter.probe_result.update(port_available=False, backend=backend())
    first = controller.handle("remote_connect", approved())
    controller.adapter.liveness.pop(3401)
    assert controller.connections()[0]["running"] is False
    second = controller.handle("remote_connect", approved())
    assert second["connection_id"] == first["connection_id"]
    assert controller.adapter.calls.count("spawn") == 2


def test_failed_remote_install_retains_plan_and_never_opens_backend(controller, monkeypatch):
    add_artifact(controller.resources)
    plan = controller.handle("remote_preflight", approved())
    monkeypatch.setattr(controller.adapter, "install", lambda *args: {"ok": False, "code": "recovery_required"})
    with pytest.raises(RemoteError) as error:
        controller.handle("remote_install", approved(approve_sha256=plan["plan_sha256"]))
    assert error.value.code == "recovery_required"
    assert next(controller.base.glob("*.plan.json")).exists()
    assert "spawn" not in controller.adapter.calls


def test_live_loopback_preflight_returns_only_public_metadata(tmp_path):
    from mia.desktop_remote import _PROBE
    server_backend = backend()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            key = {"/health": "health", "/api/status": "status", "/api/installation": "installation"}.get(self.path)
            self.send_response(200 if key else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(server_backend.get(key, {})).encode())
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run([sys.executable, "-I", "-c", _PROBE], input=json.dumps({"remote_port": server.server_port}), text=True, capture_output=True, timeout=15, env={**os.environ, "HOME": str(tmp_path), "OPENROUTER_API_KEY": "must-not-appear-in-probe"})
        assert result.returncode == 0, result.stderr
        state = json.loads(result.stdout)
        assert state["port_available"] is False
        assert state["backend"] == server_backend
        assert "must-not-appear-in-probe" not in result.stdout
        assert set(state) == {"platform", "platform_version", "architecture", "home_safe", "free_bytes", "user_service", "linger", "port_available", "backend"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("url", ["http://mia.example", "https://user:secret@mia.example", "https://mia.example/?token=secret", "https://mia.example/app", "https://mia.example/#secret"])
def test_https_rejects_plaintext_credentials_and_unsupported_paths(controller, url):
    with pytest.raises(OperationError):
        controller.handle("https_connect", {"url": url})
    assert controller.adapter.calls == []


def test_ssh_arguments_ignore_user_config_and_keep_host_checking(tmp_path):
    adapter = SystemSSH(tmp_path)
    args = adapter.arguments({"host": "server.example", "user": "tester", "port": 2222, "remote_port": 8123, "key_path": str(tmp_path / "key with spaces")}, tmp_path / "private_known_hosts")
    assert args[:4] == ["/usr/bin/ssh", "-F", "/dev/null", "-T"]
    assert "StrictHostKeyChecking=yes" in args and "ForwardAgent=no" in args
    assert not any("StrictHostKeyChecking=no" in item or "ProxyCommand" in item for item in args)
    assert args[-1] == str(tmp_path / "key with spaces")


def test_known_hosts_absent_entry_is_not_a_transport_failure(tmp_path, monkeypatch):
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    (ssh / "known_hosts").write_text("unrelated.example ssh-ed25519 " + KEY + "\n")
    adapter = SystemSSH(tmp_path)
    assert adapter.known({"host": "unmatched.example", "port": 22}, KEY) == (False, False)


def test_revoked_host_key_cannot_be_bypassed_by_manual_approval(tmp_path):
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    (ssh / "known_hosts").write_text("@revoked my-server.example ssh-ed25519 " + KEY + "\n")
    adapter = SystemSSH(tmp_path)
    with pytest.raises(RemoteError) as error:
        adapter.known({"host": "my-server.example", "port": 22}, KEY)
    assert error.value.code == "host_key_revoked"
    resources = tmp_path / "resources"
    resources.mkdir()
    adapter.scan = lambda config: KEY
    controller = RemoteController(resources, tmp_path, adapter=adapter)
    with pytest.raises(RemoteError) as error:
        controller.handle("remote_preflight", approved())
    assert error.value.code == "host_key_revoked"
    assert not list(controller.base.glob("*.known_hosts")) if controller.base.exists() else True


def test_system_stop_rechecks_process_birth_at_signal_time(tmp_path, monkeypatch):
    adapter = SystemSSH(tmp_path)
    stopped = []
    monkeypatch.setattr(adapter, "birth", lambda pid: "different")
    monkeypatch.setattr(os, "kill", lambda pid, sig: stopped.append(pid))
    adapter.stop({"pid": 100, "birth": "earlier", "child_pid": 101, "child_birth": "earlier-child"})
    assert stopped == []


def test_redirects_cannot_reach_another_endpoint():
    from mia.desktop_remote import _NoRedirect
    with pytest.raises(RemoteError) as error:
        _NoRedirect().redirect_request(None, None, 302, "redirect", {}, "http://other.example/")
    assert error.value.code == "redirect_refused"


# Import here keeps the main test assertions explicit about accepted error type.
from mia.operations import OperationError
