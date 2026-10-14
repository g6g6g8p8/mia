"""Native artifact boundary tests; fixture bytes are never claimed Mac builds."""
from __future__ import annotations

import io
import json
from pathlib import Path
import plistlib
import struct
import tarfile

import pytest

from mia.operations import OperationError
from scripts import package_macos, prepare_macos_artifacts


def fixtures(tmp_path, architecture="arm64"):
    runtime = tmp_path / "runtime"
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin/python3").write_text("never executed runtime fixture")
    (runtime / "bin/python3").chmod(0o755)
    wheels = tmp_path / "wheelhouse"
    wheels.mkdir()
    (wheels / "fixture-1.0-py3-none-any.whl").write_bytes(b"never installed wheel fixture")
    common = {"format": 1, "platform": "macos", "architecture": architecture, "python_version": "3.12"}
    runtime_manifest, wheel_manifest = tmp_path / "runtime.json", tmp_path / "wheelhouse.json"
    runtime_manifest.write_text(json.dumps({**common, "source_url": "https://github.com/astral-sh/python-build-standalone/releases/download/reviewed/runtime.tar.gz", "files": package_macos.inventory(runtime)}))
    wheel_manifest.write_text(json.dumps({**common, "source_url": "https://pypi.org/simple/", "files": package_macos.inventory(wheels)}))
    return runtime, runtime_manifest, wheels, wheel_manifest


def thin_macho(path, architecture="arm64", *, minimum=13, platform=1):
    cpu = {"arm64": 0x0100000C, "x86_64": 0x01000007}[architecture]
    header = struct.pack("<8I", 0xFEEDFACF, cpu, 0, 2, 1, 24, 0, 0)
    command = struct.pack("<6I", 0x32, 24, platform, minimum << 16, 15 << 16, 0)
    path.write_bytes(header + command)
    path.chmod(0o755)
    return path


def test_native_mode_is_actual_binary_with_versioned_contract_and_private_inputs_excluded(tmp_path):
    inputs = fixtures(tmp_path)
    binary = thin_macho(tmp_path / "Mia")
    output = tmp_path / "Mia.app"
    result = package_macos.build(output, *inputs, native_binary=binary)
    resources = output / "Contents/Resources"
    assert (output / "Contents/MacOS/Mia").read_bytes() == binary.read_bytes()
    assert result["entrypoint"] == "native-swift"
    assert not result["signed"] and not result["validated_on_macos"]
    assert (resources / "desktop_bridge.py").read_bytes() == (package_macos.REPOSITORY / "scripts/desktop_bridge.py").read_bytes()
    assert not (resources / "launcher.py").exists()
    contract = json.loads((resources / "desktop-contract.json").read_text())
    assert contract["protocol"] == 1 and contract["app_version"] == result["app_version"]
    info = plistlib.loads((output / "Contents/Info.plist").read_bytes())
    assert info["LSMinimumSystemVersion"] == "13.0"
    assert info["MiaBackendVersion"] == result["app_version"]
    assert not info["SUEnableAutomaticChecks"] and "SUFeedURL" not in info
    assert not (resources / "source/.git").exists()


@pytest.mark.parametrize("minimum,platform", [(14, 1), (13, 2)])
def test_native_binary_must_support_offered_macos(tmp_path, minimum, platform):
    inputs = fixtures(tmp_path)
    binary = thin_macho(tmp_path / "Mia", minimum=minimum, platform=platform)
    with pytest.raises(OperationError, match="macOS"):
        package_macos.build(tmp_path / "Mia.app", *inputs, native_binary=binary)
    assert not (tmp_path / "Mia.app").exists()


def test_native_binary_architecture_and_truncated_commands_rejected_before_writes(tmp_path):
    inputs = fixtures(tmp_path)
    binary = thin_macho(tmp_path / "Mia", "x86_64")
    with pytest.raises(OperationError, match="arquitetura"):
        package_macos.build(tmp_path / "Mia.app", *inputs, native_binary=binary)
    binary.write_bytes(binary.read_bytes()[:-1])
    with pytest.raises(OperationError, match="truncados"):
        package_macos.macho_architecture(binary)


def test_framework_links_resources_and_xpc_are_preserved(tmp_path):
    inputs = fixtures(tmp_path)
    binary = thin_macho(tmp_path / "Mia")
    framework = tmp_path / "Sparkle.framework"
    version = framework / "Versions/B"
    version.mkdir(parents=True)
    (version / "Sparkle").write_bytes(b"synthetic framework executable not used")
    helper = version / "XPCServices/Downloader.xpc/Contents/MacOS"
    helper.mkdir(parents=True)
    (helper / "Downloader").write_bytes(b"synthetic XPC not used")
    (framework / "Versions/Current").symlink_to("B")
    (framework / "Sparkle").symlink_to("Versions/Current/Sparkle")
    output = tmp_path / "Mia.app"
    package_macos.build(output, *inputs, native_binary=binary, sparkle_framework=framework)
    bundled = output / "Contents/Frameworks/Sparkle.framework"
    assert (bundled / "Sparkle").is_symlink()
    assert (bundled / "Versions/B/XPCServices/Downloader.xpc/Contents/MacOS/Downloader").read_bytes().startswith(b"synthetic")
    assert package_macos.inventory(bundled) == package_macos.inventory(framework)


def test_public_source_never_copies_private_static_database(tmp_path):
    source = tmp_path / "source"
    (source / "mia/static").mkdir(parents=True)
    (source / "mia/static/user.db").write_bytes(b"private fixture must be rejected")
    with pytest.raises(ValueError, match="private"):
        package_macos.copy_public_source(source, tmp_path / "public")


def test_runtime_extraction_refuses_traversal_without_touching_destination(tmp_path):
    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        member = tarfile.TarInfo("python/../../outside")
        member.size = 7
        stream.addfile(member, io.BytesIO(b"private"))
    with pytest.raises(OperationError, match="Caminho"):
        prepare_macos_artifacts.extract_runtime(archive, tmp_path / "runtime")
    assert not (tmp_path / "outside").exists()
    assert not (tmp_path / "runtime").exists()
    assert not (tmp_path / "runtime-extracting").exists()


def test_download_does_not_replace_mutated_cached_payload_or_trust_fresh_checksum(tmp_path, monkeypatch):
    artifact = tmp_path / "python.tar.gz"
    artifact.write_bytes(b"mutated cached payload")
    monkeypatch.setattr(prepare_macos_artifacts.urllib.request, "build_opener", lambda *args: pytest.fail("should not download over mutated cache"))
    with pytest.raises(OperationError, match="hash fixado"):
        prepare_macos_artifacts.download("https://github.com/astral-sh/python-build-standalone/releases/download/reviewed/runtime.tar.gz", artifact, "a" * 64)
    assert artifact.read_bytes() == b"mutated cached payload"


def test_target_preparation_never_executes_cross_platform_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare_macos_artifacts.platform, "system", lambda: "Linux")
    monkeypatch.setattr(prepare_macos_artifacts.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(prepare_macos_artifacts.subprocess, "run", lambda *args, **kwargs: pytest.fail("cross-platform runtime executed"))
    with pytest.raises(OperationError, match="nativos"):
        prepare_macos_artifacts.prepare(tmp_path / "build", "macos", "arm64", tmp_path / "cache")
    assert not (tmp_path / "build").exists()


def test_macos_wheel_requires_supported_minimum_os(tmp_path):
    inputs = fixtures(tmp_path)
    wheels, manifest = inputs[2:]
    (wheels / "fixture-1.0-py3-none-any.whl").unlink()
    (wheels / "fixture-1.0-cp312-cp312-macosx_14_0_arm64.whl").write_bytes(b"newer-OS fixture")
    data = json.loads(manifest.read_text())
    data["files"] = package_macos.inventory(wheels)
    manifest.write_text(json.dumps(data))
    with pytest.raises(OperationError, match="compatível"):
        package_macos.build(tmp_path / "Mia.app", *inputs, native_binary=thin_macho(tmp_path / "Mia"))
