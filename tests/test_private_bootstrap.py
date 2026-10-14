"""Other local OS users cannot claim a fresh native installation over TCP."""
import json
import secrets

import pytest

from mia import operations
from test_app import client, setup_payload


def protected(client, monkeypatch):
    browser, directory = client
    root = directory / "managed"
    root.mkdir(mode=0o700)
    token = secrets.token_urlsafe(32)
    path = root / "bootstrap-token"
    path.write_text(token + "\n")
    path.chmod(0o600)
    monkeypatch.setenv("MIA_SETUP_REQUIRE_TOKEN", "true")
    monkeypatch.setenv("MIA_OPERATIONS_ROOT", str(root))
    return browser, root, token


def test_native_first_owner_requires_private_cookie_and_does_not_publish_token(client, monkeypatch):
    browser, root, token = protected(client, monkeypatch)
    info = browser.get("/api/installation")
    assert info.json()["bootstrap_protected"] is True
    assert token not in info.text
    for value in (None, secrets.token_urlsafe(32), "invalid"):
        if value:
            browser.cookies.set("mia_bootstrap", value)
        response = browser.post("/api/setup", json=setup_payload())
        assert response.status_code == 401
        assert token not in response.text
        assert browser.get("/api/status").json()["configured"] is False
    browser.cookies.set("mia_bootstrap", token)
    rejected_origin = browser.post("/api/setup", json=setup_payload(), headers={"Origin": "https://untrusted.example.test"})
    assert rejected_origin.status_code == 403
    assert browser.get("/api/status").json()["configured"] is False
    success = browser.post("/api/setup", json=setup_payload())
    assert success.status_code == 201 and 'mia_bootstrap=""' in success.headers.get("set-cookie", "")
    assert browser.get("/api/status").json()["configured"] is True
    browser.cookies.clear()
    assert browser.post("/api/setup", json=setup_payload()).status_code == 409
    assert browser.post("/api/login", json={"password": setup_payload()["password"]}).status_code == 200


@pytest.mark.parametrize("failure", ["missing", "permissions", "symlink", "oversized"])
def test_damaged_bootstrap_requires_recovery_without_creating_owner(client, monkeypatch, failure):
    browser, root, token = protected(client, monkeypatch)
    path = root / "bootstrap-token"
    if failure == "missing":
        path.unlink()
    elif failure == "permissions":
        path.chmod(0o644)
    elif failure == "symlink":
        path.rename(root / "original")
        path.symlink_to(root / "original")
    else:
        path.write_bytes(b"synthetic" * 100)
    browser.cookies.set("mia_bootstrap", token)
    response = browser.post("/api/setup", json=setup_payload())
    assert response.status_code == 503 and token not in response.text
    assert browser.get("/api/status").json()["configured"] is False


def test_native_manager_creates_private_capability_without_command_line_secret(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(operations.Manager, "_release", lambda self, *_args: {"release": "releases/synthetic", "version": "synthetic"})
    manager = operations.Manager(tmp_path / "native")
    manager.install(source, private_bootstrap=True)
    token_file = manager.root / "bootstrap-token"
    assert 32 <= len(token_file.read_text().strip()) <= 128
    assert token_file.stat().st_mode & 0o077 == 0
    assert json.loads((manager.root / "installation.json").read_text())["private_bootstrap"] is True
    assert "MIA_SETUP_REQUIRE_TOKEN=true\n" in (manager.root / "machine.env").read_text()
    assert token_file.read_text().strip() not in (manager.root / "installation.json").read_text()
