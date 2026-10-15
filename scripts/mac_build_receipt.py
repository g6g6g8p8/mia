"""Record final native build bytes; release acceptance remains a separate gate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re

from scripts.package_macos import inventory


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _read(path: Path, *, maximum=16 * 1024 * 1024) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("Build evidence requires a regular bounded file")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("Build evidence must be an object")
    return value


def make_receipt(app: Path, staged_app: Path, artifact: Path, *, signed: bool,
                 webkit_evidence: Path, service_evidence: Path,
                 notarization: Path | None = None) -> dict:
    resources = app / "Contents/Resources"
    report = _read(resources / "build-report.json")
    if artifact.is_symlink() or not artifact.is_file() or artifact.suffix != ".dmg":
        raise ValueError("Artifact must be a regular DMG")
    with artifact.open("rb") as incoming:
        sha = hashlib.file_digest(incoming, "sha256").hexdigest()
    files = inventory(app)
    if files != inventory(staged_app):
        raise ValueError("Staged app differs from the final tested app")
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    source_files = inventory(resources / "source")
    source = report["source_provenance"]
    if source.get("files") != source_files or source.get("files_sha256") != hashlib.sha256(canonical(source_files)).hexdigest():
        raise ValueError("Final source differs from authenticated build inputs")
    for folder, key in (("runtime", "runtime_provenance"), ("wheelhouse", "wheelhouse_provenance")):
        if report[key].get("files") != inventory(resources / folder):
            raise ValueError("Final bundled component differs from build inputs")
    webkit, service = _read(webkit_evidence), _read(service_evidence)
    if (webkit.get("native_test_passed") is not True or service.get("launchd_test_passed") is not True
            or webkit.get("synthetic_backend_stopped_and_removed") is not True
            or service.get("synthetic_job_unloaded_and_backend_removed") is not True
            or any(evidence.get("final_bundled_runtime_used") is not True
                   or evidence.get("bundled_runtime_unchanged") is not True
                   for evidence in (webkit, service))
            or webkit.get("engine") != "actual macOS WKWebView"
            or service.get("engine") != "actual macOS launchd GUI-user domain"
            or webkit.get("app_version") != report["app_version"]
            or service.get("app_version") != report["app_version"]):
        raise ValueError("Native acceptance did not pass")
    if signed:
        if notarization is None:
            raise ValueError("Signed artifact requires actual notarization evidence")
        accepted = _read(notarization)
        if accepted.get("status") != "Accepted" or not isinstance(accepted.get("id"), str):
            raise ValueError("Notarization did not accept this build")
    else:
        if notarization is not None:
            raise ValueError("Unsigned build cannot claim notarization")
        accepted = {}
    version = report["app_version"]
    if info.get("MiaBackendVersion") != version or info.get("CFBundleIdentifier") != "org.mia.demo" or report.get("entrypoint") != "native-swift":
        raise ValueError("Final bundle does not match the native application contract")
    if report["architecture"] not in ("arm64", "x86_64") or not re.fullmatch(r"[0-9][0-9A-Za-z.+-]{0,39}", version):
        raise ValueError("Invalid release version or architecture")
    channel_path = resources / "release-channel.json"
    channel = _read(channel_path) if channel_path.exists() else {}
    return {"format": 2, "artifact": artifact.name, "sha256": sha, "size": artifact.stat().st_size,
            "architecture": report["architecture"], "app_version": version, "backend_version": version,
            "minimum_macos": info["LSMinimumSystemVersion"], "bundle_identifier": info["CFBundleIdentifier"],
            "source_provenance": source, "runtime_provenance": report["runtime_provenance"],
            "wheelhouse_provenance": report["wheelhouse_provenance"], "release_channel": channel,
            "disk_image_integrity_verified": True, "signed": signed, "notarized": signed,
            "codesign_verified": signed, "notarization_accepted": signed,
            "dmg_ticket_validated": signed, "gatekeeper_assessed": signed,
            "notarization_id": accepted.get("id"), "native_backend_smoke_passed": True,
            "native_backend_smoke_scope": "final app runtime after code signing" if signed else "unsigned development app runtime",
            "native_webkit_acceptance": webkit, "native_user_service_acceptance": service,
            "app_files": files, "app_inventory_sha256": hashlib.sha256(canonical(files)).hexdigest(),
            "clean_mac_ui_acceptance": False, "consumer_distribution_ready": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("app", "staged-app", "artifact", "webkit-evidence", "service-evidence"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--signed", action="store_true")
    parser.add_argument("--notarization", type=Path)
    args = parser.parse_args()
    values = vars(args)
    receipt = make_receipt(**values)
    artifact = args.artifact
    for path, content in ((Path(str(artifact) + ".sha256"), receipt["sha256"] + "  " + artifact.name + "\n"),
                          (Path(str(artifact) + ".verification.json"), json.dumps(receipt, indent=2))):
        with path.open("x") as outgoing:
            outgoing.write(content)


if __name__ == "__main__":
    main()
