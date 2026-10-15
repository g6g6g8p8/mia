"""Actual Mac WKWebView acceptance against the final app's bundled backend.

Developer/CI harness only. It creates private disposable synthetic data, never
installs a personal LaunchAgent, never automates another app or changes TCC, and
never contacts an AI provider. Native file chooser callbacks receive synthetic
fixture URLs; a physical NSOpenPanel, Gatekeeper and boot/sleep remain unverified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile


def write_new(path: Path, content: str) -> None:
    """Publish a new private receipt/log without overwriting files or links."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as outgoing:
        outgoing.write(content)
        outgoing.flush()
        os.fsync(outgoing.fileno())


def verify_source_binding(app: Path, source: Path) -> str:
    """Bind checkout-native tests and service helpers to reviewed app inputs.

    The final backend must match the recorded public source inventory. The
    checkout must be clean at the app assembly's exact recorded Git revision;
    this binds the Swift Coordinator compiled by XCTest to that build input.
    It does not claim the signed app's actual window or Gatekeeper was opened.
    """
    from scripts.package_macos import copy_public_source, inventory
    resources = app / "Contents/Resources"
    build = json.loads((resources / "build-report.json").read_text())
    provenance = build.get("source_provenance", {})
    revision = provenance.get("revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision) or provenance.get("clean_checkout") is not True:
        raise AssertionError("Native acceptance requires a recorded clean reviewed Git revision.")
    actual_revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True)
    if actual_revision != revision or dirty:
        raise AssertionError("Native acceptance source differs from the final app's reviewed Git revision.")
    files = inventory(resources / "source")
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if files != provenance.get("files") or digest != provenance.get("files_sha256"):
        raise AssertionError("Final bundled backend differs from its recorded reviewed source inventory.")
    with tempfile.TemporaryDirectory(prefix="mia-native-source-verification-") as temporary:
        expected = Path(temporary) / "source"
        copy_public_source(source, expected)
        if inventory(expected) != files:
            raise AssertionError("Checkout service helpers/backend differ from the final bundled source.")
    return revision


def fixture(stage: Path) -> tuple[Path, Path]:
    folder = stage / "Aurora"
    folder.mkdir(mode=0o700)
    (folder / "decisao.md").write_text("# Decisão Aurora\n\nDecisão: revisar com uma pessoa antes de publicar.")
    (folder / "pendencia.md").write_text("# Pendência Aurora\n\nPendente: conferir a experiência antes do convite.")
    (folder / ".obsidian").mkdir(mode=0o700)
    (folder / ".obsidian/app.json").write_text('{"plugins": []}')
    # Test the real WebKit directory enumerator, not a JavaScript list invented
    # by the harness. Reading this sentinel through a symlink must be refused.
    outside = stage / "outside-secret.md"
    outside.write_text("Synthetic sentinel outside the selected directory; must not be uploaded.")
    (folder / "escaped.md").symlink_to(outside)
    archive = stage / "synthetic-webkit.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as compressed:
        for relative in ("decisao.md", "pendencia.md", ".obsidian/app.json"):
            compressed.write(folder / relative, "Aurora/" + relative)
    return archive, folder


def run(app: Path, source: Path, output: Path) -> dict:
    if sys.platform != "darwin":
        raise RuntimeError("Native Mac acceptance requires macOS and actual WKWebView; Linux cannot certify it.")
    log_path = Path(str(output) + ".log")
    if any(path.exists() or path.is_symlink() for path in (output, log_path)):
        raise ValueError("Acceptance output must be a new path.")
    app, source = app.resolve(strict=True), source.resolve(strict=True)
    resources = app / "Contents/Resources"
    expected = (resources / "runtime/bin/python3", resources / "source/mia/operations.py", resources / "wheelhouse", source / "macos/Mia/Tests/MiaClientTests/NativeWebAcceptanceTests.swift")
    if any(not path.exists() for path in expected):
        raise ValueError("The final app/runtime and checked-out native acceptance source are required.")
    if not shutil.which("swift"):
        raise RuntimeError("Swift/Xcode is required only by this developer acceptance harness.")
    sys.path.insert(0, str(source))
    from mia.operations import Manager
    from scripts.package_macos import inventory

    source_revision = verify_source_binding(app, source)
    report = json.loads((resources / "build-report.json").read_text())
    runtime_before = inventory(resources / "runtime")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="mia-native-webkit-synthetic-")).resolve()
    stage.chmod(0o700)
    manager = Manager(stage / "installation")
    cleanup_allowed = False
    installation_created = False
    token = ""
    try:
        archive, folder = fixture(stage)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        private_env = stage / "synthetic-machine.env"
        private_env.write_text("MIA_AI_ENABLED=false\nMIA_AI_BASE_URL=\nMIA_AI_MODEL=\nMIA_AI_API_KEY=\nMIA_COOKIE_SECURE=false\nMIA_INSTALLATION_MODE=local\n")
        private_env.chmod(0o600)
        install = [str(resources / "runtime/bin/python3"), "-I", "-B", str(resources / "source/mia/operations.py"), "--root", str(manager.root), "install", "--source", str(resources / "source"), "--wheelhouse", str(resources / "wheelhouse"), "--offline", "--port", str(port), "--private-bootstrap", "--env-file", str(private_env)]
        installed = subprocess.run(install, capture_output=True, text=True, timeout=300, check=False)
        if installed.returncode:
            raise RuntimeError("Synthetic final-bundle installation failed before WebKit acceptance.")
        installation_created = True
        token_path = manager.root / "bootstrap-token"
        token = token_path.read_text().strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise AssertionError("Synthetic private bootstrap capability is invalid.")
        manager.start()
        base = f"http://127.0.0.1:{port}/"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(base + "api/status", timeout=5) as response:
            status = json.load(response)
        if status.get("configured") is not False or status.get("version") != report["app_version"]:
            raise AssertionError("Native acceptance must start empty on the final bundled release.")
        with opener.open(base + "api/installation", timeout=5) as response:
            identity = json.load(response)
        if identity.get("bootstrap_protected") is not True:
            raise AssertionError("Native acceptance must enforce private first-owner creation.")
        result_path = stage / "webkit-result.json"
        environment = {key: value for key, value in os.environ.items() if not key.startswith("MIA_")}
        environment.update(MIA_NATIVE_ACCEPTANCE="1", MIA_TEST_BASE_URL=base,
                           MIA_TEST_SETUP_TOKEN_PATH=str(token_path), MIA_TEST_ZIP_PATH=str(archive),
                           MIA_TEST_FOLDER_PATH=str(folder), MIA_TEST_REPORT_PATH=str(result_path))
        print("Mia Mac acceptance: actual WKWebView, private synthetic final-bundle backend, no model calls.", flush=True)
        native = subprocess.run(["swift", "test", "--package-path", str(source / "macos/Mia"), "--force-resolved-versions", "--filter", "NativeWebAcceptanceTests"], capture_output=True, text=True, timeout=300, env=environment, check=False)
        # The capability never appears in published logs, even on a framework
        # error. The native test itself never reads it from page JavaScript.
        log = (native.stdout + native.stderr).replace(token, "[redacted bootstrap capability]")
        write_new(log_path, log)
        if native.returncode or not result_path.is_file():
            print(log[-6000:], file=sys.stderr)
            raise AssertionError("Actual native WebKit acceptance did not pass; do not distribute this artifact.")
        evidence = json.loads(result_path.read_text())
        if evidence.get("engine") != "actual macOS WKWebView" or evidence.get("source_count") != 2 or evidence.get("model_calls") != 0:
            raise AssertionError("Native WebKit did not publish complete acceptance evidence.")
        if inventory(resources / "runtime") != runtime_before:
            raise AssertionError("Acceptance changed the final immutable bundled runtime.")
        evidence.update(app_version=report["app_version"], final_bundled_runtime_used=True,
                        bundled_runtime_unchanged=True, native_test_passed=True,
                        reviewed_source_revision=source_revision, checkout_matches_final_build_revision=True,
                        actual_app_window_exercised=False,
                        consumer_distribution_ready=False)
    finally:
        try:
            if installation_created:
                manager.stop()
            cleanup_allowed = True
        finally:
            if cleanup_allowed:
                shutil.rmtree(stage)
            else:
                print("Synthetic acceptance process stop was not confirmed; disposable fixture retained at " + str(stage), file=sys.stderr)
    evidence["synthetic_backend_stopped_and_removed"] = True
    write_new(output, json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"native_webkit_acceptance": "passed", "app_version": report["app_version"],
                      "checks": len(evidence["checks"]), "source_count": 2, "model_calls": 0,
                      "physical_file_dialog_verified": False, "consumer_distribution_ready": False}), flush=True)
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, type=Path, help="Final assembled/signed Mia.app to test")
    parser.add_argument("--source", required=True, type=Path, help="Reviewed repository with Swift integration tests")
    parser.add_argument("--output", required=True, type=Path, help="New JSON evidence path; adjacent log is sanitized")
    args = parser.parse_args()
    run(args.app, args.source, args.output)


if __name__ == "__main__":
    main()
