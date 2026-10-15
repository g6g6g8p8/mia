import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time

from fastapi.testclient import TestClient
import httpx
import pytest

from test_release_publication import release as signed_release

from mia.demo_distribution import DistributionError, InvitationStore
from mia.release_publication import PublicationError, canonical
from mia.vercel_distribution import VercelDistributionUnavailable
from mia.vercel_release import BlobArtifactUploader, create_vercel_distribution_app, unconfigured_vercel_app, vercel_deployment_plan, write_vercel_kit


class StoreFixture:
    """API contract fixture; real atomic Lua/persistence is tested separately."""
    def __init__(self, root):
        self.invites = InvitationStore(root)
        self.architecture = None
        self.ticket, self.access, self.nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32), None
        self.invitation_id = None

    def redeem(self, token, sha256, *, request_id, architecture):
        result = self.invites.redeem(token, sha256, request_id=request_id)
        if self.architecture is not None and architecture != self.architecture:
            raise DistributionError("wrong arch")
        self.architecture = architecture
        return {**result, "activation_ticket": self.ticket}

    def authorize(self, token, sha256):
        self.invites.authorize(token, sha256)
        return {"expires_at": int(time.time()) + 86400}

    def activate(self, ticket, client_nonce, architecture):
        if ticket != self.ticket or architecture != self.architecture or self.nonce is not None and self.nonce != client_nonce:
            raise DistributionError("activation rejected")
        self.nonce = client_nonce
        return {"access_token": self.access, "expires_at": int(time.time()) + 90 * 86400}

    def authorize_beta(self, access_token, architecture):
        if access_token != self.access or architecture != self.architecture or self.nonce is None:
            raise DistributionError("beta rejected")
        invitation = self.invites.list_invitations()[0]
        if invitation["revoked_at"] is not None:
            raise DistributionError("revoked")
        return {"expires_at": int(time.time()) + 90 * 86400, "invitation_id": invitation["id"]}


class DownloadsFixture:
    def __init__(self):
        self.calls = []

    def download_url(self, pathname, *, session_expires_at):
        self.calls.append((pathname, session_expires_at))
        return {"url": "https://fixture123.private.blob.vercel-storage.com/" + pathname + "?vercel-blob-delegation=fixture&vercel-blob-signature=fixture", "expires_at": int(time.time()) + 60}


@pytest.fixture
def frontend(tmp_path):
    feed_root = tmp_path / "update-feeds"
    feed_root.mkdir()
    content = b'<?xml version="1.0"?><rss version="2.0"><channel><title>Synthetic fixture</title></channel></rss>'
    (feed_root / "arm64.xml").write_bytes(content)
    config = {"protocol": 1, "hosting": "vercel", "origin": "https://mia.example", "download_policy": "private-blob-one-object-60s-leases", "invitation_namespace": "mia-demo-beta", "current_release_id": "0.2.0a14-s1",
        "appcasts": {"arm64": {"filename": "arm64.xml", "sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}},
        "releases": [{"release_id": "0.2.0a14-s1", "version": "0.2.0a14", "artifacts": {"arm64": {"pathname": "0.2.0a14-s1/Mia-arm64.dmg", "sha256": "a" * 64, "size": 132 * 1024**2}}}]}
    store, downloads = StoreFixture(tmp_path / "invites"), DownloadsFixture()
    app = create_vercel_distribution_app(config, feed_root=feed_root, store=store, downloads=downloads)
    return TestClient(app), config, store, downloads, feed_root


def test_initial_download_activation_private_update_and_revocation_without_large_function_body(frontend):
    client, config, store, downloads, _ = frontend
    invitation = store.invites.issue()
    nonce = secrets.token_urlsafe(32)
    body = {"token": invitation["token"], "request_id": nonce, "architecture": "arm64", "release_id": config["current_release_id"]}
    assert client.get("/updates/arm64/appcast.xml").status_code == 401
    assert client.get("/app-updates/0.2.0a14-s1/arm64").status_code == 401
    redeemed = client.post("/redeem", json=body)
    assert redeemed.status_code == 200 and len(redeemed.content) < 4096
    receipt = redeemed.json()
    assert receipt["size"] == 132 * 1024**2 and len(receipt["activation_ticket"]) == 43
    assert client.post("/redeem", json=body).json() == receipt
    lease = client.get("/download/0.2.0a14-s1/arm64", headers={"Authorization": "Bearer " + receipt["download_token"]})
    assert lease.status_code == 200 and len(lease.content) < 4096
    assert ".private.blob.vercel-storage.com/" in lease.json()["download_url"]
    assert lease.headers["Cache-Control"] == "no-store"
    activation = {"ticket": receipt["activation_ticket"], "client_nonce": secrets.token_urlsafe(32), "architecture": "arm64"}
    activated = client.post("/beta/activate", json=activation)
    assert activated.status_code == 200
    access = activated.json()["access_token"]
    headers = {"Authorization": "Bearer " + access}
    assert client.get("/updates/arm64/appcast.xml", headers=headers).status_code == 200
    update = client.get("/app-updates/0.2.0a14-s1/arm64", headers=headers, follow_redirects=False)
    assert update.status_code == 302 and len(update.content) == 0
    assert ".private.blob.vercel-storage.com/" in update.headers["Location"]
    assert len(downloads.calls) == 2
    store.invites.revoke(invitation["id"])
    assert client.get("/download/0.2.0a14-s1/arm64", headers={"Authorization": "Bearer " + receipt["download_token"]}).status_code == 401
    assert client.get("/updates/arm64/appcast.xml", headers=headers).status_code == 401
    assert client.get("/app-updates/0.2.0a14-s1/arm64", headers=headers, follow_redirects=False).status_code == 401
    assert len(downloads.calls) == 2


def test_portal_keeps_invitation_fragment_local_and_emits_activation_link_only_after_redemption(frontend):
    client, _, _, _, _ = frontend
    response = client.get("/invite")
    assert response.status_code == 200
    assert "location.hash.slice(1)" in response.text and "history.replaceState" in response.text
    assert "mia-demo://activate?ticket=" in response.text
    assert "response.blob()" not in response.text
    assert "Intel" not in response.text  # Only reviewed/offered architecture.
    assert "60 segundos" in response.text and "já iniciada" in response.text
    assert "nonce-" in response.headers["Content-Security-Policy"]
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert client.get("/invite?token=do-not-log").status_code == 400


@pytest.mark.parametrize("payload", [{}, {"token": "secret"}, {"token": "secret", "request_id": "secret", "architecture": "x86_64", "release_id": "0.2.0a14-s1"}, {"token": "secret", "request_id": "secret", "architecture": "arm64", "release_id": "not-reviewed"}])
def test_bad_redemptions_never_echo_secret_or_call_private_download(frontend, payload):
    client, _, _, downloads, _ = frontend
    response = client.post("/redeem", json=payload)
    assert response.status_code == 400 and "secret" not in response.text
    assert downloads.calls == []


def test_wrong_origin_and_provider_outage_cannot_authorize_a_download(frontend, monkeypatch):
    client, config, store, downloads, _ = frontend
    invitation = store.invites.issue()
    payload = {"token": invitation["token"], "request_id": secrets.token_urlsafe(32), "architecture": "arm64", "release_id": config["current_release_id"]}
    assert client.post("/redeem", json=payload, headers={"Origin": "https://attacker.example"}).status_code == 403
    def unavailable(*args, **kwargs):
        raise VercelDistributionUnavailable("provider-secret-response")
    monkeypatch.setattr(store, "redeem", unavailable)
    response = client.post("/redeem", json=payload)
    assert response.status_code == 503 and "provider-secret" not in response.text and invitation["token"] not in response.text
    assert downloads.calls == []


def test_private_appcast_hash_is_bound_to_config_and_not_served_after_change(frontend):
    client, _, store, _, feed_root = frontend
    invitation = store.invites.issue()
    receipt = client.post("/redeem", json={"token": invitation["token"], "request_id": secrets.token_urlsafe(32), "architecture": "arm64", "release_id": "0.2.0a14-s1"}).json()
    activated = client.post("/beta/activate", json={"ticket": receipt["activation_ticket"], "client_nonce": secrets.token_urlsafe(32), "architecture": "arm64"}).json()
    (feed_root / "arm64.xml").write_bytes(b"changed")
    assert client.get("/updates/arm64/appcast.xml", headers={"Authorization": "Bearer " + activated["access_token"]}).status_code == 503


def test_unconfigured_preparation_returns_503_and_never_claims_beta_ready():
    response = TestClient(unconfigured_vercel_app()).get("/health")
    assert response.status_code == 503 and response.json()["ready_for_beta"] is False


def test_blob_upload_is_streamed_with_no_overwrite_and_verified_readback(tmp_path):
    artifact = tmp_path / "Mia.dmg"
    artifact.write_bytes(b"synthetic reviewed image")
    checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
    calls = []
    stored = False
    def transport(request):
        nonlocal stored
        calls.append((request.method, str(request.url)))
        if request.method == "HEAD":
            return httpx.Response(200 if stored else 404)
        if request.method == "PUT":
            assert request.headers["x-allow-overwrite"] == "0" and request.headers["x-add-random-suffix"] == "0"
            assert request.headers["x-vercel-blob-access"] == "private"
            assert request.read() == artifact.read_bytes()
            stored = True
            return httpx.Response(200, json={"url": "https://fixture123.private.blob.vercel-storage.com/release/Mia.dmg", "pathname": "release/Mia.dmg"})
        assert request.headers["Authorization"].startswith("Bearer ")
        return httpx.Response(200, content=artifact.read_bytes())
    uploader = BlobArtifactUploader(token="test-private-token-only-in-fixture", store_id="fixture123", access="private", client=httpx.Client(transport=httpx.MockTransport(transport)))
    result = uploader.upload(artifact, "release/Mia.dmg", sha256=checksum)
    assert result["byte_verification"] is True and result["size"] == artifact.stat().st_size
    uploader.upload(artifact, "release/Mia.dmg", sha256=checksum)
    assert sum(method == "PUT" for method, _ in calls) == 1
    assert all("test-private-token" not in url for _, url in calls)


def test_preparation_kit_contains_real_api_config_license_and_no_artifacts_or_secrets(tmp_path):
    source = Path(__file__).resolve().parents[1]
    plan = vercel_deployment_plan(domain="mia-demo.example", project_name="mia-demo")
    output = tmp_path / "vercel"
    result = write_vercel_kit(plan, output, source=source)
    assert result["ready_for_deployment"] is False and result["unconfigured_returns"] == 503
    assert (output / "api/index.py").is_file() and (output / "vercel.json").is_file()
    assert (output / "LICENSE").is_file() and (output / "THIRD_PARTY_LICENSES/native-inventory.json").is_file()
    assert not list(output.rglob("*.dmg")) and not list(output.rglob("*.pem")) and not list(output.rglob(".env"))
    assert not (output / "distribution-release.json").exists()
    settings = json.loads((output / "vercel.json").read_text())
    assert settings["functions"]["api/index.py"]["maxDuration"] == 30
    assert settings["routes"][-1]["dest"] == "/api/index.py"
    # Exercise the generated entry point from the kit itself, with no source
    # checkout on sys.path and no provider/account resources configured.
    subprocess.run([sys.executable, "-c", "from api.index import app; from fastapi.testclient import TestClient; r=TestClient(app).get('/health'); assert r.status_code == 503 and r.json()['ready_for_beta'] is False"], cwd=output, check=True, capture_output=True)
    with pytest.raises(PublicationError, match="nova"):
        write_vercel_kit(plan, output, source=source)


def test_plan_changes_and_mixed_public_private_store_are_refused(tmp_path):
    with pytest.raises(PublicationError, match="distintos"):
        vercel_deployment_plan(domain="mia.example", project_name="mia-demo", private_store_id="fixture123", public_store_id="fixture123")
    plan = vercel_deployment_plan(domain="mia.example", project_name="mia-demo")
    plan["origin"] = "https://changed.example"
    with pytest.raises(PublicationError, match="mudou"):
        write_vercel_kit(plan, tmp_path / "new", source=Path(__file__).resolve().parents[1])


def test_production_kit_preserves_historical_packages_and_keeps_appcasts_out_of_public_files(signed_release, tmp_path):
    """Synthetic signed fixture, not evidence of Apple or real Vercel acceptance."""
    from mia.release_publication import stage_release
    fixture = signed_release
    stage_release(fixture["state"], **fixture["kwargs"])
    first = json.loads((fixture["state"] / "current.json").read_text())
    stage_release(fixture["state"], refresh=True, **fixture["kwargs"])
    current = json.loads((fixture["state"] / "current.json").read_text())
    records = []
    for manifest in (first, current):
        for name, entry in manifest["files"].items():
            if not name.endswith((".dmg", ".zip")):
                continue
            access = "private" if name.endswith(".dmg") else "public"
            store = "private123" if access == "private" else "public123"
            pathname = manifest["release_id"] + "/" + name
            records.append({"access": access, "store_id": store, "pathname": pathname, **entry,
                "url": "https://" + store + "." + access + ".blob.vercel-storage.com/" + pathname, "byte_verification": True})
    plan = vercel_deployment_plan(domain="mia.example", project_name="mia-demo", private_store_id="private123", public_store_id="public123", publication=current)
    output = tmp_path / "production-kit"
    result = write_vercel_kit(plan, output, source=Path(__file__).resolve().parents[1], publisher_state=fixture["state"], uploads=records)
    assert result["ready_for_deployment"] is True and result["deployed"] is False
    config = json.loads((output / "distribution-release.json").read_text())
    assert len(config["releases"]) == 2
    assert (output / "update-feeds/arm64.xml").is_file()
    assert not list((output / "public").rglob("*.xml"))
    settings = json.loads((output / "vercel.json").read_text())
    destinations = {route.get("dest") for route in settings["routes"]}
    for manifest in (first, current):
        for arch in ("arm64", "x86_64"):
            assert "https://public123.public.blob.vercel-storage.com/" + manifest["release_id"] + "/backend-" + arch + ".zip" in destinations
    filesystem_index = next(index for index, route in enumerate(settings["routes"]) if route.get("handle") == "filesystem")
    assert "update-feeds" in settings["routes"][filesystem_index - 1]["src"]
    client = TestClient(create_vercel_distribution_app(config, feed_root=output / "update-feeds", store=StoreFixture(tmp_path / "invite-fixture"), downloads=DownloadsFixture()))
    assert client.get("/updates/arm64/appcast.xml").status_code == 401
    assert client.get("/update-feeds/arm64.xml").status_code == 404
    assert client.get("/distribution-release.json").status_code == 404
    assert client.get("/invite/" + first["release_id"]).status_code == 200
    missing_historical = [entry for entry in records if entry["pathname"] != first["release_id"] + "/backend-arm64.zip"]
    with pytest.raises(PublicationError, match="anteriores"):
        write_vercel_kit(plan, tmp_path / "missing-history", source=Path(__file__).resolve().parents[1], publisher_state=fixture["state"], uploads=missing_historical)
