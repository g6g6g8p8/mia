#!/usr/bin/env python3
"""Build unsigned Mac launcher inputs from explicitly verified offline artifacts.

No download/build of Python, host-service activation, signing identity, network
or private data is inferred. Manifests must come from trusted build provenance;
hashes detect mutation, not the authenticity of a caller-supplied manifest.
Produce separate arm64/x86_64 artifacts with matching standalone runtime/wheels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tomllib
import urllib.parse

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))
from mia.operations import OperationError


def inventory(directory: Path) -> dict:
    result = {}
    if directory.is_symlink() or not directory.is_dir():
        raise OperationError("Artefatos exigem diretório real")
    for path in sorted(directory.rglob("*")):
        relative = str(path.relative_to(directory))
        if path.is_symlink():
            link = os.readlink(path)
            if Path(link).is_absolute() or not path.resolve().is_relative_to(directory.resolve()) or not path.resolve().exists():
                raise OperationError("Link de runtime aponta para fora ou está quebrado")
            result[relative] = {"symlink": link}
        elif path.is_file():
            with path.open("rb") as file:
                result[relative] = {"sha256": hashlib.file_digest(file, "sha256").hexdigest(), "executable": bool(path.stat().st_mode & 0o111)}
        elif not path.is_dir():
            raise OperationError("Artefato especial não suportado")
    return result


def verify(directory: Path, manifest: Path, *, runtime: bool) -> dict:
    if manifest.is_symlink() or not manifest.is_file():
        raise OperationError("Manifesto de proveniência deve ser arquivo regular")
    data = json.loads(manifest.read_text())
    origin = urllib.parse.urlsplit(data.get("source_url", ""))
    if origin.scheme != "https" or origin.username or origin.password or origin.fragment or origin.query:
        raise OperationError("Proveniência exige URL HTTPS sem credenciais")
    allowed = (origin.hostname == "www.python.org" or origin.hostname == "python.org" or
               origin.hostname == "github.com" and origin.path.startswith("/astral-sh/python-build-standalone/")) if runtime else origin.hostname in ("pypi.org", "files.pythonhosted.org")
    if not allowed or data.get("format") != 1 or data.get("files") != inventory(directory):
        raise OperationError("Origem ou hashes de artefatos não correspondem à proveniência revisada")
    if runtime and (data.get("platform") != "macos" or data.get("architecture") not in ("arm64", "x86_64") or data.get("python_version") not in ("3.12", "3.13")):
        raise OperationError("Runtime deve identificar Python 3.12/3.13 standalone macOS e arquitetura")
    return data


def copy_public_source(source: Path, public: Path) -> None:
    """The bundle/remote companion receives only reviewed public inputs."""
    from scripts.check_distribution import safe_member
    public.mkdir()
    for name in ("pyproject.toml", "requirements.lock", "README.md", "MANIFEST.in", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        path = source / name
        if path.exists():
            if path.is_symlink() or not path.is_file():
                raise OperationError("Fonte pública contém arquivo não regular")
            safe_member(name, path.read_bytes())
            shutil.copyfile(path, public / name)
    notices = source / "THIRD_PARTY_LICENSES"
    if notices.exists():
        from mia.operations import _copy_private
        _copy_private(notices, public / notices.name)
    for path in (source / "mia").rglob("*"):
        relative = path.relative_to(source / "mia")
        if path.is_symlink():
            raise OperationError("Fonte do pacote contém link simbólico")
        if path.is_file() and "__pycache__" not in relative.parts and (path.suffix == ".py" or relative.parts[0] == "static"):
            safe_member("mia/" + relative.as_posix(), path.read_bytes())
            target = public / "mia" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def source_provenance(source: Path, copied_source: Path) -> dict:
    files = inventory(copied_source)
    revision, clean = None, False
    try:
        candidate = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
        if re.fullmatch(r"[0-9a-f]{40}", candidate):
            revision = candidate
            clean = not subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        pass
    return {"revision": revision, "clean_checkout": clean, "files_sha256": hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "files": files}


def validate_remote_artifact(artifact: Path) -> dict:
    if artifact.is_symlink() or not artifact.is_dir():
        raise OperationError("Companheiro remoto exige diretório regular")
    manifest = artifact / "manifest.json"
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 16 * 1024 * 1024:
        raise OperationError("Manifesto remoto inválido")
    data = json.loads(manifest.read_text())
    payload = artifact / "payload"
    if data.get("format") != 1 or data.get("platform") != "ubuntu24.04" or data.get("architecture") != "amd64" or data.get("python_version") != "3.12" or data.get("files") != inventory(payload):
        raise OperationError("Companheiro remoto não corresponde aos hashes/alvo revisados")
    if set(path.name for path in payload.iterdir()) != {"runtime", "wheelhouse", "source"}:
        raise OperationError("Companheiro remoto inclui arquivos inesperados")
    for relative in data["files"]:
        if "symlink" in data["files"][relative] and not relative.startswith("runtime/"):
            raise OperationError("Somente runtime pode incluir links seguros")
    for key, folder, hosts in (("runtime_provenance", "runtime", {"github.com"}), ("wheelhouse_provenance", "wheelhouse", {"pypi.org", "files.pythonhosted.org"})):
        provenance = data.get(key, {})
        parsed = urllib.parse.urlsplit(provenance.get("source_url", ""))
        if parsed.scheme != "https" or parsed.hostname not in hosts or parsed.username or parsed.password or parsed.query or parsed.fragment or provenance.get("platform") != "linux" or provenance.get("architecture") != "x86_64" or provenance.get("files") != inventory(payload / folder):
            raise OperationError("Proveniência remota inválida")
        if key == "runtime_provenance" and not parsed.path.startswith("/astral-sh/python-build-standalone/releases/download/"):
            raise OperationError("Runtime remoto exige origem oficial standalone")
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "pyproject.toml", "requirements.lock", "mia/operations.py"):
        if not (payload / "source" / name).is_file():
            raise OperationError("Companheiro remoto sem fonte/avisos obrigatórios")
    return data


def macho_architecture(binary: Path, *, maximum_macos: int = 13) -> str:
    """Validate the thin release executable without executing caller input.

    Build one app per architecture. Universal/fat files and Linux fixtures are
    deliberately not accepted as an actual native Mac app.
    """
    if binary.is_symlink() or not binary.is_file() or not binary.stat().st_mode & 0o111:
        raise OperationError("Aplicativo nativo exige binário Mach-O executável regular")
    with binary.open("rb") as stream:
        header = stream.read(32)
        if len(header) != 32 or header[:4] != b"\xcf\xfa\xed\xfe":
            raise OperationError("Aplicativo nativo exige Mach-O 64-bit por arquitetura")
        _, cpu, _, kind, count, size, _, _ = struct.unpack("<8I", header)
        architecture = {0x0100000C: "arm64", 0x01000007: "x86_64"}.get(cpu)
        if architecture is None or kind != 2 or count > 4096 or size > 2 * 1024 * 1024:
            raise OperationError("Arquitetura ou comandos Mach-O não suportados")
        commands = stream.read(size)
    if len(commands) != size:
        raise OperationError("Comandos Mach-O truncados")
    offset, minimum = 0, None
    for _ in range(count):
        if offset + 8 > len(commands):
            raise OperationError("Comandos Mach-O inválidos")
        command, length = struct.unpack_from("<2I", commands, offset)
        if length < 8 or offset + length > len(commands):
            raise OperationError("Comandos Mach-O inválidos")
        if command == 0x32:  # LC_BUILD_VERSION
            if length < 24:
                raise OperationError("Versão Mach-O inválida")
            platform, minimum = struct.unpack_from("<2I", commands, offset + 8)
            if platform != 1:
                raise OperationError("Binário Mach-O não é destinado ao macOS")
        elif command == 0x24:  # LC_VERSION_MIN_MACOSX
            if length < 16:
                raise OperationError("Versão Mach-O inválida")
            minimum = struct.unpack_from("<I", commands, offset + 8)[0]
        offset += length
    if offset != size or minimum is None or minimum > maximum_macos << 16:
        raise OperationError("Binário exige versão de macOS superior à oferecida")
    return architecture


def build(output: Path, runtime: Path, runtime_manifest: Path, wheelhouse: Path, wheelhouse_manifest: Path, source: Path = REPOSITORY, *, native_binary: Path | None = None, release_channel: Path | None = None, sparkle_framework: Path | None = None, remote_artifact: Path | None = None) -> dict:
    runtime_data = verify(runtime, runtime_manifest, runtime=True)
    wheel_data = verify(wheelhouse, wheelhouse_manifest, runtime=False)
    if wheel_data.get("architecture") != runtime_data["architecture"] or wheel_data.get("python_version") != runtime_data["python_version"] or wheel_data.get("platform") != "macos":
        raise OperationError("Wheelhouse não corresponde à plataforma/arquitetura/Python do runtime")
    if native_binary is not None and macho_architecture(native_binary) != runtime_data["architecture"]:
        raise OperationError("Aplicativo nativo não corresponde à arquitetura do runtime")
    remote_data = validate_remote_artifact(remote_artifact) if remote_artifact is not None else None
    if sparkle_framework is not None:
        if native_binary is None or sparkle_framework.name != "Sparkle.framework" or not sparkle_framework.is_dir():
            raise OperationError("Sparkle exige framework nativo revisado")
        framework_files = inventory(sparkle_framework)
        if not (sparkle_framework / "Sparkle").is_file() or not (source / "THIRD_PARTY_LICENSES/native-sparkle-2.10.0--LICENSE").is_file():
            raise OperationError("Sparkle framework exige executável e licença preservada na fonte")
    if not list(wheelhouse.iterdir()) or any(path.suffix != ".whl" or path.is_symlink() or not path.is_file() for path in wheelhouse.iterdir()):
        raise OperationError("Wheelhouse aceita somente wheels regulares offline")
    python_tag = "cp" + runtime_data["python_version"].replace(".", "")
    for wheel in wheelhouse.iterdir():
        parts = wheel.name[:-4].split("-")
        if len(parts) < 5:
            raise OperationError("Nome de wheel inválido")
        tags, abi, platform = parts[-3:]
        pure = platform == "any" and abi == "none" and any(tag in ("py3", "py2.py3", python_tag) for tag in tags.split("."))
        platform_tags = platform.split(".")
        mac = any(re.fullmatch(r"macosx_([0-9]+)_([0-9]+)_(?:" + runtime_data["architecture"] + r"|universal2)", tag) and int(tag.split("_")[1]) <= 13 for tag in platform_tags)
        stable_abi = abi == "abi3" and any(re.fullmatch(r"cp3[0-9]+", tag) and int(tag[3:]) <= int(runtime_data["python_version"].split(".")[1]) for tag in tags.split("."))
        native_abi = python_tag in tags.split(".") and abi in (python_tag, "none", "abi3")
        if not pure and not (mac and (native_abi or stable_abi)):
            raise OperationError("Wheel não compatível com Python/macOS/arquitetura declarados")
    if output.exists() or output.is_symlink() or output.suffix != ".app":
        raise OperationError("Use uma pasta .app nova; nenhum artefato será substituído")
    python = runtime / "bin/python3"
    if not python.is_file() or not python.stat().st_mode & 0o111:
        raise OperationError("Runtime exige bin/python3 executável")
    resources = output / "Contents/Resources"
    executable = output / "Contents/MacOS"
    resources.mkdir(parents=True)
    executable.mkdir()
    try:
        shutil.copytree(runtime, resources / "runtime", symlinks=True)
        shutil.copytree(wheelhouse, resources / "wheelhouse")
        public = resources / "source"
        copy_public_source(source, public)
        if remote_artifact is not None:
            if remote_data.get("version") != tomllib.loads((source / "pyproject.toml").read_text())["project"]["version"]:
                raise OperationError("Companheiro remoto difere da versão do aplicativo")
            shutil.copytree(remote_artifact, resources / "remote-runtime", symlinks=True)
            validate_remote_artifact(resources / "remote-runtime")
        if sparkle_framework is not None:
            frameworks = output / "Contents/Frameworks"
            frameworks.mkdir()
            shutil.copytree(sparkle_framework, frameworks / "Sparkle.framework", symlinks=True)
        entry = executable / "Mia"
        version = tomllib.loads((source / "pyproject.toml").read_text())["project"]["version"]
        if native_binary is not None:
            bridge = source / "scripts/desktop_bridge.py"
            if bridge.is_symlink() or not bridge.is_file():
                raise OperationError("Aplicativo nativo exige bridge revisado no pacote fonte")
            shutil.copyfile(bridge, resources / "desktop_bridge.py")
            shutil.copyfile(native_binary, entry)
            (resources / "desktop-contract.json").write_text(json.dumps({"protocol": 1, "app_version": version, "minimum_macos": "13.0"}, indent=2))
        else:
            launcher = resources / "launcher.py"
            launcher.write_text('from pathlib import Path\nimport sys\nresources = Path(__file__).resolve().parent\nsys.path.insert(0, str(resources / "source"))\nfrom mia.launcher import main, dialog\ntry:\n    main(resources)\nexcept Exception:\n    dialog("Mia não conseguiu concluir a operação. Seus dados foram preservados. Revise o log privado e o plano; não repita instalações nem apague dados.")\n')
            entry.write_text('#!/bin/sh\nbase=$(CDPATH= cd -- "$(dirname -- "$0")/../Resources" && pwd) || exit 1\nexec "$base/runtime/bin/python3" -I "$base/launcher.py"\n')
        entry.chmod(0o755)
        channel = {}
        if release_channel is not None:
            if release_channel.is_symlink() or not release_channel.is_file() or release_channel.stat().st_size > 64 * 1024:
                raise OperationError("Configuração do canal de atualização inválida")
            from mia.updates import validate_channel
            channel = json.loads(release_channel.read_text())
            validate_channel(channel)
            (resources / "release-channel.json").write_text(json.dumps(channel, indent=2))
        info = {"CFBundleIdentifier": "org.mia.demo" if native_binary else "local.mia.launcher", "CFBundleName": "Mia", "CFBundleDisplayName": "Mia", "CFBundleExecutable": "Mia", "CFBundlePackageType": "APPL", "CFBundleVersion": version.replace("a", "."), "CFBundleShortVersionString": version.split("a")[0], "MiaBackendVersion": version, "LSMinimumSystemVersion": "13.0" if native_binary else "12.0", "NSHighResolutionCapable": True, "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True}, "SUEnableAutomaticChecks": False, "SUAutomaticallyUpdate": False}
        if channel.get("appcast_url") and channel.get("sparkle_public_key"):
            if sparkle_framework is None:
                raise OperationError("Canal de aplicativo exige Sparkle framework revisado")
            info.update({"SUFeedURL": channel["appcast_url"], "SUPublicEDKey": channel["sparkle_public_key"]})
        (output / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
        report = {"format": 1, "signed": False, "notarized": False, "validated_on_macos": False,
                  "app_version": version, "desktop_protocol": 1 if native_binary else None,
                  "entrypoint": "native-swift" if native_binary else "legacy-browser-launcher",
                  "remote_platform": "ubuntu24.04-amd64" if remote_data else None,
                  "sparkle_bundled": sparkle_framework is not None,
                  "source_provenance": source_provenance(source, public),
                  "architecture": runtime_data["architecture"], "runtime_provenance": runtime_data,
                  "wheelhouse_provenance": wheel_data,
                  "external_gates": ["license/attribution review", "compatible runtime + wheel installation on clean Mac", "codesign/notarization", "login/sleep/resume/update/restore acceptance"],
                  "files": inventory(output)}
        (resources / "build-report.json").write_text(json.dumps(report, indent=2))
        return {"output": str(output), "architecture": runtime_data["architecture"], "entrypoint": report["entrypoint"], "app_version": version, "signed": False, "notarized": False, "validated_on_macos": False}
    except BaseException:
        shutil.rmtree(output)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "runtime", "runtime-manifest", "wheelhouse", "wheelhouse-manifest"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--native-binary", type=Path)
    parser.add_argument("--release-channel", type=Path, help="Reviewed public update-channel configuration; never a private signing key")
    parser.add_argument("--sparkle-framework", type=Path)
    parser.add_argument("--remote-artifact", type=Path, help="Verified Ubuntu 24.04 amd64 offline companion directory")
    args = vars(parser.parse_args())
    try:
        print(json.dumps(build(**args), indent=2))
    except (OperationError, OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
