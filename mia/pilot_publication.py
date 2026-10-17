"""Explicit, non-notarized pilot policy; never an Apple release attestation.

Produces private review material only. It does not deploy, issue invitations,
change Gatekeeper, or enable automatic application updates.
"""
from __future__ import annotations

import hashlib
import plistlib
import time
from pathlib import Path
import sys

from mia.release_publication import (
    APPLE_GATES, PublicationError, _mounted_dmg, _receipt_metadata,
    _regular, _run, canonical,
)

POLICY = "mac-direct-unnotarized-v1"
NOTICE = "Piloto sem Developer ID ou notarização Apple. A primeira abertura pode exigir autorização explícita no macOS."
CHECKS = {
    "local": (
        "browser_download_with_quarantine", "explicit_first_open", "empty_installation",
        "import_and_today_sources", "quit_without_terminal", "restart_and_login",
        "sleep_and_resume", "snapshot_and_restore", "manual_app_update_preserves_context",
        "backend_update_preserves_context",
    ),
    "remote": (
        "verified_ssh_host", "empty_installation", "import_and_today_sources",
        "quit_without_terminal", "server_restart", "reconnect_and_login",
        "snapshot_and_restore", "backend_update_preserves_context",
    ),
}


def validate_receipt(receipt: dict, artifact: Path) -> dict:
    """Validate original build evidence without claiming Apple certification."""
    _receipt_metadata(receipt, artifact, require_apple=False, require_channel=False)
    if artifact.suffix != ".dmg":
        raise PublicationError("Piloto exige DMG")
    for gate in APPLE_GATES:
        expected = gate in ("disk_image_integrity_verified", "native_backend_smoke_passed")
        if receipt.get(gate) is not expected:
            raise PublicationError("Recibo não corresponde à política explícita sem notarização")
    if receipt.get("apple_attestation") or receipt.get("notarization_id"):
        raise PublicationError("Piloto não aceita declaração Apple")
    # This first pilot has manual app/backend delivery, not the old signed channel.
    if receipt.get("release_channel") != {}:
        raise PublicationError("Piloto manual exige build sem canal automático")
    if receipt.get("consumer_distribution_ready") is not False:
        raise PublicationError("Recibo de build não pode declarar aceite de participantes")
    files = receipt.get("app_files")
    if not isinstance(files, dict) or not files or receipt.get("app_inventory_sha256") != hashlib.sha256(canonical(files)).hexdigest():
        raise PublicationError("Inventário final do app inválido")
    for key, passed, engine, cleaned in (
        ("native_webkit_acceptance", "native_test_passed", "actual macOS WKWebView", "synthetic_backend_stopped_and_removed"),
        ("native_user_service_acceptance", "launchd_test_passed", "actual macOS launchd GUI-user domain", "synthetic_job_unloaded_and_backend_removed"),
    ):
        record = receipt.get(key)
        if not isinstance(record, dict) or record.get(passed) is not True or record.get(cleaned) is not True or record.get("engine") != engine or record.get("app_version") != receipt["app_version"] or any(record.get(k) is not True for k in ("final_bundled_runtime_used", "bundled_runtime_unchanged")):
            raise PublicationError("Evidência nativa do build incompleta")
    return receipt


def verify_mac_artifact(receipt: dict, artifact: Path) -> dict:
    """Verify disk image and final inventories, without running its executables."""
    if sys.platform != "darwin":
        raise PublicationError("Verificação do DMG requer macOS")
    artifact = _regular(artifact)
    validate_receipt(receipt, artifact)
    _run(["/usr/bin/hdiutil", "verify", str(artifact)], timeout=120)
    with _mounted_dmg(artifact) as mount:
        from scripts.package_macos import inventory, macho_architecture
        app = mount / "Mia.app"
        if app.is_symlink() or not app.is_dir():
            raise PublicationError("DMG não contém Mia.app regular")
        resources = app / "Contents/Resources"
        info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
        if (inventory(app) != receipt["app_files"]
                or macho_architecture(app / "Contents/MacOS/Mia") != receipt["architecture"]
                or info.get("MiaBackendVersion") != receipt["app_version"]
                or info.get("CFBundleIdentifier") != receipt["bundle_identifier"]
                or info.get("LSMinimumSystemVersion") != receipt["minimum_macos"]):
            raise PublicationError("App montado difere do recibo")
        for folder, key in (("source", "source_provenance"), ("runtime", "runtime_provenance"), ("wheelhouse", "wheelhouse_provenance")):
            if inventory(resources / folder) != receipt.get(key, {}).get("files"):
                raise PublicationError("Componente montado difere do inventário")
        if (resources / "release-channel.json").exists():
            raise PublicationError("App de piloto contém canal automático")
    return {"policy": POLICY, "artifact_sha256": receipt["sha256"],
            "receipt_sha256": hashlib.sha256(canonical(receipt)).hexdigest(),
            "verified_at": int(time.time()), "method": "readonly-dmg-and-byte-inventories",
            "apple_notarized": False, "human_acceptance_verified": False}


def acceptance_template(receipt: dict) -> dict:
    return {"policy": POLICY, "operator_approved": False, "artifact_sha256": receipt["sha256"],
            "architecture": receipt["architecture"], "version": receipt["app_version"],
            "notice_acknowledged": False,
            # Both destinations are visible in the existing app; cannot waive one by JSON.
            "offered_modes": list(CHECKS),
            "modes": {mode: {"operating_system": "", "checks": {
                check: {"status": "not_run", "observed_at": None, "evidence": ""}
                for check in checks}} for mode, checks in CHECKS.items()}}


def pilot_plan(receipt: dict, artifact: Path, acceptance: dict | None = None,
               mac_verification: dict | None = None, *, now: int | None = None) -> dict:
    validate_receipt(receipt, artifact)
    now = int(time.time()) if now is None else now
    acceptance, verification = acceptance or {}, mac_verification or {}
    blocked = []
    for key, expected in (("policy", POLICY), ("artifact_sha256", receipt["sha256"]),
                          ("architecture", receipt["architecture"]), ("version", receipt["app_version"]),
                          ("operator_approved", True), ("notice_acknowledged", True)):
        if type(acceptance.get(key)) is not type(expected) or acceptance.get(key) != expected:
            blocked.append("acceptance:" + key)
    if acceptance.get("offered_modes") != list(CHECKS):
        blocked.append("acceptance:offered_modes")
    modes = acceptance.get("modes")
    modes = modes if isinstance(modes, dict) else {}
    for mode, names in CHECKS.items():
        record = modes.get(mode)
        record = record if isinstance(record, dict) else {}
        operating_system = record.get("operating_system")
        if not isinstance(operating_system, str) or not 3 <= len(operating_system.strip()) <= 200:
            blocked.append(mode + ":operating_system")
        checks = record.get("checks")
        checks = checks if isinstance(checks, dict) else {}
        for name in names:
            check = checks.get(name)
            check = check if isinstance(check, dict) else {}
            stamp, evidence = check.get("observed_at"), check.get("evidence")
            if check.get("status") != "passed" or type(stamp) is not int or not 1 <= stamp <= now + 300 or not isinstance(evidence, str) or not 10 <= len(evidence.strip()) <= 2000:
                blocked.append(mode + ":" + name)
    for key, expected in (("policy", POLICY), ("artifact_sha256", receipt["sha256"]),
                          ("receipt_sha256", hashlib.sha256(canonical(receipt)).hexdigest()),
                          ("method", "readonly-dmg-and-byte-inventories"),
                          ("apple_notarized", False), ("human_acceptance_verified", False)):
        if type(verification.get(key)) is not type(expected) or verification.get(key) != expected:
            blocked.append("mac_verification:" + key)
    stamp = verification.get("verified_at")
    if type(stamp) is not int or not 1 <= stamp <= now + 300:
        blocked.append("mac_verification:verified_at")
    result = {"protocol": 1, "policy": POLICY, "notice": NOTICE,
              "artifact": artifact.name, "artifact_sha256": receipt["sha256"],
              "architecture": receipt["architecture"], "version": receipt["app_version"],
              "receipt_sha256": hashlib.sha256(canonical(receipt)).hexdigest(),
              "acceptance_sha256": hashlib.sha256(canonical(acceptance)).hexdigest(),
              "mac_verification_sha256": hashlib.sha256(canonical(verification)).hexdigest(),
              "blocked_gates": blocked, "ready_for_operator_review": not blocked,
              "ready_for_beta": False, "automatic_app_updates": False,
              "browser_iphone_verified": False,
              "evidence_trust": "operator-supplied; publication must authenticate evidence and artifact"}
    return {**result, "approve_sha256": hashlib.sha256(canonical(result)).hexdigest()}
