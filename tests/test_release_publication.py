"""Synthetic release fixtures; no Apple acceptance or production key is implied."""
import base64
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import time
import xml.etree.ElementTree as ET
import zipfile

from fastapi.testclient import TestClient
import pytest

from mia import updates
from mia.demo_distribution import DistributionError, InvitationStore, create_distribution_app
from mia.release_publication import (ACCEPTANCE_CHECKS, APPLE_GATES, ARCHITECTURES, OpenSSLSigner, PublicationError, SPARKLE_NS,
    acceptance_failures, acceptance_template, canonical, channel_for, create_release_distribution_app, digest, extract_sparkle_tools,
    publication_plan, read_attestation, stage_release, verify_ed25519)
from mia.updates import UpdateController
from scripts.package_macos import copy_public_source, inventory


def key(tmp_path, name):
    path = tmp_path / (name + ".pem")
    subprocess.run(["/usr/bin/openssl", "genpkey", "-algorithm", "ED25519", "-out", str(path)], check=True, capture_output=True)
    path.chmod(0o600)
    return OpenSSLSigner(path)


class FixtureSparkleSigner:
    """Linux-only fixture: archive signatures are real; XML signing is observed.

    Production CLI exclusively constructs the upstream hash-verified native
    SparkleSigner. This fixture cannot establish any Apple/sign_update claim.
    """
    def __init__(self, signer):
        self.signer, self.public_key, self.appcasts = signer, signer.public_key, []

    def sign(self, path):
        return self.signer.sign(path)

    def sign_appcast(self, path):
        self.appcasts.append(path.name)


@pytest.fixture
def release(tmp_path):
    build, backend, sparkle = key(tmp_path, "build"), key(tmp_path, "backend"), key(tmp_path, "sparkle")
    source = tmp_path / "source-checkout"
    (source / "mia").mkdir(parents=True)
    (source / "pyproject.toml").write_text('[project]\nname="mia-personal-ai"\nversion="0.2.0a14"\n')
    (source / "mia/__init__.py").write_text('__version__ = "0.2.0a14"\n')
    (source / "LICENSE").write_text("Synthetic test license, no production distribution\n")
    (source / "NOTICE").write_text("Synthetic test notice\n")
    (source / "requirements.lock").write_text("synthetic==1.0\n")
    public = tmp_path / "public-source"
    copy_public_source(source, public)
    source_files = inventory(public)
    provenance = {"revision": "1" * 40, "clean_checkout": True, "files": source_files, "files_sha256": hashlib.sha256(canonical(source_files)).hexdigest()}
    artifacts, attestations, wheels, receipts = {}, {}, {}, []
    for arch in ARCHITECTURES:
        artifact = tmp_path / ("Mia-" + arch + ".dmg")
        artifact.write_bytes(b"Synthetic fixture, not an Apple disk image: " + arch.encode())
        artifacts[arch] = artifact
        wheelhouse = tmp_path / ("wheels-" + arch)
        wheelhouse.mkdir()
        (wheelhouse / "synthetic-1.0-py3-none-any.whl").write_bytes(b"Synthetic fixture not installed")
        wheels[arch] = wheelhouse
        receipt = {"format": 2, "artifact": artifact.name, "sha256": digest(artifact), "size": artifact.stat().st_size,
            "architecture": arch, "app_version": "0.2.0a14", "backend_version": "0.2.0a14", "minimum_macos": "13.0", "bundle_identifier": "org.mia.demo",
            "source_provenance": provenance, "wheelhouse_provenance": {"files": inventory(wheelhouse)},
            "release_channel": channel_for("https://mia.example", "beta", arch, backend.public_key, sparkle.public_key),
            "apple_attestation": {"verified_at": int(time.time()), "method": "read-only-dmg-apple-tools-and-byte-inventories"},
            **{gate: True for gate in APPLE_GATES}}
        receipts.append(receipt)
        payload = tmp_path / (arch + ".receipt")
        payload.write_bytes(canonical(receipt))
        attestation = tmp_path / (arch + ".attestation.json")
        attestation.write_text(json.dumps({"protocol": 1, "payload": base64.b64encode(payload.read_bytes()).decode(), "signature": build.sign(payload)}))
        attestations[arch] = attestation
    ledger = acceptance_template(receipts)
    ledger["operator_approved"] = True
    for artifact in ledger["artifacts"]:
        for mode in artifact["modes"].values():
            mode["operating_system"] = "Synthetic fixture, not a real acceptance"
            for check in mode["checks"].values():
                check.update(status="passed", observed_at=int(time.time()), evidence="Synthetic fixture checks; never production evidence")
    acceptance = tmp_path / "acceptance.json"
    acceptance.write_bytes(canonical(ledger))
    plan = publication_plan(receipts, ledger, origin="https://mia.example", channel="beta", build_public_key=build.public_key)
    kwargs = {"source": source, "artifacts": artifacts, "attestations": attestations, "wheelhouses": wheels, "acceptance_path": acceptance,
        "origin": "https://mia.example", "channel": "beta", "build_public_key": build.public_key, "backend_signer": backend,
        "sparkle_signer": FixtureSparkleSigner(sparkle), "approve_sha256": plan["approve_sha256"], "notes": "Synthetic private review fixture"}
    return {"state": tmp_path / "publisher", "kwargs": kwargs, "receipts": receipts, "ledger": ledger, "build": build, "backend": backend, "sparkle": sparkle}


def test_ed25519_key_is_private_and_signature_verifies_exact_bytes(tmp_path):
    signer = key(tmp_path, "private")
    payload = tmp_path / "payload"
    payload.write_bytes(b"reviewed source")
    signature = signer.sign(payload)
    verify_ed25519(signer.public_key, signature, payload)
    payload.write_bytes(b"tampered source")
    with pytest.raises(PublicationError):
        verify_ed25519(signer.public_key, signature, payload)
    signer.key_file.chmod(0o644)
    with pytest.raises(PublicationError, match="0600"):
        signer.sign(payload)


def test_unreviewed_sparkle_tool_is_never_extracted_or_executed(tmp_path):
    archive = tmp_path / "Sparkle.tar.xz"
    archive.write_bytes(b"not the pinned official archive")
    with pytest.raises(PublicationError, match="oficial"):
        extract_sparkle_tools(archive, tmp_path / "tools")
    assert not (tmp_path / "tools").exists()


def test_acceptance_template_never_marks_real_mac_or_server_checks_passed(release):
    template = acceptance_template(release["receipts"])
    assert template["operator_approved"] is False
    assert all(check["status"] == "not_run" and check["observed_at"] is None for artifact in template["artifacts"] for mode in artifact["modes"].values() for check in mode["checks"].values())
    failures = acceptance_failures(template, release["receipts"])
    assert "operator_acceptance_approval" in failures
    for architecture in ARCHITECTURES:
        assert architecture + ":remote:server_restart" in failures
        assert architecture + ":local:signed_app_update_preserves_context" in failures


def test_acceptance_cannot_waive_an_installation_mode_visible_in_the_app(release):
    ledger = json.loads(canonical(release["ledger"]))
    ledger["artifacts"][0]["offered_modes"] = ["local"]
    assert ledger["artifacts"][0]["architecture"] + ":offered_modes" in acceptance_failures(ledger, release["receipts"])


def test_remote_acceptance_requires_a_context_preserving_backend_update(release):
    ledger = json.loads(canonical(release["ledger"]))
    artifact = ledger["artifacts"][0]
    artifact["modes"]["remote"]["checks"]["signed_backend_update_preserves_context"]["status"] = "not_run"
    assert artifact["architecture"] + ":remote:signed_backend_update_preserves_context" in acceptance_failures(ledger, release["receipts"])


@pytest.mark.parametrize("tamper", ["receipt_signature", "artifact_bytes", "build_trust_key"])
def test_attestation_cannot_be_replaced_by_unsigned_flags(release, tmp_path, tamper):
    kwargs = release["kwargs"]
    artifact, envelope = kwargs["artifacts"]["arm64"], kwargs["attestations"]["arm64"]
    public_key = release["build"].public_key
    if tamper == "receipt_signature":
        contents = json.loads(envelope.read_text())
        receipt = json.loads(base64.b64decode(contents["payload"]))
        receipt["notarized"] = False
        contents["payload"] = base64.b64encode(canonical(receipt)).decode()
        envelope.write_bytes(canonical(contents))
    elif tamper == "artifact_bytes":
        artifact.write_bytes(artifact.read_bytes() + b"tampered")
    else:
        public_key = key(tmp_path, "otherbuild").public_key
    with pytest.raises(PublicationError):
        read_attestation(envelope, artifact, public_key)


@pytest.mark.parametrize("tamper", ["missing_gate", "changed_channel", "changed_arch_source", "missing_acceptance", "changed_acceptance_sha", "unsigned_wheels", "wrong_approval", "wrong_signing_key"])
def test_release_rejects_each_unresolved_gate_before_pointer_commit(release, tmp_path, tamper):
    kwargs = dict(release["kwargs"])
    if tamper in ("missing_gate", "changed_channel", "changed_arch_source"):
        path = kwargs["attestations"]["arm64"]
        envelope = json.loads(path.read_text())
        receipt = json.loads(base64.b64decode(envelope["payload"]))
        if tamper == "missing_gate":
            receipt["gatekeeper_assessed"] = False
        elif tamper == "changed_channel":
            receipt["release_channel"]["appcast_url"] = "https://attacker.example/appcast.xml"
        else:
            receipt["source_provenance"]["revision"] = "2" * 40
        payload = tmp_path / "mutated-receipt"
        payload.write_bytes(canonical(receipt))
        path.write_bytes(canonical({"protocol": 1, "payload": base64.b64encode(payload.read_bytes()).decode(), "signature": release["build"].sign(payload)}))
    elif tamper == "missing_acceptance":
        ledger = release["ledger"]
        ledger["artifacts"][0]["modes"]["remote"]["checks"]["server_restart"]["status"] = "not_run"
        kwargs["acceptance_path"].write_bytes(canonical(ledger))
    elif tamper == "changed_acceptance_sha":
        ledger = release["ledger"]
        ledger["declaration"] += " Changed after approval"
        kwargs["acceptance_path"].write_bytes(canonical(ledger))
    elif tamper == "unsigned_wheels":
        next(kwargs["wheelhouses"]["arm64"].iterdir()).write_bytes(b"changed wheels")
    elif tamper == "wrong_approval":
        kwargs["approve_sha256"] = "f" * 64
    else:
        kwargs["backend_signer"] = key(tmp_path, "wrongbackend")
    with pytest.raises(PublicationError):
        stage_release(release["state"], **kwargs)
    assert not (release["state"] / "current.json").exists()


def test_full_immutable_publication_serves_invites_ranges_and_authenticated_updates(release, tmp_path, monkeypatch):
    staged = stage_release(release["state"], **release["kwargs"])
    assert staged["published"] and staged["sequence"] == 1 and staged["invitations_sent"] == 0
    root = Path(staged["directory"])
    manifest = json.loads((root / "publication.json").read_text())
    assert set(manifest["portals"]) == set(ARCHITECTURES)
    assert release["kwargs"]["sparkle_signer"].appcasts == ["appcast-arm64.xml", "appcast-x86_64.xml"]
    state = tmp_path / "invites"
    store = InvitationStore(state)
    invite = store.issue()
    app = create_release_distribution_app(release["state"], state)
    client = TestClient(app)
    assert client.get("/invite").status_code == 200
    assert client.get("/publication.json").status_code == 404
    assert client.get("/invite?token=secret").status_code == 400
    prefix = manifest["portals"]["arm64"]["prefix"]
    landing = client.get(prefix + "/invite").text
    assert "fetch('" + prefix + "/redeem'" in landing
    assert manifest["portals"]["arm64"]["sha256"] in landing
    request_id = secrets.token_urlsafe(32)
    response = client.post(prefix + "/redeem", json={"token": invite["token"], "request_id": request_id})
    assert response.status_code == 200
    receipt = response.json()
    assert receipt["download_path"] == prefix + "/download"
    assert client.post(prefix + "/redeem", json={"token": invite["token"], "request_id": request_id}).json()["download_token"] == receipt["download_token"]
    other = manifest["portals"]["x86_64"]["prefix"]
    assert client.post(other + "/redeem", json={"token": invite["token"], "request_id": request_id}).status_code == 410
    response = client.get(prefix + "/download", headers={"Authorization": "Bearer " + receipt["download_token"], "Range": "bytes=0-9"})
    assert response.status_code == 206 and response.content == release["kwargs"]["artifacts"]["arm64"].read_bytes()[:10]
    store.revoke(invite["id"])
    assert client.get(prefix + "/download", headers={"Authorization": "Bearer " + receipt["download_token"]}).status_code == 401
    for architecture in ARCHITECTURES:
        resources = tmp_path / ("Resources-" + architecture)
        resources.mkdir()
        (resources / "release-channel.json").write_bytes(canonical(channel_for("https://mia.example", "beta", architecture, release["backend"].public_key, release["sparkle"].public_key)))
        controller = UpdateController(resources, tmp_path / ("home-" + architecture))
        def fetch(url, target, limit, expected_size=None):
            from urllib.parse import urlsplit
            response = client.get(urlsplit(url).path)
            assert response.status_code == 200
            target.write_bytes(response.content)
            target.chmod(0o600)
        monkeypatch.setattr(updates, "_fetch", fetch)
        available = controller.handle("updates_check", {})
        assert available["state"] == "available"
        prepared = controller.handle("updates_prepare", {"release_id": available["releases"][0]["id"]})
        assert prepared["state"] == "prepared" and prepared["backend_version"] is None
        source_zip = root / ("backend-" + architecture + ".zip")
        with zipfile.ZipFile(source_zip) as archive:
            assert "source/LICENSE" in archive.namelist() and "source/.env" not in archive.namelist()
        assert client.get("/updates/" + architecture + "/appcast.xml").status_code == 401
        appcast = ET.fromstring((root / ("appcast-" + architecture + ".xml")).read_bytes())
        enclosure = appcast.find("channel/item/enclosure")
        assert enclosure.get("{" + SPARKLE_NS + "}version") == "0.2.0a14"
        verify_ed25519(release["sparkle"].public_key, enclosure.get("{" + SPARKLE_NS + "}edSignature"), root / ("Mia-" + architecture + ".dmg"))


def test_repeated_publication_refused_and_refresh_is_monotonic_with_old_download_preserved(release, tmp_path):
    first = stage_release(release["state"], **release["kwargs"])
    with pytest.raises(PublicationError, match="repetida"):
        stage_release(release["state"], **release["kwargs"])
    second = stage_release(release["state"], **release["kwargs"], refresh=True)
    assert second["sequence"] == 2 and first["release_id"] != second["release_id"]
    old = json.loads((Path(first["directory"]) / "publication.json").read_text())
    store = InvitationStore(tmp_path / "invites")
    invite = store.issue()
    client = TestClient(create_release_distribution_app(release["state"], tmp_path / "invites"))
    prefix = old["portals"]["arm64"]["prefix"]
    receipt = client.post(prefix + "/redeem", json={"token": invite["token"], "request_id": secrets.token_urlsafe(32)}).json()
    assert client.get(prefix + "/download", headers={"Authorization": "Bearer " + receipt["download_token"]}).status_code == 200


def test_changed_publication_bytes_pause_startup_and_live_download(release, tmp_path):
    staged = stage_release(release["state"], **release["kwargs"])
    state = tmp_path / "invites"
    client = TestClient(create_release_distribution_app(release["state"], state))
    manifest = json.loads((Path(staged["directory"]) / "publication.json").read_text())
    package = Path(staged["directory"]) / "backend-arm64.zip"
    package.write_bytes(package.read_bytes() + b"changed")
    route = next(route for route, name in manifest["routes"].items() if name == package.name)
    assert client.get(route).status_code == 503
    with pytest.raises(PublicationError, match="difere"):
        create_release_distribution_app(release["state"], state)


@pytest.mark.parametrize("prefix", ["/../bad", "//bad", "/bad?token=x", "/bad#secret", "/bad'js", "https://external"])
def test_portal_prefix_cannot_inject_script_or_redirect(tmp_path, prefix):
    artifact = tmp_path / "Mia.dmg"
    artifact.write_bytes(b"synthetic")
    with pytest.raises(DistributionError):
        create_distribution_app(tmp_path / "state", artifact, sha256=digest(artifact), url_prefix=prefix)
