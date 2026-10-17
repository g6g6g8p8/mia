"""Serverless durability/authorization tests, including real Redis Lua execution.

Set MIA_TEST_REDIS_SERVER to a Redis executable for the isolated Unix-socket
integration tests. No external database/provider or production credential is
needed; the scripts executed here are the actual Upstash EVAL payloads.
"""
from __future__ import annotations

import base64
import concurrent.futures
from email.message import Message
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import time
import urllib.parse

import pytest

import mia.vercel_distribution as distribution
from mia.demo_distribution import DistributionError, DOWNLOAD_TTL

TOKEN = "provider-secret-for-test-only-123456789"
SHA = "f" * 64
PATHNAME = "releases/0.2.0a13/arm64/Mia-Demo.dmg"


class RedisServer:
    def __init__(self, executable, root):
        self.executable, self.root = executable, root
        self.socket = root / "redis.sock"
        self.start()

    def start(self):
        self.process = subprocess.Popen([self.executable, "--port", "0", "--unixsocket", str(self.socket),
            "--unixsocketperm", "700", "--dir", str(self.root), "--save", "", "--appendonly", "yes", "--appendfsync", "always"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                if self.command(["PING"]) == b"PONG":
                    return
            except (OSError, ValueError):
                time.sleep(0.01)
        self.close()
        raise RuntimeError("Isolated Redis did not start")

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)

    def restart(self):
        self.close()
        self.start()

    def command(self, arguments):
        encoded = [str(value).encode() for value in arguments]
        wire = b"*" + str(len(encoded)).encode() + b"\r\n" + b"".join(
            b"$" + str(len(value)).encode() + b"\r\n" + value + b"\r\n" for value in encoded)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(5)
            client.connect(str(self.socket))
            client.sendall(wire)
            with client.makefile("rb") as response:
                def read():
                    prefix, line = response.read(1), response.readline().rstrip(b"\r\n")
                    if prefix == b"+": return line
                    if prefix == b"-": raise ValueError(line.decode())
                    if prefix == b":": return int(line)
                    if prefix == b"$":
                        size = int(line)
                        if size == -1: return None
                        value = response.read(size)
                        assert response.read(2) == b"\r\n"
                        return value
                    if prefix == b"*": return [read() for _ in range(int(line))]
                    raise ValueError("Invalid Redis response")
                return read()


@pytest.fixture(scope="module")
def redis_server(tmp_path_factory):
    executable = os.environ.get("MIA_TEST_REDIS_SERVER") or shutil.which("redis-server")
    if not executable:
        pytest.skip("A Redis executable is required for the real Lua integration checks")
    server = RedisServer(executable, tmp_path_factory.mktemp("vercel-redis"))
    try:
        yield server
    finally:
        server.close()


@pytest.fixture
def store(monkeypatch, redis_server):
    redis_server.command(["FLUSHDB"])
    def post(url, token, payload, **kwargs):
        assert url == "https://mia-test.upstash.io" and token == TOKEN
        assert payload[0] == "EVAL" and len(payload) >= 7
        return {"result": redis_server.command(payload).decode()}
    monkeypatch.setattr(distribution, "_post_json", post)
    return distribution.UpstashInvitationStore("https://mia-test.upstash.io", TOKEN)


def test_real_lua_lost_response_replay_preserves_session_expiry(store, redis_server):
    invite = store.issue(now=1000)
    request_id = secrets.token_urlsafe(32)
    original = store.redeem(invite["token"], SHA, request_id=request_id, now=1001)
    # A new function instance knows no process-local session or token state.
    fresh = distribution.UpstashInvitationStore("https://mia-test.upstash.io", TOKEN)
    repeat = fresh.redeem(invite["token"], SHA, request_id=request_id, now=1100)
    assert repeat == original
    assert fresh.authorize(original["download_token"], SHA, now=1200) == {
        "expires_at": 1001 + DOWNLOAD_TTL, "invitation_id": invite["id"]}
    for attempt in (None, secrets.token_urlsafe(32)):
        with pytest.raises(DistributionError):
            fresh.redeem(invite["token"], SHA, request_id=attempt, now=1200)
    assert fresh.list_invitations() == [{"id": invite["id"], "created_at": 1000,
        "expires_at": 1000 + 7 * 86400, "redeemed_at": 1001, "revoked_at": None}]
    persisted = b"".join(value for key in store.keys[:3] for value in redis_server.command(["HGETALL", key]))
    for secret in (invite["token"], request_id, original["download_token"], TOKEN):
        assert secret.encode() not in persisted


def test_real_lua_concurrent_redeemers_exactly_one_request_wins(store, redis_server):
    invite = store.issue(now=1000)
    requests = [secrets.token_urlsafe(32), secrets.token_urlsafe(32)]
    def redeem(index):
        try:
            return index, store.redeem(invite["token"], SHA, request_id=requests[index], now=1001)
        except DistributionError:
            return index, None
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(redeem, [0, 1] * 20))
    successful = [(index, result) for index, result in results if result]
    assert len(successful) == 20 and len({index for index, result in successful}) == 1
    assert len({result["download_token"] for index, result in successful}) == 1
    assert redis_server.command(["HLEN", store.keys[2]]) == 1


def test_real_lua_revocation_and_exact_artifact_identity(store):
    invite = store.issue(now=1000)
    request = secrets.token_urlsafe(32)
    session = store.redeem(invite["token"], SHA, request_id=request, now=1001)
    with pytest.raises(DistributionError): store.authorize(session["download_token"], "a" * 64, now=1002)
    with pytest.raises(DistributionError): store.redeem(invite["token"], "a" * 64, request_id=request, now=1002)
    store.revoke(invite["id"], now=1003)
    with pytest.raises(DistributionError): store.authorize(session["download_token"], SHA, now=1004)
    with pytest.raises(DistributionError): store.redeem(invite["token"], SHA, request_id=request, now=1004)
    assert store.list_invitations()[0]["revoked_at"] == 1003


def test_real_lua_boundaries_no_session_extension_and_empty_list(store):
    assert store.list_invitations() == []
    expired = store.issue(ttl=60, now=1000)
    with pytest.raises(DistributionError):
        store.redeem(expired["token"], SHA, request_id=secrets.token_urlsafe(32), now=1060)
    invite = store.issue(now=1000)
    request = secrets.token_urlsafe(32)
    session = store.redeem(invite["token"], SHA, request_id=request, now=1001)
    with pytest.raises(DistributionError): store.authorize(session["download_token"], SHA, now=session["expires_at"])
    with pytest.raises(DistributionError): store.redeem(invite["token"], SHA, request_id=request, now=session["expires_at"])


def test_real_lua_durable_restart_and_capacity(store, redis_server, monkeypatch):
    invite = store.issue(now=1000)
    session = store.redeem(invite["token"], SHA, request_id=secrets.token_urlsafe(32), now=1001)
    redis_server.restart()
    fresh = distribution.UpstashInvitationStore("https://mia-test.upstash.io", TOKEN)
    assert fresh.authorize(session["download_token"], SHA, now=1200)["invitation_id"] == invite["id"]
    monkeypatch.setattr(distribution, "MAX_RECORDS", 1)
    with pytest.raises(DistributionError, match="retenção"): fresh.issue(now=1200)
    assert len(fresh.list_invitations()) == 1


def test_real_lua_beta_activation_replay_no_extension_after_ticket_expiry(store):
    invite = store.issue(now=1000)
    request = secrets.token_urlsafe(32)
    receipt = store.redeem(invite["token"], SHA, request_id=request, architecture="x86_64", now=1001)
    client = secrets.token_urlsafe(32)
    original = store.activate(receipt["activation_ticket"], client, "x86_64", now=1002)
    assert original["expires_at"] == 1002 + distribution.BETA_ACCESS_TTL
    assert len(original["access_token"]) == 43 and original["access_token"] != receipt["activation_ticket"]
    fresh = distribution.UpstashInvitationStore("https://mia-test.upstash.io", TOKEN)
    assert fresh.activate(receipt["activation_ticket"], client, "x86_64", now=receipt["expires_at"] + 1) == original
    assert fresh.authorize_beta(original["access_token"], "x86_64", now=receipt["expires_at"] + 1) == {
        "expires_at": original["expires_at"], "invitation_id": invite["id"]}
    with pytest.raises(DistributionError):
        fresh.redeem(invite["token"], SHA, request_id=request, architecture="arm64", now=1003)
    with pytest.raises(DistributionError): fresh.activate(receipt["activation_ticket"], client, "arm64", now=1003)
    with pytest.raises(DistributionError): fresh.authorize_beta(original["access_token"], "arm64", now=1003)
    with pytest.raises(DistributionError):
        fresh.activate(receipt["activation_ticket"], secrets.token_urlsafe(32), "x86_64", now=1003)
    with pytest.raises(DistributionError): fresh.authorize_beta(original["access_token"], "x86_64", now=original["expires_at"])
    with pytest.raises(DistributionError): fresh.activate(receipt["activation_ticket"], client, "x86_64", now=original["expires_at"])


def test_real_lua_concurrent_activations_only_one_client_wins(store, redis_server):
    invite = store.issue(now=1000)
    receipt = store.redeem(invite["token"], SHA, request_id=secrets.token_urlsafe(32), now=1001)
    clients = [secrets.token_urlsafe(32), secrets.token_urlsafe(32)]
    def activate(index):
        try:
            return index, store.activate(receipt["activation_ticket"], clients[index], "arm64", now=1002)
        except DistributionError:
            return index, None
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(activate, [0, 1] * 20))
    successful = [(index, result) for index, result in results if result]
    assert len(successful) == 20 and len({index for index, result in successful}) == 1
    assert len({result["access_token"] for index, result in successful}) == 1
    assert redis_server.command(["HLEN", store.keys[5]]) == 1


def test_real_lua_expired_unactivated_ticket_never_creates_access(store, redis_server):
    invite = store.issue(now=1000)
    receipt = store.redeem(invite["token"], SHA, request_id=secrets.token_urlsafe(32), now=1001)
    with pytest.raises(DistributionError):
        store.activate(receipt["activation_ticket"], secrets.token_urlsafe(32), "arm64", now=receipt["expires_at"])
    assert redis_server.command(["HLEN", store.keys[5]]) == 0


def test_real_lua_revocation_blocks_beta_activation_retry_and_updates(store):
    unactivated = store.issue(now=1000)
    unused = store.redeem(unactivated["token"], SHA, request_id=secrets.token_urlsafe(32), now=1001)
    store.revoke(unactivated["id"], now=1002)
    with pytest.raises(DistributionError):
        store.activate(unused["activation_ticket"], secrets.token_urlsafe(32), "arm64", now=1003)
    invite = store.issue(now=1000)
    receipt = store.redeem(invite["token"], SHA, request_id=secrets.token_urlsafe(32), now=1001)
    client = secrets.token_urlsafe(32)
    active = store.activate(receipt["activation_ticket"], client, "arm64", now=1002)
    store.revoke(invite["id"], now=1003)
    with pytest.raises(DistributionError): store.authorize_beta(active["access_token"], "arm64", now=1004)
    with pytest.raises(DistributionError): store.activate(receipt["activation_ticket"], client, "arm64", now=1004)


def test_real_lua_beta_restart_persistence_and_all_private_values_hash_only(store, redis_server):
    invite = store.issue(now=1000)
    request, client = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    receipt = store.redeem(invite["token"], SHA, request_id=request, now=1001)
    active = store.activate(receipt["activation_ticket"], client, "arm64", now=1002)
    redis_server.restart()
    fresh = distribution.UpstashInvitationStore("https://mia-test.upstash.io", TOKEN)
    assert fresh.activate(receipt["activation_ticket"], client, "arm64", now=1003) == active
    assert fresh.authorize_beta(active["access_token"], "arm64", now=1003)["invitation_id"] == invite["id"]
    persisted = b"".join(value for index in (0, 1, 2, 4, 5) for value in redis_server.command(["HGETALL", store.keys[index]]))
    for secret in (invite["token"], receipt["download_token"], receipt["activation_ticket"], active["access_token"], request, client, TOKEN):
        assert secret.encode() not in persisted


@pytest.mark.parametrize("architecture", ["intel", "aarch64", "universal", "", None, ["arm64"]])
def test_beta_rejects_invalid_architecture_before_provider(monkeypatch, architecture):
    monkeypatch.setattr(distribution, "_post_json", lambda *args, **kwargs: pytest.fail("Invalid architecture reached provider"))
    store = distribution.UpstashInvitationStore("https://mia-test.upstash.io", TOKEN)
    with pytest.raises(DistributionError): store.redeem("mia_invite_" + "A" * 43, SHA, request_id="B" * 43, architecture=architecture, now=1000)
    with pytest.raises(DistributionError): store.activate("A" * 43, "B" * 43, architecture, now=1000)
    with pytest.raises(DistributionError): store.authorize_beta("A" * 43, architecture, now=1000)


@pytest.mark.parametrize("url", ["http://mia.upstash.io", "https://mia.upstash.io:443", "https://mia.upstash.io:notaport",
    "https://user:secret@mia.upstash.io", "https://mia.upstash.io?token=secret", "https://mia.upstash.io/path",
    "https://mia.upstash.io.evil.test", "https://localhost", "https://127.0.0.1"])
def test_upstash_rejects_untrusted_credential_destinations(url):
    with pytest.raises(DistributionError): distribution.UpstashInvitationStore(url, TOKEN)


def test_store_rejects_malformed_provider_results_without_leaking(monkeypatch):
    store = distribution.UpstashInvitationStore("https://mia.upstash.io", TOKEN)
    for result in ({"error": TOKEN}, {"result": TOKEN}, {"result": json.dumps({"ok": "yes"})},
                   {"result": json.dumps({"ok": True, "expires_at": 10**20})}):
        monkeypatch.setattr(distribution, "_post_json", lambda *args, **kwargs: result)
        with pytest.raises(distribution.VercelDistributionUnavailable) as failed:
            store.redeem("mia_invite_" + "A" * 43, SHA, request_id="B" * 43, now=1000)
        assert TOKEN not in str(failed.value)


def blob_reply(**changes):
    payload = {"storeId": "store_teststore123", "ownerId": "owner_test", "pathname": PATHNAME,
        "operations": ["get"], "validUntil": 1060000, "iat": 1000000}
    payload.update(changes)
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=").decode()
    return {"delegationToken": encoded + "." + "B" * 43, "clientSigningToken": "A" * 43,
        "validUntil": payload["validUntil"]}


def test_blob_private_lease_matches_official_node_hmac_vector(monkeypatch):
    captured = []
    def post(*args, **kwargs):
        captured.append((args, kwargs))
        return blob_reply()
    monkeypatch.setattr(distribution, "_post_json", post)
    blobs = distribution.BlobPrivateDownloads(TOKEN, "store_teststore123")
    lease = blobs.download_url(PATHNAME, session_expires_at=1000 + DOWNLOAD_TTL, now=1000)
    parsed = urllib.parse.urlsplit(lease["url"])
    query = urllib.parse.parse_qs(parsed.query)
    assert parsed.scheme == "https" and parsed.netloc == "teststore123.private.blob.vercel-storage.com"
    assert parsed.path == "/" + PATHNAME and lease["expires_at"] == 1060
    # Independent fixed vector from Node createHmac, matching official SDK.
    assert query["vercel-blob-signature"] == ["xeXRIufgW7NXkQXO1JabIeFkPZYR2CsE3SUVPEJMCaY"]
    assert set(query) == {"vercel-blob-delegation", "vercel-blob-signature"}
    assert TOKEN not in lease["url"] and "clientSigningToken" not in lease["url"]
    args, options = captured[0]
    assert args == ("https://vercel.com/api/blob/signed-token", TOKEN,
        {"pathname": PATHNAME, "operations": ["get"], "validUntil": 1060000})
    assert options["headers"] == {"x-api-version": "13", "x-vercel-blob-store-id": "teststore123"}


def test_blob_lease_capped_to_session_deadline(monkeypatch):
    monkeypatch.setattr(distribution, "_post_json", lambda *args, **kwargs: blob_reply(validUntil=1001000))
    assert distribution.BlobPrivateDownloads(TOKEN, "teststore123").download_url(
        PATHNAME, session_expires_at=1001, now=1000)["expires_at"] == 1001


def test_blob_beta_access_still_yields_only_sixty_second_download_lease(monkeypatch):
    monkeypatch.setattr(distribution, "_post_json", lambda *args, **kwargs: blob_reply())
    assert distribution.BlobPrivateDownloads(TOKEN, "teststore123").download_url(
        PATHNAME, session_expires_at=1000 + distribution.BETA_ACCESS_TTL, now=1000)["expires_at"] == 1060


@pytest.mark.parametrize("changes", [{"storeId": "store_other"}, {"pathname": "*"}, {"operations": ["get", "put"]},
    {"operations": ["head"]}, {"validUntil": 1060001}, {"validUntil": 1000000}, {"validUntil": True}])
def test_blob_rejects_widened_or_expired_delegation(monkeypatch, changes):
    monkeypatch.setattr(distribution, "_post_json", lambda *args, **kwargs: blob_reply(**changes))
    with pytest.raises(distribution.VercelDistributionUnavailable):
        distribution.BlobPrivateDownloads(TOKEN, "teststore123").download_url(PATHNAME, session_expires_at=1100, now=1000)


@pytest.mark.parametrize("pathname", ["../Mia.dmg", "releases/../Mia.dmg", "/Mia.dmg", "Mia.dmg?secret=x",
    "Mia.dmg#x", "https://evil/Mia.dmg", "Mia.dmg\nHeader", "Mia.zip"])
def test_blob_rejects_arbitrary_object_or_url_before_provider(monkeypatch, pathname):
    monkeypatch.setattr(distribution, "_post_json", lambda *args, **kwargs: pytest.fail("Unsafe path reached provider"))
    with pytest.raises(DistributionError):
        distribution.BlobPrivateDownloads(TOKEN, "teststore123").download_url(pathname, session_expires_at=1100, now=1000)


def test_http_post_bounded_json_and_private_headers(monkeypatch):
    seen = []
    class Response:
        headers = Message()
        headers["Content-Type"] = "application/json"
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def getcode(self): return 200
        def read(self, maximum):
            assert maximum == 17
            return b'{"result":"ok"}'
    class Opener:
        def open(self, request, timeout):
            assert timeout == 8
            seen.append(request)
            return Response()
    monkeypatch.setattr(distribution.urllib.request, "build_opener", lambda handler: Opener())
    assert distribution._post_json("https://mia.upstash.io", TOKEN, ["EVAL", "return 1", 0], maximum=16) == {"result": "ok"}
    request = seen[0]
    assert request.method == "POST" and not urllib.parse.urlsplit(request.full_url).query
    assert request.get_header("Authorization") == "Bearer " + TOKEN
    assert TOKEN.encode() not in request.data
    assert distribution._NoRedirect().redirect_request(None, None, 307, "", {}, "https://evil.test") is None


def test_http_failure_never_echoes_provider_secret(monkeypatch):
    class Opener:
        def open(self, *args, **kwargs): raise OSError(TOKEN)
    monkeypatch.setattr(distribution.urllib.request, "build_opener", lambda handler: Opener())
    with pytest.raises(distribution.VercelDistributionUnavailable) as failed:
        distribution._post_json("https://mia.upstash.io", TOKEN, [], maximum=16)
    assert TOKEN not in str(failed.value)
