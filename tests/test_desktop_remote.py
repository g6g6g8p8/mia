"""Native remote boundary tests with an adapter; never contact personal hosts."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import tarfile
from types import SimpleNamespace
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from mia.desktop_remote import RemoteController, RemoteError, SystemSSH, _fingerprint, _write, artifact


KEY = base64.b64encode(b"fixture-server-ed25519-public-key-not-a-secret").decode()
FINGERPRINT = _fingerprint(KEY)
IDENTITY = "5cdd414b-7271-4503-b817-f764cbd0b900"
HOST = {"host": "my-server.example", "user": "tester"}
BOOTSTRAP_TOKEN = "synthetic-private-bootstrap-authority-00000"
assert len(BOOTSTRAP_TOKEN) == 43


def backend(identity=IDENTITY, secure=False, configured=False, protected=True):
    return {"health": {"ok": True, "version": "0.2.0a13"}, "status": {"configured": configured, "version": "0.2.0a13"}, "installation": {"installation_id": identity, "version": "0.2.0a13", "desktop_protocol": 1, "cookie_secure": secure, "transport_policy": "https_required" if secure else "private_connection_only", "bootstrap_protected": protected}}


class FixtureSSH:
    def __init__(self):
        self.key = KEY
        self.known_host = False
        self.changed = False
        self.calls = []
        self.liveness = {}
        self.server = backend()
        self.http_server = backend(configured=True)
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
        value = dict(self.probe_result)
        if value.get("backend") and value["backend"]["status"]["configured"] is False and value["backend"]["installation"]["bootstrap_protected"] is True:
            value.setdefault("bootstrap_token", BOOTSTRAP_TOKEN)
        return value

    def install(self, config, pin, manifest, directory, identity):
        self.calls.append("install")
        self.server["installation"]["installation_id"] = identity
        self.probe_result.update(port_available=False, backend=self.server)
        self.http_server = self.server
        return {"ok": True, "version": manifest["version"], "root_id": identity, "installation_id": identity, "service_activated": True}

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


@contextmanager
def public_backend(server_backend):
    """Actual loopback transport with public metadata and no bootstrap nonce."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            key = {"/health": "health", "/api/status": "status", "/api/installation": "installation"}.get(self.path)
            self.send_response(200 if key else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(server_backend.get(key, {})).encode())
        def log_message(self, *_args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def managed_bootstrap(home, identity, port):
    root = home / ".local/share/mia-demo/installations" / identity
    root.mkdir(mode=0o700, parents=True)
    (home / ".local/share/mia-demo").chmod(0o700)
    _write(root / "installation.json", {"installation_id": identity, "private_bootstrap": True, "host": "127.0.0.1", "port": port})
    token = root / "bootstrap-token"
    token.write_text(BOOTSTRAP_TOKEN + "\n")
    token.chmod(0o600)
    return root


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
    assert result["installation_id"] == json.loads(next(controller.base.glob("*.plan.json")).read_text())["identity"] and result["configured"] is False
    assert result["bootstrap_token"] == BOOTSTRAP_TOKEN
    assert BOOTSTRAP_TOKEN not in json.dumps(controller.connections())
    assert BOOTSTRAP_TOKEN not in (controller.base / result["connection_id"] / "connection.json").read_text()
    assert controller.adapter.calls.count("install") == 1
    assert controller.adapter.calls.count("spawn") == 1
    # One short-lived bridge can be replaced without creating a new backend,
    # session identity or tunnel when the verified process is alive.
    replacement = RemoteController(controller.resources, controller.home, adapter=controller.adapter)
    connected = replacement.handle("remote_connect", approved())
    assert connected["connection_id"] == result["connection_id"] and connected["url"] == result["url"]
    assert connected["bootstrap_token"] == BOOTSTRAP_TOKEN
    assert controller.adapter.calls.count("spawn") == 1


def test_compiled_remote_installer_enables_private_owner_creation_before_activation(tmp_path, monkeypatch, capsys):
    """Execute the embedded SSH program, intercepting OS activation only.

    Manager.install runs its actual private-root/config/token creation. A fake
    release replaces package installation; this does not attest macOS/Linux
    runtime artifacts or a real systemd boot.
    """
    from mia import desktop_remote
    from mia.operations import Manager
    import platform
    import shutil

    home = tmp_path / "server-home"
    home.mkdir(mode=0o700)
    resources = tmp_path / "resources"
    resources.mkdir()
    artifact_root, payload = add_artifact(resources)
    manifest = json.loads((artifact_root / "manifest.json").read_text())
    identity = str(uuid.uuid4())
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    incoming = io.BytesIO()
    incoming.write(json.dumps({"manifest": manifest, "identity": identity, "remote_port": port}).encode() + b"\n")
    with tarfile.open(fileobj=incoming, mode="w") as archive:
        for name in sorted(manifest["files"]):
            archive.add(payload / name, arcname=name, recursive=False)
    incoming.seek(0)
    read_text, is_file = Path.read_text, Path.is_file
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(Path, "read_text", lambda path, *args, **kwargs: 'ID="ubuntu"\nVERSION_ID="24.04"\n' if str(path) == "/etc/os-release" else read_text(path, *args, **kwargs))
    monkeypatch.setattr(Path, "is_file", lambda path: True if str(path).startswith("/var/lib/systemd/linger/") else is_file(path))
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(shutil, "disk_usage", lambda path: SimpleNamespace(free=10 * 1024**3))
    calls = []
    def release(manager, source, wheelhouse=None, offline=False):
        assert offline and wheelhouse is not None
        (manager.root / "releases/synthetic").mkdir(mode=0o700)
        return {"release": "releases/synthetic", "version": manifest["version"]}
    monkeypatch.setattr(Manager, "_release", release)
    def run(command, **kwargs):
        if command[:2] == ["/usr/bin/systemctl", "--user"]:
            return subprocess.CompletedProcess(command, 0)
        if "install" in command:
            assert "--private-bootstrap" in command
            root = Path(command[command.index("--root") + 1])
            calls.append("install")
            Manager(root).install(Path(command[command.index("--source") + 1]), port=port,
                                  env_file=Path(command[command.index("--env-file") + 1]),
                                  wheelhouse=Path(command[command.index("--wheelhouse") + 1]), offline=True,
                                  installation_id=command[command.index("--installation-id") + 1], private_bootstrap=True)
        else:
            assert "apply_service_plan" in command[3]
            root = Path(command[-1])
            assert json.loads((root / "installation.json").read_text())["private_bootstrap"] is True
            assert (root / "machine.env").read_text().endswith("MIA_SETUP_REQUIRE_TOKEN=true\n")
            assert len((root / "bootstrap-token").read_bytes()) == 44
            assert (root / "bootstrap-token").stat().st_mode & 0o777 == 0o600
            calls.append("activate")
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=incoming))
    exec(compile(desktop_remote._INSTALL, "<private-remote-installer>", "exec"), {})
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["ok"] is True and result["service_activated"] is True
    assert result["installation_id"] == identity and calls == ["install", "activate"]
    root = home / ".local/share/mia-demo/installations" / identity
    token = (root / "bootstrap-token").read_text().strip()
    assert "bootstrap_token" not in result and token not in output
    with public_backend(backend(identity=identity)) as server_port:
        configuration = json.loads((root / "installation.json").read_text())
        configuration["port"] = server_port
        _write(root / "installation.json", configuration)
        monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps({"remote_port": server_port}).encode() + b"\n")))
        exec(compile(desktop_remote._PROBE, "<private-remote-probe>", "exec"), {})
        private_result = json.loads(capsys.readouterr().out)
        assert private_result["bootstrap_token"] == token
        assert token not in json.dumps(private_result["backend"])


@pytest.mark.parametrize("mutation", [None, "missing", "malformed", "extra_newline", "shared", "symlink", "wrong_id", "unprotected", "wrong_port", "public_bind", "configured"])
def test_private_ssh_probe_attests_exact_empty_installation_token(tmp_path, mutation):
    from mia.desktop_remote import _PROBE
    server_backend = backend()
    with public_backend(server_backend) as port:
        root = managed_bootstrap(tmp_path, IDENTITY, port)
        token = root / "bootstrap-token"
        if mutation == "missing":
            token.unlink()
        elif mutation == "malformed":
            token.write_bytes(b"invalid authorization\n")
        elif mutation == "extra_newline":
            token.write_text(BOOTSTRAP_TOKEN + "\n\n")
        elif mutation == "shared":
            token.chmod(0o644)
        elif mutation == "symlink":
            outside = tmp_path / "retain-private-token"
            token.rename(outside)
            token.symlink_to(outside)
        elif mutation == "configured":
            server_backend["status"]["configured"] = True
        elif mutation:
            configuration = json.loads((root / "installation.json").read_text())
            field, value = {"wrong_id": ("installation_id", str(uuid.uuid4())), "unprotected": ("private_bootstrap", False), "wrong_port": ("port", port + 1), "public_bind": ("host", "0.0.0.0")}[mutation]
            configuration[field] = value
            _write(root / "installation.json", configuration)
        process = subprocess.run([sys.executable, "-I", "-c", _PROBE], input=json.dumps({"remote_port": port}), text=True, capture_output=True, timeout=15, env={**os.environ, "HOME": str(tmp_path)})
        assert process.returncode == 0, process.stderr
        private_result = json.loads(process.stdout)
        assert private_result["bootstrap_token"] == (BOOTSTRAP_TOKEN if mutation is None else None)
        assert BOOTSTRAP_TOKEN not in json.dumps(private_result["backend"])


@pytest.mark.parametrize("token", [None, "", "short", "A" * 42, "A" * 44, "A" * 42 + "!", "A" * 42 + "\n"])
def test_empty_remote_connect_without_valid_private_handoff_does_not_open_page(controller, token):
    controller.adapter.probe_result.update(port_available=False, backend=backend(), bootstrap_token=token)
    with pytest.raises(RemoteError) as error:
        controller.handle("remote_connect", approved())
    assert error.value.code == "bootstrap_unavailable"
    assert "spawn" not in controller.adapter.calls
    assert controller.connections() == []


def test_legacy_empty_remote_is_not_claimed_and_https_never_authorizes_first_owner(controller):
    controller.adapter.probe_result.update(port_available=False, backend=backend(protected=False))
    with pytest.raises(RemoteError) as error:
        controller.handle("remote_connect", approved())
    assert error.value.code == "bootstrap_unprotected"
    controller.adapter.http_server = backend()
    with pytest.raises(RemoteError) as error:
        controller.handle("https_connect", {"url": "https://mia.example/"})
    assert error.value.code == "bootstrap_requires_private_connection"
    assert controller.connections() == [] and "spawn" not in controller.adapter.calls


def test_reconnect_delivers_ephemeral_authority_only_until_first_owner_exists(controller):
    empty = backend()
    controller.adapter.probe_result.update(port_available=False, backend=empty)
    controller.adapter.http_server = empty
    first = controller.handle("remote_connect", approved())
    assert first["bootstrap_token"] == BOOTSTRAP_TOKEN
    state_path = controller.base / first["connection_id"] / "connection.json"
    assert BOOTSTRAP_TOKEN not in state_path.read_text()
    assert BOOTSTRAP_TOKEN not in json.dumps(controller.connections())
    again = controller.handle("remote_connect", {"connection_id": first["connection_id"]})
    assert again["bootstrap_token"] == BOOTSTRAP_TOKEN and controller.adapter.calls.count("spawn") == 1
    # A private connection record from an older client may have cached the
    # nonce. Reconnecting to an initialized owner removes that obsolete cache.
    stored = json.loads(state_path.read_text())
    stored["bootstrap_token"] = BOOTSTRAP_TOKEN
    _write(state_path, stored)
    empty["status"]["configured"] = True
    configured = controller.handle("remote_connect", {"connection_id": first["connection_id"]})
    assert "bootstrap_token" not in configured and BOOTSTRAP_TOKEN not in json.dumps(configured)
    assert BOOTSTRAP_TOKEN not in state_path.read_text()


@pytest.mark.parametrize("change", ["https_policy", "bootstrap_disabled"])
def test_existing_tunnel_policy_change_is_rejected_before_private_handoff(controller, change):
    controller.adapter.probe_result.update(port_available=False, backend=backend())
    controller.adapter.http_server = backend()
    first = controller.handle("remote_connect", approved())
    controller.adapter.http_server = backend(secure=change == "https_policy", protected=change != "bootstrap_disabled")
    with pytest.raises(RemoteError) as error:
        controller.handle("remote_connect", {"connection_id": first["connection_id"]})
    assert error.value.code == "installation_changed" and BOOTSTRAP_TOKEN not in str(error.value)
    assert controller.adapter.liveness == {}


@pytest.mark.parametrize("section,field,value", [("installation", "desktop_protocol", True), ("installation", "desktop_protocol", 1.0), ("installation", "cookie_secure", 1), ("installation", "bootstrap_protected", 1), ("status", "configured", 0)])
def test_protocol_fields_reject_bool_or_numeric_coercion_before_token_handoff(controller, section, field, value):
    invalid = backend()
    invalid[section][field] = value
    controller.adapter.probe_result.update(port_available=False, backend=invalid)
    with pytest.raises(RemoteError) as error:
        controller.handle("remote_connect", approved())
    assert error.value.code == "protocol_unsupported"
    assert BOOTSTRAP_TOKEN not in str(error.value) and "spawn" not in controller.adapter.calls


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
    controller.adapter.http_server = backend(identity=str(uuid.uuid4()), configured=True)
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


def test_remote_install_cannot_substitute_another_identity_for_approved_empty_root(controller, monkeypatch):
    add_artifact(controller.resources)
    plan = controller.handle("remote_preflight", approved())
    install = controller.adapter.install
    def changed(*args):
        result = install(*args)
        result["installation_id"] = str(uuid.uuid4())
        return result
    monkeypatch.setattr(controller.adapter, "install", changed)
    with pytest.raises(RemoteError) as error:
        controller.handle("remote_install", approved(approve_sha256=plan["plan_sha256"]))
    assert error.value.code == "recovery_required" and "spawn" not in controller.adapter.calls
    assert next(controller.base.glob("*.plan.json")).exists()


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
        assert state["bootstrap_token"] is None
        assert set(state) == {"platform", "platform_version", "architecture", "home_safe", "free_bytes", "user_service", "linger", "port_available", "backend", "bootstrap_token"}
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
