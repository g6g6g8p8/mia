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
import sys
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


def build(output: Path, runtime: Path, runtime_manifest: Path, wheelhouse: Path, wheelhouse_manifest: Path, source: Path = REPOSITORY) -> dict:
    runtime_data = verify(runtime, runtime_manifest, runtime=True)
    wheel_data = verify(wheelhouse, wheelhouse_manifest, runtime=False)
    if wheel_data.get("architecture") != runtime_data["architecture"] or wheel_data.get("python_version") != runtime_data["python_version"] or wheel_data.get("platform") != "macos":
        raise OperationError("Wheelhouse não corresponde à plataforma/arquitetura/Python do runtime")
    if not list(wheelhouse.iterdir()) or any(path.suffix != ".whl" or path.is_symlink() or not path.is_file() for path in wheelhouse.iterdir()):
        raise OperationError("Wheelhouse aceita somente wheels regulares offline")
    python_tag = "cp" + runtime_data["python_version"].replace(".", "")
    for wheel in wheelhouse.iterdir():
        parts = wheel.name[:-4].split("-")
        if len(parts) < 5:
            raise OperationError("Nome de wheel inválido")
        tags, abi, platform = parts[-3:]
        pure = platform == "any" and abi == "none" and any(tag in ("py3", "py2.py3", python_tag) for tag in tags.split("."))
        mac = bool(re.fullmatch(r"macosx_[0-9]+_[0-9]+_(?:" + runtime_data["architecture"] + r"|universal2)", platform))
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
        public.mkdir()
        for name in ("pyproject.toml", "requirements.lock", "README.md", "MANIFEST.in", "THIRD_PARTY_NOTICES.md"):
            path = source / name
            if path.exists():
                if path.is_symlink() or not path.is_file():
                    raise OperationError("Fonte pública contém arquivo não regular")
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
                target = public / "mia" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        launcher = resources / "launcher.py"
        launcher.write_text('from pathlib import Path\nimport sys\nresources = Path(__file__).resolve().parent\nsys.path.insert(0, str(resources / "source"))\nfrom mia.launcher import main, dialog\ntry:\n    main(resources)\nexcept Exception:\n    dialog("Mia não conseguiu concluir a operação. Seus dados foram preservados. Revise o log privado e o plano; não repita instalações nem apague dados.")\n')
        entry = executable / "Mia"
        entry.write_text('#!/bin/sh\nbase=$(CDPATH= cd -- "$(dirname -- "$0")/../Resources" && pwd) || exit 1\nexec "$base/runtime/bin/python3" -I "$base/launcher.py"\n')
        entry.chmod(0o755)
        (output / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "local.mia.launcher", "CFBundleName": "Mia", "CFBundleExecutable": "Mia", "CFBundlePackageType": "APPL", "CFBundleVersion": "1", "LSMinimumSystemVersion": "12.0"}))
        report = {"format": 1, "signed": False, "notarized": False, "validated_on_macos": False,
                  "architecture": runtime_data["architecture"], "runtime_provenance": runtime_data,
                  "wheelhouse_provenance": wheel_data,
                  "external_gates": ["license/attribution review", "compatible runtime + wheel installation on clean Mac", "codesign/notarization", "login/sleep/resume/update/restore acceptance"],
                  "files": inventory(output)}
        (resources / "build-report.json").write_text(json.dumps(report, indent=2))
        return {"output": str(output), "architecture": runtime_data["architecture"], "signed": False, "notarized": False, "validated_on_macos": False}
    except BaseException:
        shutil.rmtree(output)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "runtime", "runtime-manifest", "wheelhouse", "wheelhouse-manifest"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = vars(parser.parse_args())
    try:
        print(json.dumps(build(**args), indent=2))
    except (OperationError, OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
