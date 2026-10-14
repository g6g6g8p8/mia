"""Native artifact boundary tests; fixture bytes are never claimed Mac builds."""
from __future__ import annotations

import io
import json
from pathlib import Path
import plistlib
import shutil
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


def test_linux_terminal_alias_trim_happens_before_case_insensitive_extraction_and_preserves_python(tmp_path, monkeypatch):
    archive = tmp_path / "linux-runtime.tar.gz"
    python_bytes, terminfo_bytes = b"synthetic Python executable; never run", b"optional terminal metadata"
    with tarfile.open(archive, "w:gz") as stream:
        for name in ("python", "python/bin", "python/share", "python/share/terminfo", "python/share/terminfo/N", "python/share/terminfo/n"):
            member = tarfile.TarInfo(name)
            member.type = tarfile.DIRTYPE
            stream.addfile(member)
        for name, content in (("python/bin/python3", python_bytes), ("python/share/terminfo/n/ncr260vt300wpp", terminfo_bytes)):
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(content), 0o755
            stream.addfile(member, io.BytesIO(content))
        alias = tarfile.TarInfo("python/share/terminfo/N/NCR260VT300WPP")
        alias.type, alias.linkname = tarfile.SYMTYPE, "../n/ncr260vt300wpp"
        stream.addfile(alias)
    original_extractall = tarfile.TarFile.extractall
    def case_insensitive_extractall(self, path, *, members, filter):
        names = [member.name.casefold() for member in members]
        if len(set(names)) != len(names):
            raise OSError(62, "Too many levels of symbolic links on a case-insensitive fixture")
        return original_extractall(self, path, members=members, filter=filter)
    monkeypatch.setattr(tarfile.TarFile, "extractall", case_insensitive_extractall)
    with pytest.raises(OSError, match="symbolic links"):
        prepare_macos_artifacts.extract_runtime(archive, tmp_path / "untrimmed")
    transformation = prepare_macos_artifacts.extract_runtime(archive, tmp_path / "normalized", omit_linux_terminfo=True)
    assert (tmp_path / "normalized/bin/python3").read_bytes() == python_bytes
    assert not (tmp_path / "normalized/share/terminfo").exists()
    assert transformation[0]["archive_prefix"] == "python/share/terminfo"
    assert transformation[0]["excluded_member_count"] == 5
    assert transformation[0]["excluded_file_bytes"] == len(terminfo_bytes)
    assert len(transformation[0]["excluded_member_index_sha256"]) == 64
    # Independently extracting for origin verification yields identical bytes
    # and the same original-member index, regardless of host case sensitivity.
    repeated = prepare_macos_artifacts.extract_runtime(archive, tmp_path / "verification", omit_linux_terminfo=True)
    assert repeated == transformation
    assert package_macos.inventory(tmp_path / "verification") == package_macos.inventory(tmp_path / "normalized")


def test_linux_optional_trim_does_not_hide_archive_traversal(tmp_path):
    archive = tmp_path / "unsafe-terminal-path.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        member = tarfile.TarInfo("python/share/terminfo/../../../../outside")
        member.size = 7
        stream.addfile(member, io.BytesIO(b"private"))
    with pytest.raises(OperationError, match="Caminho"):
        prepare_macos_artifacts.extract_runtime(archive, tmp_path / "runtime", omit_linux_terminfo=True)
    assert not (tmp_path / "outside").exists()
    assert not (tmp_path / "runtime").exists()


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


def test_prepared_runtime_is_checked_against_pinned_origin_even_with_self_consistent_manifest(tmp_path, monkeypatch):
    source = tmp_path / "source"
    (source / "scripts").mkdir(parents=True)
    (source / "requirements.lock").write_text("fixture==1.0\n")
    trusted = tmp_path / "trusted.tar.gz"
    content = b"original reviewed runtime fixture; never executed"
    with tarfile.open(trusted, "w:gz") as stream:
        member = tarfile.TarInfo("python/bin/python3")
        member.mode, member.size = 0o755, len(content)
        stream.addfile(member, io.BytesIO(content))
    sha = prepare_macos_artifacts.digest(trusted)
    lock = {"release": "reviewed", "targets": {"linux-x86_64": {"archive": "runtime.tar.gz", "sha256": sha, "license_archive": "notices.tar.gz", "license_archive_sha256": sha, "triple": "x86_64-unknown-linux-gnu"}}}
    (source / "scripts/macos-runtime-lock.json").write_text(json.dumps(lock))
    monkeypatch.setattr(prepare_macos_artifacts, "ROOT", source)
    def cached_download(url, destination, expected):
        assert expected == sha
        destination.write_bytes(trusted.read_bytes())
    monkeypatch.setattr(prepare_macos_artifacts, "download", cached_download)
    monkeypatch.setattr(prepare_macos_artifacts, "preserve_runtime_notices", lambda *args, **kwargs: {})
    monkeypatch.setattr(prepare_macos_artifacts, "wheel_provenance", lambda *args, **kwargs: [])
    runtime = tmp_path / "prepared"
    prepare_macos_artifacts.extract_runtime(trusted, runtime)
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    prepare_macos_artifacts.verify_prepared(runtime, wheels, "linux", "x86_64", tmp_path / "cache", source=source)
    (runtime / "bin/python3").write_bytes(b"mutated payload")
    # A matching caller-generated manifest must not make mutated bytes trusted.
    (tmp_path / "self-claimed.json").write_text(json.dumps({"files": package_macos.inventory(runtime)}))
    monkeypatch.setattr(prepare_macos_artifacts.subprocess, "run", lambda *args, **kwargs: pytest.fail("artifact was executed during verification"))
    with pytest.raises(OperationError, match="bytes oficiais"):
        prepare_macos_artifacts.verify_prepared(runtime, wheels, "linux", "x86_64", tmp_path / "cache", source=source)


@pytest.mark.parametrize("source_drift", [False, True])
def test_remote_companion_must_ship_the_same_reviewed_source_even_at_the_same_version(tmp_path, source_drift):
    inputs = fixtures(tmp_path)
    binary = thin_macho(tmp_path / "Mia")
    remote = tmp_path / "remote-runtime"
    payload = remote / "payload"
    payload.mkdir(parents=True)
    shutil.copytree(inputs[0], payload / "runtime")
    shutil.copytree(inputs[2], payload / "wheelhouse")
    package_macos.copy_public_source(package_macos.REPOSITORY, payload / "source")
    if source_drift:
        with (payload / "source/mia/operations.py").open("a") as target:
            target.write("\n# Same-version source drift; never executed.\n")
    common = {"format": 1, "platform": "linux", "architecture": "x86_64", "python_version": "3.12"}
    manifest = {"format": 1, "platform": "ubuntu24.04", "architecture": "amd64", "python_version": "3.12", "version": package_macos.tomllib.loads((payload / "source/pyproject.toml").read_text())["project"]["version"], "files": package_macos.inventory(payload)}
    for folder, origin in (("runtime", "https://github.com/astral-sh/python-build-standalone/releases/download/reviewed/fixture.tar.gz"), ("wheelhouse", "https://pypi.org/simple/")):
        manifest[folder + "_provenance"] = {**common, "source_url": origin, "files": package_macos.inventory(payload / folder)}
    (remote / "manifest.json").write_text(json.dumps(manifest))
    output = tmp_path / "Mia.app"
    if source_drift:
        with pytest.raises(OperationError, match="Fonte do companheiro remoto"):
            package_macos.build(output, *inputs, native_binary=binary, remote_artifact=remote)
        assert not output.exists()
    else:
        package_macos.build(output, *inputs, native_binary=binary, remote_artifact=remote)
        assert package_macos.inventory(output / "Contents/Resources/source") == package_macos.inventory(output / "Contents/Resources/remote-runtime/payload/source")
