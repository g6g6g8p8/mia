import base64
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import time
import zipfile

import pytest

from mia import updates
from mia.operations import _write
from mia.updates import UpdateController, UpdateError


@pytest.fixture
def channel(tmp_path, monkeypatch):
    resources = tmp_path / "Resources"
    resources.mkdir()
    key = tmp_path / "key.pem"
    subprocess.run(["/usr/bin/openssl", "genpkey", "-algorithm", "ED25519", "-out", str(key)], check=True, capture_output=True)
    public = subprocess.check_output(["/usr/bin/openssl", "pkey", "-in", str(key), "-pubout", "-outform", "DER"])[-32:]
    (resources / "release-channel.json").write_text(json.dumps({"protocol": 1, "channel": "beta",
        "backend_feed_url": "https://releases.example/feed.json", "backend_public_key": base64.b64encode(public).decode()}))
    controller = UpdateController(resources, tmp_path / "home")
    package = tmp_path / "artifact.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("update.json", json.dumps({"protocol": 1, "target": "backend", "version": "0.2.0a14", "manager_protocol": 2, "runtime_changed": False, "manager_changed": False}))
        archive.writestr("source/pyproject.toml", '[project]\nname="mia-personal-ai"\nversion="0.2.0a14"\n')
        archive.writestr("wheelhouse/", b"")
        archive.writestr("source/mia/__init__.py", '__version__="0.2.0a14"')
    release = {"id": "backend-a14", "version": "0.2.0a14", "target": "backend", "notes": "Synthetic release",
        "manager_protocol": 2, "url": "https://releases.example/artifact.zip", "size": package.stat().st_size,
        "sha256": hashlib.sha256(package.read_bytes()).hexdigest()}
    feed = {"protocol": 1, "channel": "beta", "expires_at": int(time.time()) + 600, "sequence": 1, "releases": [release]}
    def envelope(feed_data=None):
        payload = json.dumps(feed if feed_data is None else feed_data, sort_keys=True).encode()
        payload_path = tmp_path / "signed"
        payload_path.write_bytes(payload)
        signature = subprocess.check_output(["/usr/bin/openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(key), "-in", str(payload_path)])
        return json.dumps({"payload": base64.b64encode(payload).decode(), "signature": base64.b64encode(signature).decode()}).encode()
    contents = {"feed": envelope(), "package": package.read_bytes()}
    def download(url, target, limit, expected_size=None):
        data = contents["feed"] if url.endswith("feed.json") else contents["package"]
        target.write_bytes(data)
        target.chmod(0o600)
    monkeypatch.setattr(updates, "_fetch", download)
    return controller, contents, feed, envelope


def test_channel_missing_is_human_unconfigured_not_updated(tmp_path):
    resources = tmp_path / "Resources"
    resources.mkdir()
    result = UpdateController(resources, tmp_path / "home").handle("updates_check", {})
    assert result["state"] == "unconfigured"
    assert result["app_updated"] is False and result["runtime_updated"] is False
    assert not (tmp_path / "home/Library/Application Support/Mia/installation").exists()


def test_signed_backend_flow_reviews_exact_plan_and_distinguishes_client(channel, monkeypatch):
    controller, _, _, _ = channel
    assert controller.handle("updates_check", {})["state"] == "available"
    prepared = controller.handle("updates_prepare", {"release_id": "backend-a14"})
    assert prepared["state"] == "prepared"
    calls = []
    def manager(action, args):
        calls.append((action, args))
        controller.root.mkdir(parents=True, mode=0o700)
        _write(controller.root / "installation.json", {})
        _write(controller.root / "active.json", {"version": "0.2.0a14"})
        return {"version": "0.2.0a14", "recovery_required": False}
    monkeypatch.setattr(controller, "_manager", manager)
    with pytest.raises(UpdateError, match="aprovação"):
        controller.handle("updates_apply", {"approve_sha256": "wrong"})
    assert not calls
    result = controller.handle("updates_apply", {"approve_sha256": prepared["plan_sha256"]})
    assert calls[0][0] == "update" and calls[0][1][-1] == "--offline"
    assert result["state"] == "applied_backend" and result["backend_version"] == "0.2.0a14"
    assert result["app_updated"] is result["manager_updated"] is result["runtime_updated"] is False
    assert not (controller.state / "journal.json").exists()
    assert controller.handle("updates_check", {})["state"] == "idle"
    assert controller.handle("updates_status", {})["releases"] == []


def test_signature_tamper_and_unsigned_cached_changes_never_execute(channel):
    controller, contents, _, _ = channel
    original = contents["feed"]
    envelope = json.loads(original)
    envelope["payload"] = base64.b64encode(b'{"evil":true}').decode()
    contents["feed"] = json.dumps(envelope).encode()
    with pytest.raises(UpdateError, match="Assinatura"):
        controller.handle("updates_check", {})
    contents["feed"] = original
    controller.handle("updates_check", {})
    cache = json.loads((controller.state / "releases.json").read_text())
    cache["releases"][0]["url"] = "https://attacker.example/malware"
    _write(controller.state / "releases.json", cache)
    with pytest.raises(UpdateError, match="mudou"):
        controller.handle("updates_prepare", {"release_id": "backend-a14"})
    assert not (controller.state / "artifact.zip").exists()


@pytest.mark.parametrize("case", ["expired", "rollback", "app", "http", "credentials"])
def test_authenticated_but_unsafe_feeds_are_rejected(channel, case):
    controller, contents, feed, envelope = channel
    controller.handle("updates_check", {})
    if case == "expired":
        feed["expires_at"] = int(time.time()) - 1
    elif case == "rollback":
        feed["sequence"] = 0
    elif case == "app":
        feed["releases"][0]["target"] = "app"
    elif case == "http":
        feed["releases"][0]["url"] = "http://releases.example/package"
    else:
        feed["releases"][0]["url"] = "https://user:secret@releases.example/package"
    contents["feed"] = envelope(feed)
    with pytest.raises(UpdateError):
        controller.handle("updates_check", {})


def test_interrupted_or_wrong_hash_download_preserves_journal_and_can_discard(channel):
    controller, contents, _, _ = channel
    controller.handle("updates_check", {})
    contents["package"] = b"interrupted download"
    with pytest.raises(UpdateError, match="difere"):
        controller.handle("updates_prepare", {"release_id": "backend-a14"})
    assert controller.handle("updates_status", {})["state"] == "interrupted"
    assert not controller.root.exists()
    assert controller.handle("updates_prepare", {"discard": True})["state"] == "available"
    assert not (controller.state / "artifact.download").exists()


@pytest.mark.parametrize("name", ["../outside", "source/../../outside", "/absolute", "source\\bad", "source/./bad", "source//bad", "source/.env", "wheelhouse/malware.py"])
def test_archive_paths_are_rejected_before_any_extraction(tmp_path, name):
    artifact = tmp_path / "bad.zip"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("source/good.py", b"good")
        archive.writestr(name, b"bad")
    with pytest.raises(UpdateError):
        updates._extract(artifact, tmp_path / "output")
    assert not (tmp_path / "output").exists()
    assert not (tmp_path / "outside").exists()


def test_archive_links_duplicates_and_expansion_are_rejected(tmp_path, monkeypatch):
    for failure in ("link", "duplicate", "expansion"):
        artifact = tmp_path / (failure + ".zip")
        with zipfile.ZipFile(artifact, "w") as archive:
            info = zipfile.ZipInfo("source/a")
            if failure == "link":
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, b"contents")
            if failure == "duplicate":
                archive.writestr("source/A", b"duplicate on Mac")
        if failure == "expansion":
            monkeypatch.setattr(updates, "MAX_EXPANDED", 1)
        with pytest.raises(UpdateError):
            updates._extract(artifact, tmp_path / "output")
        assert not (tmp_path / "output").exists()


def test_apply_reextracts_authenticated_source_and_failed_activation_is_recoverable(channel, monkeypatch):
    controller, _, _, _ = channel
    controller.handle("updates_check", {})
    prepared = controller.handle("updates_prepare", {"release_id": "backend-a14"})
    source = controller.state / "package/source/mia/__init__.py"
    source.write_text("tampered after approval")
    def failed(action, args):
        assert "tampered" not in source.read_text()
        raise UpdateError("Synthetic startup failure")
    monkeypatch.setattr(controller, "_manager", failed)
    with pytest.raises(UpdateError):
        controller.handle("updates_apply", {"approve_sha256": prepared["plan_sha256"]})
    assert controller.handle("updates_status", {})["state"] == "recovery_required"
    monkeypatch.setattr(controller, "_manager", lambda action, args: {"version": "old", "recovery_required": False})
    assert controller.handle("updates_recover", {})["state"] == "recovered"
    assert not (controller.state / "journal.json").exists()


def test_redirects_and_privileged_payloads_are_rejected(tmp_path):
    with pytest.raises(UpdateError, match="Redirecionamento"):
        updates._NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://another.example")
    resources = tmp_path / "Resources"
    resources.mkdir()
    controller = UpdateController(resources, tmp_path / "home")
    with pytest.raises(UpdateError):
        controller.handle("updates_apply", {"source": "/tmp/arbitrary", "approve_sha256": "anything"})


def test_manager_rejects_unreviewed_bootstrap_or_external_runtime(channel):
    controller, _, _, _ = channel
    controller.root.mkdir(parents=True, mode=0o700)
    manager = controller.root / "manager.py"
    manager.write_text("raise RuntimeError('must never execute')")
    _write(controller.root / "installation.json", {"manager_protocol": 2, "manager_sha256": "invalid", "python": "/usr/bin/python3"})
    with pytest.raises(UpdateError, match="Gerenciador difere"):
        controller._manager("recover", [])
    _write(controller.root / "installation.json", {"manager_protocol": 2, "manager_sha256": hashlib.sha256(manager.read_bytes()).hexdigest(), "python": "/usr/bin/python3"})
    with pytest.raises(UpdateError, match="Runtime"):
        controller._manager("recover", [])


def test_changed_installation_requires_new_review_and_no_downgrade(channel, monkeypatch):
    controller, _, _, _ = channel
    controller.root.mkdir(parents=True, mode=0o700)
    _write(controller.root / "installation.json", {"manager_protocol": 2})
    _write(controller.root / "active.json", {"version": "0.2.0a13"})
    controller.handle("updates_check", {})
    prepared = controller.handle("updates_prepare", {"release_id": "backend-a14"})
    _write(controller.root / "active.json", {"version": "0.2.0a14"})
    with pytest.raises(UpdateError, match="mudou após"):
        controller.handle("updates_apply", {"approve_sha256": prepared["plan_sha256"]})
    controller.handle("updates_prepare", {"discard": True})
    with pytest.raises(UpdateError, match="posterior"):
        controller.handle("updates_prepare", {"release_id": "backend-a14"})


def test_recovery_does_not_start_backend_when_only_prepared(channel, monkeypatch):
    controller, _, _, _ = channel
    monkeypatch.setattr(controller, "_manager", lambda *_: pytest.fail("No pending operation may invoke manager"))
    assert controller.handle("updates_recover", {})["state"] == "idle"
    controller.handle("updates_check", {})
    controller.handle("updates_prepare", {"release_id": "backend-a14"})
    with pytest.raises(UpdateError, match="não alterou"):
        controller.handle("updates_recover", {})


def test_transport_stream_bounds_actual_bytes_and_rejects_encoded_response(tmp_path, monkeypatch):
    class Response:
        status = 200
        headers = {"Content-Length": "4"}
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def read(self, size):
            return b"x" * size
    response = Response()
    class Opener:
        def open(self, *_args, **_kwargs):
            return response
    monkeypatch.setattr(updates.urllib.request, "build_opener", lambda *_: Opener())
    with pytest.raises(UpdateError, match="excedeu o limite"):
        updates._fetch("https://releases.example/package", tmp_path / "overflow", 4)
    response.headers = {"Content-Encoding": "gzip"}
    with pytest.raises(UpdateError, match="incompatível"):
        updates._fetch("https://releases.example/package", tmp_path / "encoded", 4)


def test_channel_public_config_rejects_private_fields_and_unpaired_trust():
    with pytest.raises(UpdateError, match="não permitidos"):
        updates.validate_channel({"protocol": 1, "channel": "beta", "api_key": "private"})
    with pytest.raises(UpdateError, match="juntos"):
        updates.validate_channel({"protocol": 1, "channel": "beta", "appcast_url": "https://releases.example/appcast.xml"})


def test_changed_official_channel_cannot_use_previous_signed_cache(channel):
    controller, _, _, _ = channel
    controller.handle("updates_check", {})
    config = json.loads((controller.resources / "release-channel.json").read_text())
    config["channel"] = "stable"
    (controller.resources / "release-channel.json").write_text(json.dumps(config))
    with pytest.raises(UpdateError, match="canal oficial mudou"):
        controller.handle("updates_prepare", {"release_id": "backend-a14"})
    assert not (controller.state / "artifact.zip").exists()
