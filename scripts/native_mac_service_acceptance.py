"""Actual isolated launchd user-service lifecycle on a native Mac runner.

The job label is derived from a fresh private synthetic installation. Its plist
lives under a disposable fake home, never the real ~/Library/LaunchAgents. Only
that exact audited job may be unloaded. No sudo, system domain, TCC automation,
login/boot/sleep simulation claim, personal data or external model is involved.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def run(app: Path, source: Path, output: Path) -> dict:
    if sys.platform != "darwin":
        raise RuntimeError("Actual launchd service acceptance requires macOS; Linux cannot certify it.")
    if output.exists() or output.is_symlink():
        raise ValueError("Acceptance output must be a new path.")
    app, source = app.resolve(strict=True), source.resolve(strict=True)
    resources = app / "Contents/Resources"
    if not (resources / "source/mia/operations.py").is_file() or not shutil.which("launchctl"):
        raise ValueError("Final bundled backend and native launchctl are required.")
    sys.path.insert(0, str(source))
    from mia.operations import Manager
    from mia.installation import _loaded_launchd, apply_service_plan, service_plan
    from scripts.package_macos import inventory
    from scripts.native_mac_acceptance import verify_source_binding, write_new

    source_revision = verify_source_binding(app, source)
    runtime_before = inventory(resources / "runtime")
    build = json.loads((resources / "build-report.json").read_text())
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="mia-native-launchd-synthetic-")).resolve()
    stage.chmod(0o700)
    # Real default installation paths contain spaces. Verify actual launchctl
    # output parsing and ProgramArguments without pretending mocks prove it.
    manager = Manager(stage / "Application Support" / "Mia Synthetic")
    fake_home = stage / "synthetic-home"
    fake_home.mkdir(mode=0o700)
    plan = None
    installed = False
    activation_attempted = False
    job_absence_confirmed = False
    cleanup_allowed = False
    cleanup_error = None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def http(path: str) -> dict:
        with opener.open(base + path, timeout=5) as response:
            return json.load(response)

    def healthy(label: str) -> None:
        end = time.monotonic() + 20
        while time.monotonic() < end:
            try:
                status, identity = http("api/status"), http("api/installation")
                if status.get("version") == build["app_version"] and identity.get("installation_id") == installation_id:
                    return
            except (OSError, ValueError):
                pass
            time.sleep(.1)
        raise AssertionError("The exact synthetic launchd installation did not become healthy: " + label)

    def unload_exact_job() -> None:
        if not activation_attempted or plan is None or not _loaded_launchd(plan):
            return
        destination = Path(plan["destination"])
        expected = plistlib.loads(plan["content"].encode())
        if not destination.is_relative_to(fake_home) or destination.is_symlink() or destination.read_text() != plan["content"]:
            raise AssertionError("Synthetic job identity changed; no job was unloaded.")
        target = "gui/" + str(os.getuid()) + "/" + expected["Label"]
        result = subprocess.run(["launchctl", "bootout", target], capture_output=True, text=True, timeout=20, check=False)
        if result.returncode:
            raise AssertionError("The exact synthetic launchd job could not be unloaded safely.")
        end = time.monotonic() + 15
        while time.monotonic() < end:
            if not _loaded_launchd(plan):
                return
            time.sleep(.1)
        raise AssertionError("The synthetic launchd job unload was not confirmed.")

    try:
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        base = f"http://127.0.0.1:{port}/"
        private_env = stage / "machine.env"
        private_env.write_text("MIA_AI_ENABLED=false\nMIA_AI_BASE_URL=\nMIA_AI_MODEL=\nMIA_AI_API_KEY=\nMIA_COOKIE_SECURE=false\nMIA_INSTALLATION_MODE=local\n")
        private_env.chmod(0o600)
        manager.root.parent.mkdir(mode=0o700)
        installation = subprocess.run([str(resources / "runtime/bin/python3"), "-I", "-B", str(resources / "source/mia/operations.py"), "--root", str(manager.root), "install", "--source", str(resources / "source"), "--wheelhouse", str(resources / "wheelhouse"), "--offline", "--port", str(port), "--private-bootstrap", "--env-file", str(private_env)], capture_output=True, text=True, timeout=300, check=False)
        if installation.returncode:
            raise RuntimeError("Final-bundle synthetic launchd installation failed.")
        installed = True
        configuration = json.loads((manager.root / "installation.json").read_text())
        installation_id = configuration["installation_id"]
        plan = service_plan(manager, "launchd", home=fake_home)
        if Path(plan["destination"]).is_relative_to(Path.home() / "Library/LaunchAgents"):
            raise AssertionError("Synthetic acceptance must not install in the real user's LaunchAgents.")
        if _loaded_launchd(plan):
            raise AssertionError("A synthetic acceptance label already exists; no service changed.")
        job_absence_confirmed = True
        # Identity alone is insufficient to prove registration ownership. Only
        # after absence is established may cleanup unload our attempted job.
        activation_attempted = True
        print("Mia Mac service acceptance: exact temporary launchd GUI-user job, private synthetic data.", flush=True)
        first = apply_service_plan(manager, plan, approve_sha256=plan["sha256"], home=fake_home)
        if first.get("applied") is not True or not _loaded_launchd(plan):
            raise AssertionError("Real launchd activation or exact native print parsing failed.")
        healthy("initial activation")
        apply_service_plan(manager, plan, approve_sha256=plan["sha256"], home=fake_home)
        healthy("idempotent activation")
        if http("api/status").get("configured") is not False:
            raise AssertionError("Synthetic service must start with an empty personal library.")
        if http("api/installation").get("bootstrap_protected") is not True:
            raise AssertionError("Synthetic user service must protect first-owner creation.")
        payload = json.dumps({"name": "Synthetic launchd owner", "password": "synthetic-launchd-password-123"}).encode()
        unauthorized = urllib.request.Request(base + "api/setup", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            opener.open(unauthorized, timeout=5)
        except urllib.error.HTTPError as error:
            if error.code != 401:
                raise
        else:
            raise AssertionError("Private launchd service allowed unprivileged owner creation.")
        token = (manager.root / "bootstrap-token").read_text().strip()
        authorized = urllib.request.Request(base + "api/setup", data=payload, headers={"Content-Type": "application/json", "Cookie": "mia_bootstrap=" + token}, method="POST")
        with opener.open(authorized, timeout=5) as response:
            if response.status != 200:
                raise AssertionError("Private synthetic owner creation failed.")

        manager.stop()
        time.sleep(2.2)  # The actual supervisor polls once per second.
        if manager.status().get("running") or not (manager.root / "paused.json").is_file() or not _loaded_launchd(plan):
            raise AssertionError("Explicit stop must remain paused while the launchd supervisor is loaded.")
        manager.start()
        healthy("explicit resume")
        if http("api/status").get("configured") is not True:
            raise AssertionError("Explicit resume did not preserve the synthetic owner.")

        # Exercise actual job removal/re-registration, not an OS-login claim.
        unload_exact_job()
        end = time.monotonic() + 10
        while time.monotonic() < end and manager.status().get("running"):
            time.sleep(.1)
        if manager.status().get("running"):
            raise AssertionError("Service unload did not stop its own verified backend.")
        apply_service_plan(manager, plan, approve_sha256=plan["sha256"], home=fake_home)
        healthy("actual job re-registration")
        if http("api/status").get("configured") is not True:
            raise AssertionError("Actual job re-registration replaced the synthetic owner.")
        if inventory(resources / "runtime") != runtime_before:
            raise AssertionError("Service acceptance altered the immutable bundled runtime.")
        evidence = {"schema": 1, "app_version": build["app_version"], "engine": "actual macOS launchd GUI-user domain",
                    "corpus": "disposable synthetic-only", "launchd_test_passed": True,
                    "final_bundled_runtime_used": True, "bundled_runtime_unchanged": True,
                    "reviewed_source_revision": source_revision, "checkout_matches_final_build_revision": True,
                    "real_user_launchagents_altered": False, "system_services_altered": False,
                    "checks": ["unique temporary plist and exact job identity", "actual launchctl parser with paths containing spaces", "reviewed service activation", "idempotent same-plan activation", "HTTP health and durable installation identity", "private first-owner capability", "explicit pause is not restarted by supervisor", "explicit resume preserves owner", "actual job unload and re-registration preserve owner"],
                    "os_login_verified": False, "os_boot_verified": False, "os_sleep_verified": False,
                    "consumer_distribution_ready": False}
    finally:
        try:
            if plan is not None and not job_absence_confirmed:
                raise RuntimeError("Initial absence of the synthetic label was not established; no job/backend was stopped or deleted.")
            # Verify the exact tracked label/program/args/path before bootout.
            # A changed/foreign loaded job is retained, never blindly stopped.
            unload_exact_job()
            if installed:
                manager.stop()
            cleanup_allowed = True
        except BaseException as error:
            cleanup_error = error
        if cleanup_allowed:
            shutil.rmtree(stage)
        else:
            print("Exact synthetic job/backend cleanup was not confirmed; fixture retained at " + str(stage), file=sys.stderr)
            raise RuntimeError("Native service acceptance cleanup is incomplete; no other job was altered.") from cleanup_error
    evidence["synthetic_job_unloaded_and_backend_removed"] = True
    write_new(output, json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"native_launchd_acceptance": "passed", "checks": len(evidence["checks"]),
                      "model_calls": 0, "os_login_boot_sleep_verified": False}), flush=True)
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    run(arguments.app, arguments.source, arguments.output)


if __name__ == "__main__":
    main()
