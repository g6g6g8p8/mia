from concurrent.futures import ThreadPoolExecutor
import asyncio
import hashlib
import os
from pathlib import Path
import secrets

from fastapi.testclient import TestClient
import pytest

from mia.demo_distribution import DistributionError, DOWNLOAD_TTL, InvitationStore, create_distribution_app


def fixture(tmp_path):
    artifact = tmp_path / "demo.dmg"
    artifact.write_bytes(bytes(range(256)) * 4)
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    app = create_distribution_app(tmp_path / "private", artifact, sha256=sha)
    return TestClient(app), app.state.invitation_store, artifact, sha


def test_concurrent_redemption_is_once_and_download_is_repeatable(tmp_path):
    client, store, artifact, sha = fixture(tmp_path)
    invitation = store.issue()
    def redeem():
        try:
            return store.redeem(invitation["token"], sha)
        except DistributionError:
            return None
    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(lambda _: redeem(), range(8)))
    sessions = [r for r in results if r]
    assert len(sessions) == 1
    headers = {"Authorization": "Bearer " + sessions[0]["download_token"]}
    assert client.get("/download", headers={**headers, "Range": "bytes=0-127"}).content == artifact.read_bytes()[:128]
    resumed = client.get("/download", headers={**headers, "Range": "bytes=128-"})
    assert resumed.status_code == 206
    assert resumed.content == artifact.read_bytes()[128:]
    assert resumed.headers["Content-Range"] == "bytes 128-1023/1024"
    assert client.get("/download", headers=headers).content == artifact.read_bytes()
    database = store.path.read_bytes()
    assert invitation["token"].encode() not in database
    assert sessions[0]["download_token"].encode() not in database
    assert "token_hash" not in store.list_invitations()[0]


def test_lost_redemption_response_retries_same_session_without_extending_expiry(tmp_path):
    client, store, _, sha = fixture(tmp_path)
    invitation = store.issue(now=100, ttl=60)
    request_id = secrets.token_urlsafe(32)
    lost_response = store.redeem(invitation["token"], sha, request_id=request_id, now=110)
    retry = store.redeem(invitation["token"], sha, request_id=request_id, now=200)
    assert retry == lost_response  # invitation expired; its download session remains valid
    with pytest.raises(DistributionError):
        store.redeem(invitation["token"], sha, request_id=secrets.token_urlsafe(32), now=200)
    with pytest.raises(DistributionError):
        store.redeem(invitation["token"], sha, request_id=request_id, now=110 + DOWNLOAD_TTL)
    assert request_id.encode() not in store.path.read_bytes()
    # A public HTTP retry receives the same receipt after a committed response
    # is lost, rather than consuming a second redemption.
    current = store.issue()
    body = {"token": current["token"], "request_id": secrets.token_urlsafe(32)}
    assert client.post("/redeem", json=body).json() == client.post("/redeem", json=body).json()


def test_expiry_and_revocation_do_not_affect_installed_core(tmp_path):
    _, store, _, sha = fixture(tmp_path)
    invitation = store.issue(now=100, ttl=60)
    with pytest.raises(DistributionError):
        store.redeem(invitation["token"], sha, now=160)
    invitation = store.issue(now=200, ttl=60)
    session = store.redeem(invitation["token"], sha, now=201)
    store.authorize(session["download_token"], sha, now=300)  # invitation already expired
    with pytest.raises(DistributionError):
        store.authorize(session["download_token"], sha, now=201 + DOWNLOAD_TTL)
    store.revoke(invitation["id"], now=301)
    with pytest.raises(DistributionError):
        store.authorize(session["download_token"], sha, now=302)
    # Service has no knowledge of personal installation roots or libraries.
    assert sorted(p.name for p in store.directory.iterdir()) == ["invitations.sqlite3"]


def test_public_service_never_creates_invites_or_echoes_secrets(tmp_path):
    client, store, _, _ = fixture(tmp_path)
    invitation = store.issue()
    assert client.post("/invitations", json={}).status_code == 404
    token = invitation["token"]
    response = client.post("/redeem", json={"token": token, "context": "private"})
    assert response.status_code == 400 and token not in response.text
    assert client.post("/redeem", content=b"x" * 4097).status_code == 413
    redeemed = client.post("/redeem", json={"token": token})
    assert redeemed.status_code == 200 and "no-store" == redeemed.headers["Cache-Control"]
    assert client.post("/redeem", json={"token": token}).status_code == 410
    assert client.get("/download?token=" + token).status_code == 400
    assert client.get("/download").status_code == 401
    page = client.get("/invite")
    assert page.status_code == 200 and "Baixar Mia" in page.text
    assert "location.hash.slice(1)" in page.text and "history.replaceState" in page.text
    assert "unsafe-inline" not in page.headers["Content-Security-Policy"]
    assert "nonce-" in page.headers["Content-Security-Policy"]


@pytest.mark.parametrize("value", ["bytes=-100", "bytes=1-0", "bytes=1024-", "bytes=0-1,3-4", "x"])
def test_bad_ranges_rejected_without_consuming_session(tmp_path, value):
    client, store, _, sha = fixture(tmp_path)
    session = store.redeem(store.issue()["token"], sha)
    headers = {"Authorization": "Bearer " + session["download_token"]}
    assert client.get("/download", headers={**headers, "Range": value}).status_code == 416
    assert client.get("/download", headers=headers).status_code == 200


def test_artifact_change_pauses_download_and_links_are_rejected(tmp_path):
    client, store, artifact, sha = fixture(tmp_path)
    session = store.redeem(store.issue()["token"], sha)
    artifact.write_bytes(b"changed")
    assert client.get("/download", headers={"Authorization": "Bearer " + session["download_token"]}).status_code == 503
    link = tmp_path / "link"
    link.symlink_to(store.directory, target_is_directory=True)
    with pytest.raises(DistributionError):
        InvitationStore(link)
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    public.chmod(0o755)
    with pytest.raises(DistributionError):
        InvitationStore(public)


def test_download_file_closes_when_client_disconnects_before_headers(tmp_path, monkeypatch):
    client, store, artifact, sha = fixture(tmp_path)
    session = store.redeem(store.issue()["token"], sha)
    endpoint = next(route.endpoint for route in client.app.routes if route.path == "/download")
    opened, closed = [], []
    original_open, original_close = os.open, os.close
    def capture_open(path, *args, **kwargs):
        fd = original_open(path, *args, **kwargs)
        if Path(path) == artifact:
            opened.append(fd)
        return fd
    def capture_close(fd):
        closed.append(fd)
        return original_close(fd)
    monkeypatch.setattr(os, "open", capture_open)
    monkeypatch.setattr(os, "close", capture_close)
    response = endpoint(authorization="Bearer " + session["download_token"], range=None)
    async def invoke():
        async def receive():
            return await asyncio.Future()
        async def send(_message):
            raise OSError("Disconnected before response headers")
        await response({"type": "http", "asgi": {"version": "3.0", "spec_version": "2.0"}}, receive, send)
    with pytest.raises(Exception):
        asyncio.run(invoke())
    assert len(opened) == 1 and closed.count(opened[0]) == 1
