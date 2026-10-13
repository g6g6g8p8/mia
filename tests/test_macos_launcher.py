"""Portable Mac artifact/launcher contracts; no claims of actual Mac validation."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from mia.launcher import install_bundled, remote_url, runtime_inventory
from mia.operations import Manager, OperationError
from scripts import package_macos


@pytest.mark.parametrize("value", ["http://example.test", "https://user:password@example.test", "https://example.test/token", "https://example.test/?key=x", "https://example.test/#x", "https://example.test\\@evil.test", "https://bad%20host.test", "https://-host.test", "https://example.test:70000", "https://example.test\n"])
def test_remote_client_rejects_unsafe_urls(value):
    with pytest.raises(OperationError):
        remote_url(value)


def test_remote_client_only_opens_existing_https_origin():
    assert remote_url("https://mia.example.test") == "https://mia.example.test/"
    assert remote_url("https://[::1]:8443/") == "https://[::1]:8443/"


def artifacts(tmp_path):
    runtime = tmp_path / "python"
    (runtime / "bin").mkdir(parents=True)
    python = runtime / "bin/python3"
    python.write_text("synthetic build fixture; never executed")
    python.chmod(0o755)
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    (wheels / "synthetic-1.0-py3-none-any.whl").write_bytes(b"synthetic never installed")
    provenance = {"format": 1, "platform": "macos", "architecture": "arm64", "python_version": "3.12"}
    runtime_manifest = tmp_path / "runtime.json"
    runtime_manifest.write_text(json.dumps({**provenance, "source_url": "https://github.com/astral-sh/python-build-standalone/releases/download/reviewed/python.tar.gz", "files": package_macos.inventory(runtime)}))
    wheel_manifest = tmp_path / "wheels.json"
    wheel_manifest.write_text(json.dumps({**provenance, "source_url": "https://pypi.org/simple/", "files": package_macos.inventory(wheels)}))
    return runtime, runtime_manifest, wheels, wheel_manifest


def test_macos_bundle_is_offline_private_input_free_and_truthfully_unsigned(tmp_path):
    inputs = artifacts(tmp_path)
    output = tmp_path / "Mia.app"
    result = package_macos.build(output, *inputs)
    assert not result["signed"] and not result["validated_on_macos"]
    resources = output / "Contents/Resources"
    assert (resources / "runtime/bin/python3").exists()
    assert (resources / "source/mia/launcher.py").exists()
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        assert (resources / "source" / name).read_bytes() == (package_macos.REPOSITORY / name).read_bytes()
    assert not (resources / "source/.git").exists()
    assert not (resources / "source/data").exists()
    assert not (resources / "source/.env").exists()
    assert "runtime/bin/python3" in (output / "Contents/MacOS/Mia").read_text()
    assert "notarization" in json.dumps(json.loads((resources / "build-report.json").read_text()))
    with pytest.raises(OperationError, match="nenhum.*substituído"):
        package_macos.build(output, *inputs)


def test_bundled_runtime_installs_at_stable_private_path_without_user_python(tmp_path, monkeypatch):
    inputs = artifacts(tmp_path)
    output = tmp_path / "Mia.app"
    package_macos.build(output, *inputs)
    resources = output / "Contents/Resources"
    base = tmp_path / "application-support"
    base.mkdir()
    manager = Manager(base / "installation")
    commands = []
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: commands.append(command))
    install_bundled(manager, resources)
    assert commands[0][0] == str(base / "runtime/bin/python3")
    assert "--offline" in commands[0]
    assert runtime_inventory(base / "runtime") == package_macos.inventory(inputs[0])
    assert (base / "runtime").stat().st_mode & 0o077 == 0
    (base / "runtime/bin/python3").write_text("tampered existing runtime")
    with pytest.raises(OperationError, match="não foi sobrescrito"):
        install_bundled(manager, resources)


def test_macos_builder_rejects_hash_mutation_arch_mismatch_and_escape(tmp_path):
    inputs = artifacts(tmp_path)
    runtime, runtime_manifest, wheels, wheel_manifest = inputs
    (runtime / "bin/python3").write_text("mutation")
    with pytest.raises(OperationError, match="hashes"):
        package_macos.build(tmp_path / "Mia.app", *inputs)
    data = json.loads(runtime_manifest.read_text())
    data["files"] = package_macos.inventory(runtime)
    runtime_manifest.write_text(json.dumps(data))
    data = json.loads(wheel_manifest.read_text())
    data["architecture"] = "x86_64"
    wheel_manifest.write_text(json.dumps(data))
    with pytest.raises(OperationError, match="não corresponde"):
        package_macos.build(tmp_path / "Mia.app", *inputs)
    (runtime / "escape").symlink_to("/etc/passwd")
    with pytest.raises(OperationError, match="fora"):
        package_macos.inventory(runtime)


