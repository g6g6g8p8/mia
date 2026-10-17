"""Portable receipt fault tests; synthetic bytes cannot attest Apple signing."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import plistlib
import shutil
from types import SimpleNamespace

import pytest

from scripts.mac_build_receipt import canonical, make_receipt
from scripts.package_macos import inventory


@pytest.fixture
def build(tmp_path):
    app = tmp_path / "Mia.app"
    resources = app / "Contents/Resources"
    for folder, name, content in (("source", "mia.py", b"# synthetic public source\n"),
                                  ("runtime", "python", b"synthetic runtime fixture"),
                                  ("wheelhouse", "synthetic.whl", b"synthetic wheel fixture")):
        target = resources / folder / name
        target.parent.mkdir(parents=True)
        target.write_bytes(content)
    source_files = inventory(resources / "source")
    report = {"app_version": "0.2.0a14", "architecture": "arm64", "entrypoint": "native-swift",
              "source_provenance": {"revision": "a" * 40, "clean_checkout": True,
                                    "files": source_files, "files_sha256": hashlib.sha256(canonical(source_files)).hexdigest()},
              "runtime_provenance": {"files": inventory(resources / "runtime")},
              "wheelhouse_provenance": {"files": inventory(resources / "wheelhouse")}}
    (resources / "build-report.json").write_text(json.dumps(report))
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({
        "MiaBackendVersion": "0.2.0a14", "CFBundleIdentifier": "org.mia.demo", "LSMinimumSystemVersion": "13.0"}))
    staged = tmp_path / "stage/Mia.app"
    shutil.copytree(app, staged)
    artifact = tmp_path / "Mia-arm64.dmg"
    artifact.write_bytes(b"Synthetic fixture, never a distributable disk image.")
    webkit = tmp_path / "webkit.json"
    service = tmp_path / "service.json"
    common = {"app_version": "0.2.0a14", "final_bundled_runtime_used": True, "bundled_runtime_unchanged": True}
    webkit.write_text(json.dumps({**common, "engine": "actual macOS WKWebView", "native_test_passed": True,
                                  "synthetic_backend_stopped_and_removed": True}))
    service.write_text(json.dumps({**common, "engine": "actual macOS launchd GUI-user domain", "launchd_test_passed": True,
                                   "synthetic_job_unloaded_and_backend_removed": True}))
    return SimpleNamespace(app=app, resources=resources, staged=staged, artifact=artifact, webkit=webkit, service=service)


def receipt(build, **extra):
    return make_receipt(build.app, build.staged, build.artifact, signed=False,
                        webkit_evidence=build.webkit, service_evidence=build.service, **extra)


def edit_json(path: Path, **changes):
    data = json.loads(path.read_text())
    data.update(changes)
    path.write_text(json.dumps(data))


def test_development_receipt_records_final_bytes_and_never_claims_beta_ready(build):
    actual = receipt(build)
    assert actual["sha256"] == hashlib.sha256(build.artifact.read_bytes()).hexdigest()
    assert actual["app_files"] == inventory(build.app) == inventory(build.staged)
    assert actual["app_inventory_sha256"] == hashlib.sha256(canonical(actual["app_files"])).hexdigest()
    for claim in ("signed", "notarized", "codesign_verified", "notarization_accepted",
                  "dmg_ticket_validated", "gatekeeper_assessed", "clean_mac_ui_acceptance", "consumer_distribution_ready"):
        assert actual[claim] is False


def test_signed_build_still_requires_separate_human_acceptance(build, tmp_path):
    notarization = tmp_path / "notarization.json"
    notarization.write_text(json.dumps({"status": "Accepted", "id": "synthetic-notarization-fixture"}))
    actual = make_receipt(build.app, build.staged, build.artifact, signed=True,
                          webkit_evidence=build.webkit, service_evidence=build.service, notarization=notarization)
    assert actual["signed"] is True
    assert actual["clean_mac_ui_acceptance"] is False
    assert actual["consumer_distribution_ready"] is False


def test_staged_app_must_match_the_exact_tested_final_app(build):
    (build.staged / "Contents/Resources/source/mia.py").write_text("# changed only inside staging\n")
    with pytest.raises(ValueError, match="Staged app differs"):
        receipt(build)


@pytest.mark.parametrize("folder,name,error", [
    ("source", "mia.py", "Final source differs"),
    ("runtime", "python", "Final bundled component differs"),
    ("wheelhouse", "synthetic.whl", "Final bundled component differs")])
def test_matching_staged_and_final_bytes_cannot_hide_changed_authenticated_inputs(build, folder, name, error):
    for app in (build.app, build.staged):
        (app / "Contents/Resources" / folder / name).write_bytes(b"changed after authenticated build")
    with pytest.raises(ValueError, match=error):
        receipt(build)


@pytest.mark.parametrize("which,key", [
    ("webkit", "native_test_passed"), ("service", "launchd_test_passed"),
    ("webkit", "synthetic_backend_stopped_and_removed"), ("service", "synthetic_job_unloaded_and_backend_removed"),
    ("webkit", "final_bundled_runtime_used"), ("service", "final_bundled_runtime_used"),
    ("webkit", "bundled_runtime_unchanged"), ("service", "bundled_runtime_unchanged")])
@pytest.mark.parametrize("value", [False, None, "true"])
def test_failed_missing_or_untyped_native_evidence_cannot_produce_receipt(build, which, key, value):
    edit_json(getattr(build, which), **{key: value})
    with pytest.raises(ValueError, match="Native acceptance did not pass"):
        receipt(build)


@pytest.mark.parametrize("which,changes", [
    ("webkit", {"engine": "Chromium"}), ("service", {"engine": "mock systemd"}),
    ("webkit", {"app_version": "0.2.0a13"}), ("service", {"app_version": "0.2.0a13"})])
def test_wrong_native_engine_or_version_cannot_be_relabelled_as_current_mac_acceptance(build, which, changes):
    edit_json(getattr(build, which), **changes)
    with pytest.raises(ValueError, match="Native acceptance did not pass"):
        receipt(build)


def test_signed_claim_requires_accepted_notarization_and_unsigned_claim_cannot_attach_it(build, tmp_path):
    notarization = tmp_path / "notarization.json"
    notarization.write_text(json.dumps({"status": "Invalid", "id": "synthetic-rejected-fixture"}))
    with pytest.raises(ValueError, match="Notarization did not accept"):
        make_receipt(build.app, build.staged, build.artifact, signed=True,
                     webkit_evidence=build.webkit, service_evidence=build.service, notarization=notarization)
    with pytest.raises(ValueError, match="Unsigned build cannot claim notarization"):
        receipt(build, notarization=notarization)


def test_build_evidence_and_artifact_cannot_be_symlink_substitutes(build, tmp_path):
    original = tmp_path / "original.json"
    build.webkit.rename(original)
    build.webkit.symlink_to(original)
    with pytest.raises(ValueError, match="regular bounded file"):
        receipt(build)
    build.webkit.unlink()
    original.rename(build.webkit)
    artifact = tmp_path / "original.dmg"
    build.artifact.rename(artifact)
    build.artifact.symlink_to(artifact)
    with pytest.raises(ValueError, match="regular DMG"):
        receipt(build)


def test_ad_hoc_receipt_requires_real_resource_seal(build, monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stderr="Signature=adhoc\n")
    monkeypatch.setattr("scripts.mac_build_receipt.subprocess.run", run)
    with pytest.raises(ValueError, match="resource seal"):
        receipt(build, ad_hoc_sealed=True)
    assert calls[0][1:4] == ["--verify", "--deep", "--strict"]


def test_ad_hoc_receipt_does_not_claim_apple_signing(build, monkeypatch):
    monkeypatch.setattr("scripts.mac_build_receipt.subprocess.run", lambda *a, **kw: SimpleNamespace(stderr="Signature=adhoc\n"))
    for app in (build.app, build.staged):
        seal = app / "Contents/_CodeSignature/CodeResources"
        seal.parent.mkdir()
        seal.write_bytes(b"synthetic resource seal")
    actual = receipt(build, ad_hoc_sealed=True)
    assert actual["ad_hoc_seal_verified"] is True
    assert actual["signed"] is False and actual["notarized"] is False
