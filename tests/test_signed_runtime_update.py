"""Re-signed app updates retain the exact private runtime and recoverable data.

The executable signatures here are synthetic bytes, never executed. Real
Manager.update owns SQLite snapshots and recovery; only offline installation
and process start are replaced so the contract can be checked on Linux.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

import pytest

from mia import db, desktop
from mia.desktop import DesktopController, DesktopError
from mia.launcher import runtime_inventory
from mia.operations import Manager, _write
from test_desktop import bundle, darwin, mock_install_worker


def signed_report(resources: Path) -> dict:
    report = json.loads((resources / "build-report.json").read_text())
    runtime = report["runtime_provenance"]
    runtime["source_archive_files"] = dict(runtime["files"])
    runtime.update(source_url="https://github.com/astral-sh/python-build-standalone/releases/download/20261013/cpython-synthetic.tar.gz",
                   archive_sha256="a" * 64, license_archive_sha256="b" * 64,
                   official_checksum_source="https://github.com/astral-sh/python-build-standalone/releases/download/20261013/SHA256SUMS",
                   license_archive_url="https://github.com/astral-sh/python-build-standalone/releases/download/20261013/cpython-synthetic-full.tar.zst",
                   content_transformations=[],
                   content_transformation="Developer ID codesign of native runtime executables/libraries",
                   python_entitlements={"com.apple.security.cs.disable-library-validation": True})
    executable = resources / "runtime/bin/python3"
    executable.write_bytes(executable.read_bytes() + b"\nsynthetic signature timestamp: initial")
    runtime["files"] = runtime_inventory(resources / "runtime")
    (resources / "build-report.json").write_text(json.dumps(report))
    return report


def candidate(controller, monkeypatch, version, signature):
    monkeypatch.setattr(desktop, "__version__", version)
    (controller.resources / "source/pyproject.toml").write_text(f'[project]\nname="mia-personal-ai"\nversion="{version}"\n')
    report_file = controller.resources / "build-report.json"
    report = json.loads(report_file.read_text())
    executable = controller.resources / "runtime/bin/python3"
    executable.write_text("synthetic runtime; never execute\nsynthetic signature timestamp: " + signature)
    report["runtime_provenance"]["files"] = runtime_inventory(controller.resources / "runtime")
    report["files"] = {"Contents/Resources/source/" + key: value for key, value in runtime_inventory(controller.resources / "source").items()}
    report_file.write_text(json.dumps(report))


@pytest.fixture
def signed_installation(bundle, monkeypatch):
    resources, home = bundle
    signed_report(resources)
    darwin(monkeypatch)
    controller = DesktopController(resources, home)
    plan = controller.handle("local_plan", {})
    mock_install_worker(controller, monkeypatch)
    original = controller.handle("local_install", {"approve_sha256": plan["sha256"]})
    controller.handle("local_stop", {})
    data = controller.root / "data/initial"
    monkeypatch.setenv("MIA_DATA_DIR", str(data))
    db.initialize()
    with closing(db.connect()) as database:
        database.execute("INSERT INTO owner(id,name,email,timezone,password_hash,created_at) VALUES(1,'Synthetic','synthetic@example.test','UTC','synthetic','now')")
    (data / "approved-note.md").write_text("Synthetic context retained through two re-signed app updates")
    return controller, original


def test_two_resigned_updates_keep_original_runtime_and_sqlite_snapshots(signed_installation, monkeypatch):
    controller, original = signed_installation
    configuration_before = (controller.root / "installation.json").read_bytes()
    configuration = json.loads(configuration_before)
    stable = Path(configuration["python"]).parent.parent
    actual_inventory = runtime_inventory(stable)
    old_bundle = json.loads(controller.journal.read_text())["bundle"]
    assert old_bundle["runtime_origin"]["original_files_sha256"] != old_bundle["runtime_sha256"]
    calls = []
    def release(manager, source, wheelhouse=None, offline=False):
        assert source == controller.resources / "source" and offline
        directory = manager.root / "releases" / ("candidate-" + str(len(calls)))
        directory.mkdir()
        return {"release": str(directory.relative_to(manager.root)), "version": desktop.__version__}
    monkeypatch.setattr(Manager, "_release", release)
    monkeypatch.setattr(Manager, "_start", lambda *_args, **_kwargs: None)
    def run(command, **kwargs):
        calls.append(command)
        assert command[0] == configuration["python"]
        assert command[1:3] == ["-I", "-B"]
        assert command[3] == str(controller.root / "manager.py")
        assert "MIA_AI_API_KEY" not in kwargs["env"]
        Manager(controller.root).update(controller.resources / "source", wheelhouse=controller.resources / "wheelhouse", offline=True)
    monkeypatch.setattr(subprocess, "run", run)
    for number, version in enumerate(("0.2.0a99", "0.2.0a100"), 1):
        candidate(controller, monkeypatch, version, str(number))
        plan = controller.handle("local_bundle_plan", {})
        assert plan["update_available"]
        assert plan["details"]["bundle"]["runtime_sha256"] != old_bundle["runtime_sha256"]
        assert plan["details"]["installed_runtime"]["runtime_sha256"] == old_bundle["runtime_sha256"]
        assert plan["details"]["runtime"] == str(stable)
        result = controller.handle("local_bundle_update", {"approve_sha256": plan["sha256"]})
        assert result["version"] == version and result["paused"]
        assert result["installation_id"] == original["installation_id"]
        journal = json.loads(controller.journal.read_text())
        assert journal["bundle"]["version"] == version
        assert journal["installed_runtime"]["runtime_sha256"] == old_bundle["runtime_sha256"]
        assert journal["installed_runtime"]["runtime_origin"] == old_bundle["runtime_origin"]
        assert runtime_inventory(stable) == actual_inventory
        assert (controller.root / "installation.json").read_bytes() == configuration_before
        assert list((controller.base / "runtimes").iterdir()) == [stable]
        assert (controller.root / "data/initial/approved-note.md").read_text().startswith("Synthetic context retained")
    assert len(calls) == 2
    snapshots = list((controller.root / "snapshots").iterdir())
    assert len(snapshots) == 2
    for snapshot in snapshots:
        Manager(controller.root)._verify_snapshot(str(snapshot.relative_to(controller.root)))
        assert (snapshot / "data/approved-note.md").read_text().startswith("Synthetic context retained")
        with closing(sqlite3.connect(snapshot / "data/mia.db")) as database:
            assert database.execute("SELECT name FROM owner").fetchone() == ("Synthetic",)
            assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)


@pytest.mark.parametrize("change", ["archive", "original_binary", "architecture", "python_abi", "python_relative", "transformation", "missing_proof", "signing_policy"])
def test_changed_runtime_origin_requires_explicit_runtime_migration(signed_installation, monkeypatch, change):
    controller, _ = signed_installation
    original_journal = controller.journal.read_bytes()
    candidate(controller, monkeypatch, "0.2.0a99", "changed")
    report_file = controller.resources / "build-report.json"
    report = json.loads(report_file.read_text())
    runtime = report["runtime_provenance"]
    if change == "archive":
        runtime["archive_sha256"] = "c" * 64
    elif change == "original_binary":
        runtime["source_archive_files"]["bin/python3"]["sha256"] = hashlib.sha256(b"a different original Python binary").hexdigest()
    elif change == "architecture":
        runtime["architecture"] = report["wheelhouse_provenance"]["architecture"] = "arm64"
        monkeypatch.setattr(desktop.platform, "machine", lambda: "arm64")
    elif change == "python_abi":
        runtime["python_version"] = report["wheelhouse_provenance"]["python_version"] = "3.13"
    elif change == "python_relative":
        executable = controller.resources / "runtime/bin/python3"
        target = executable.with_name("python3.12")
        executable.rename(target)
        executable.symlink_to(target.name)
        runtime["files"] = runtime_inventory(controller.resources / "runtime")
    elif change == "transformation":
        runtime["content_transformations"] = [{"replaced_native_binary": True}]
    elif change == "missing_proof":
        del runtime["archive_sha256"]
    elif change == "signing_policy":
        runtime["python_entitlements"] = {}
    report_file.write_text(json.dumps(report))
    with pytest.raises(DesktopError) as error:
        controller.handle("local_bundle_plan", {})
    assert error.value.code == "runtime_upgrade_required"
    assert controller.journal.read_bytes() == original_journal
    assert list((controller.root / "snapshots").iterdir()) == []


def test_resigned_candidate_never_authenticates_mutated_private_runtime(signed_installation, monkeypatch):
    controller, _ = signed_installation
    configuration = json.loads((controller.root / "installation.json").read_text())
    Path(configuration["python"]).write_text("private runtime was replaced unexpectedly")
    candidate(controller, monkeypatch, "0.2.0a99", "valid-new-signature")
    with pytest.raises(DesktopError) as error:
        controller.handle("local_bundle_plan", {})
    assert error.value.code == "runtime_changed"


def test_resigned_candidate_approval_binds_new_app_and_existing_runtime(signed_installation, monkeypatch):
    controller, _ = signed_installation
    candidate(controller, monkeypatch, "0.2.0a99", "first")
    plan = controller.handle("local_bundle_plan", {})
    before = controller.journal.read_bytes()
    candidate(controller, monkeypatch, "0.2.0a99", "second")
    with pytest.raises(DesktopError) as error:
        controller.handle("local_bundle_update", {"approve_sha256": plan["sha256"]})
    assert error.value.code == "approval_changed"
    assert controller.journal.read_bytes() == before
    assert list((controller.root / "snapshots").iterdir()) == []


def test_legacy_without_recorded_origin_refuses_changed_signature(signed_installation, monkeypatch):
    controller, _ = signed_installation
    state = json.loads(controller.journal.read_text())
    del state["bundle"]["runtime_origin"]
    del state["bundle"]["python_version"]
    _write(controller.journal, state)
    candidate(controller, monkeypatch, "0.2.0a99", "new-signature")
    with pytest.raises(DesktopError) as error:
        controller.handle("local_bundle_plan", {})
    assert error.value.code == "runtime_upgrade_required"


def test_legacy_identical_bytes_remains_compatible(signed_installation, monkeypatch):
    controller, _ = signed_installation
    state = json.loads(controller.journal.read_text())
    del state["bundle"]["runtime_origin"]
    del state["bundle"]["python_version"]
    _write(controller.journal, state)
    plan = controller.handle("local_bundle_plan", {})
    assert plan["update_available"] is False
    assert plan["details"]["installed_runtime"]["runtime_sha256"] == plan["details"]["bundle"]["runtime_sha256"]
