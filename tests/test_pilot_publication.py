"""Synthetic policy tests, never evidence of a real Mac acceptance."""
import copy
import hashlib
import sys

import pytest

from mia.pilot_publication import POLICY, acceptance_template, pilot_plan, validate_receipt, verify_mac_artifact
from mia.release_publication import APPLE_GATES, PublicationError, _receipt_metadata, canonical
from test_release_publication import release


@pytest.fixture
def pilot(release):
    receipt = copy.deepcopy(release["receipts"][0])
    artifact = release["kwargs"]["artifacts"]["arm64"]
    for gate in APPLE_GATES:
        receipt[gate] = gate in ("disk_image_integrity_verified", "native_backend_smoke_passed")
    receipt.pop("apple_attestation")
    receipt.update(release_channel={}, consumer_distribution_ready=False)
    receipt["app_files"] = {"Contents/MacOS/Mia": {"sha256": "a" * 64, "executable": True}}
    receipt["app_inventory_sha256"] = hashlib.sha256(canonical(receipt["app_files"])).hexdigest()
    for key, passed, engine, cleaned in (
        ("native_webkit_acceptance", "native_test_passed", "actual macOS WKWebView", "synthetic_backend_stopped_and_removed"),
        ("native_user_service_acceptance", "launchd_test_passed", "actual macOS launchd GUI-user domain", "synthetic_job_unloaded_and_backend_removed"),
    ):
        receipt[key] = {passed: True, cleaned: True, "engine": engine, "app_version": receipt["app_version"],
                        "final_bundled_runtime_used": True, "bundled_runtime_unchanged": True}
    ledger = acceptance_template(receipt)
    ledger.update(operator_approved=True, notice_acknowledged=True)
    for mode in ledger["modes"].values():
        mode["operating_system"] = "Synthetic acceptance fixture"
        for check in mode["checks"].values():
            check.update(status="passed", observed_at=100, evidence="Synthetic test only, not a real acceptance")
    verification = {"policy": POLICY, "artifact_sha256": receipt["sha256"],
                    "receipt_sha256": hashlib.sha256(canonical(receipt)).hexdigest(),
                    "verified_at": 100, "method": "readonly-dmg-and-byte-inventories",
                    "apple_notarized": False, "human_acceptance_verified": False}
    return receipt, artifact, ledger, verification


def test_pilot_never_satisfies_apple_policy(pilot):
    receipt, artifact, *_ = pilot
    assert validate_receipt(receipt, artifact) == receipt
    with pytest.raises(PublicationError):
        _receipt_metadata(receipt, artifact)


def test_pending_acceptances_do_not_become_ready(pilot):
    receipt, artifact, *_ = pilot
    ledger = acceptance_template(receipt)
    assert all(c["status"] == "not_run" for m in ledger["modes"].values() for c in m["checks"].values())
    plan = pilot_plan(receipt, artifact, ledger)
    assert not plan["ready_for_operator_review"]
    assert "local:explicit_first_open" in plan["blocked_gates"]
    assert "local:manual_app_update_preserves_context" in plan["blocked_gates"]


def test_complete_operator_record_still_does_not_publish_or_claim_iphone(pilot):
    plan = pilot_plan(*pilot, now=100)
    assert plan["ready_for_operator_review"]
    assert not plan["ready_for_beta"]
    assert not plan["automatic_app_updates"]
    assert not plan["browser_iphone_verified"]


@pytest.mark.parametrize("change", ["bytes", "apple", "channel", "native", "source", "inventory", "ready"])
def test_invalid_artifact_evidence_is_rejected(pilot, change):
    receipt, artifact, *_ = pilot
    if change == "bytes":
        artifact.write_bytes(b"tampered")
    elif change == "apple":
        receipt["notarized"] = True
    elif change == "channel":
        receipt["release_channel"] = {"appcast_url": "https://example.test"}
    elif change == "native":
        receipt["native_webkit_acceptance"]["bundled_runtime_unchanged"] = False
    elif change == "source":
        receipt["source_provenance"]["clean_checkout"] = False
    elif change == "inventory":
        receipt["app_files"]["new"] = {}
    else:
        receipt["consumer_distribution_ready"] = True
    with pytest.raises(PublicationError):
        pilot_plan(receipt, artifact)


@pytest.mark.parametrize("change", ["hash", "waive_remote", "future", "blank", "malformed", "approval", "verification"])
def test_acceptance_cannot_waive_visible_modes_or_bind_other_artifact(pilot, change):
    receipt, artifact, ledger, verification = pilot
    if change == "hash":
        ledger["artifact_sha256"] = "0" * 64
    elif change == "waive_remote":
        ledger["offered_modes"] = ["local"]
    elif change == "future":
        ledger["modes"]["local"]["checks"]["explicit_first_open"]["observed_at"] = 999999
    elif change == "blank":
        ledger["modes"]["local"]["checks"]["explicit_first_open"]["evidence"] = " " * 20
    elif change == "malformed":
        ledger["modes"] = []
    elif change == "approval":
        ledger["operator_approved"] = 1
    else:
        verification["receipt_sha256"] = "0" * 64
    assert not pilot_plan(receipt, artifact, ledger, verification, now=100)["ready_for_operator_review"]


def test_mac_verification_cannot_be_claimed_from_linux(pilot, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(PublicationError, match="macOS"):
        verify_mac_artifact(*pilot[:2])


@pytest.fixture
def staged(pilot, release, tmp_path, monkeypatch):
    from mia import pilot_publication as module
    receipt, artifact, ledger, verification = pilot
    monkeypatch.setattr(module, "verify_mac_artifact", lambda *_: verification)
    plan = pilot_plan(*pilot)
    destination = tmp_path / "private-pilot"
    result = module.stage_pilot(destination, receipt, artifact, ledger,
        approve_sha256=plan["stage_approve_sha256"], signer=release["build"], public_key=release["build"].public_key)
    return destination, release["build"], result


def test_staged_package_is_authenticated_and_does_not_claim_apple(staged):
    from mia.pilot_publication import verify_pilot_package
    directory, signer, result = staged
    manifest = verify_pilot_package(directory, public_key=signer.public_key)
    assert manifest["apple_notarized"] is False
    assert result["ready_for_beta"] is False
    assert (directory / "Mia.dmg").stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("name", ["Mia.dmg", "receipt.json", "acceptance.json", "mac-verification.json", "pilot-manifest.json", "pilot-signature.json"])
def test_staged_tampering_is_rejected(staged, name):
    from mia.pilot_publication import verify_pilot_package
    directory, signer, _ = staged
    (directory / name).write_bytes(b"modified")
    with pytest.raises(PublicationError):
        verify_pilot_package(directory, public_key=signer.public_key)


def test_package_cannot_supply_its_own_trust_key(staged, release):
    from mia.pilot_publication import verify_pilot_package
    directory, _, _ = staged
    with pytest.raises(PublicationError):
        verify_pilot_package(directory, public_key=release["backend"].public_key)


def test_stage_rejects_stale_approval_before_creating_destination(pilot, release, tmp_path, monkeypatch):
    from mia import pilot_publication as module
    receipt, artifact, ledger, verification = pilot
    plan = pilot_plan(*pilot)
    ledger["modes"]["local"]["checks"]["explicit_first_open"]["evidence"] += " changed"
    monkeypatch.setattr(module, "verify_mac_artifact", lambda *_: verification)
    destination = tmp_path / "stale"
    with pytest.raises(PublicationError):
        module.stage_pilot(destination, receipt, artifact, ledger, approve_sha256=plan["stage_approve_sha256"], signer=release["build"], public_key=release["build"].public_key)
    assert not destination.exists()


def test_stage_never_overwrites_existing_directory(pilot, staged, monkeypatch):
    from mia import pilot_publication as module
    receipt, artifact, ledger, verification = pilot
    directory, signer, _ = staged
    monkeypatch.setattr(module, "verify_mac_artifact", lambda *_: verification)
    before = (directory / "pilot-manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        module.stage_pilot(directory, receipt, artifact, ledger,
            approve_sha256=pilot_plan(*pilot)["stage_approve_sha256"], signer=signer, public_key=signer.public_key)
    assert (directory / "pilot-manifest.json").read_bytes() == before
