#!/usr/bin/env python3
"""Prepare native, hash-verified standalone runtimes and offline wheels.

The runtime SHA256 is pinned in reviewed source, obtained from the official
release's SHA256SUMS (and independently compared with GitHub asset digests).
Downloading a checksum beside an arbitrary payload is not accepted. This is a
build operation, never part of the participant's installation experience.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.package_macos import inventory
from mia.operations import BOOTSTRAP, OperationError


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise OperationError("Download redirecionou para destino não HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def digest(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def download(url: str, destination: Path, expected: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise OperationError("Proveniência de download inválida")
    if destination.is_symlink():
        raise OperationError("Cache de download não pode ser link")
    if destination.exists():
        if not destination.is_file() or digest(destination) != expected:
            raise OperationError("Cache difere do hash fixado; não será executado nem substituído")
        return
    temporary = destination.with_name(destination.name + ".part")
    if temporary.exists() or temporary.is_symlink():
        raise OperationError("Download interrompido existe; revise antes de repetir")
    try:
        opener = urllib.request.build_opener(HTTPSRedirect)
        with opener.open(url, timeout=60) as response, temporary.open("xb") as output:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 200 * 1024 * 1024:
                    raise OperationError("Artefato excede limite de download")
                output.write(chunk)
        if digest(temporary) != expected:
            raise OperationError("Artefato difere do hash fixado na fonte revisada")
        temporary.rename(destination)
    finally:
        temporary.unlink(missing_ok=True)


def extract_runtime(archive: Path, output: Path) -> None:
    """Even trusted archives must have bounded, safe filesystem members."""
    if output.exists() or output.is_symlink():
        raise OperationError("Runtime exige diretório novo")
    stage = output.with_name(output.name + "-extracting")
    if stage.exists() or stage.is_symlink():
        raise OperationError("Extração interrompida existe")
    stage.mkdir()
    try:
        with tarfile.open(archive, "r:gz") as stream:
            entries = stream.getmembers()
            if len(entries) > 100000 or sum(member.size for member in entries) > 2 * 1024 ** 3:
                raise OperationError("Runtime excede limites de extração")
            seen = set()
            for member in entries:
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts or "\\" in member.name or not path.parts or path.parts[0] != "python" or member.name in seen:
                    raise OperationError("Caminho inválido ou duplicado no runtime")
                seen.add(member.name)
                if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                    raise OperationError("Arquivo especial no runtime")
            stream.extractall(stage, members=entries, filter="data")
        (stage / "python").rename(output)
        inventory(output)  # Reject any escaping/dangling links before execution.
    finally:
        shutil.rmtree(stage)


def preserve_runtime_notices(archive: Path, runtime: Path, triple: str, *, supplemental: list[tuple[dict, Path]] | None = None) -> dict:
    """Full official distribution carries linked-library license texts."""
    zstd = shutil.which("zstd")
    if not zstd:
        raise OperationError("Build exige zstd para preservar avisos do runtime completo")
    notices = runtime / "MIA_RUNTIME_NOTICES"
    notices.mkdir()
    metadata = None
    process = subprocess.Popen([zstd, "-dc", str(archive)], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as stream:
            for member in stream:
                if member.name != "python/PYTHON.json" and not member.name.startswith("python/licenses/"):
                    continue
                if member.isdir():
                    continue
                path = PurePosixPath(member.name)
                if not member.isfile() or ".." in path.parts or len(path.parts) not in (2, 3) or member.size > 8 * 1024 * 1024:
                    raise OperationError("Aviso de runtime inválido")
                content = stream.extractfile(member).read()
                destination = notices / path.name
                if destination.exists():
                    raise OperationError("Aviso de runtime duplicado")
                destination.write_bytes(content)
                if member.name == "python/PYTHON.json":
                    metadata = json.loads(content)
        if process.wait() != 0:
            raise OperationError("Não foi possível ler avisos de runtime")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
    if not metadata or metadata.get("target_triple") != triple or metadata.get("python_major_minor_version") != "3.12":
        raise OperationError("Metadados do runtime completo não correspondem ao alvo")
    recorded_supplements = []
    for entry, source_archive in supplemental or []:
        destination = notices / entry["destination"]
        if destination.exists():
            continue
        if destination.name != entry["destination"] or digest(source_archive) != entry["archive_sha256"]:
            raise OperationError("Proveniência do aviso complementar não corresponde ao hash fixado")
        with tarfile.open(source_archive, "r:gz") as stream:
            member = stream.getmember(entry["member"])
            if not member.isfile() or member.size > 1024 * 1024:
                raise OperationError("Aviso complementar inválido")
            content = stream.extractfile(member).read()
        if hashlib.sha256(content).hexdigest() != entry["notice_sha256"]:
            raise OperationError("Texto do aviso complementar difere da fonte revisada")
        destination.write_bytes(content)
        recorded_supplements.append(entry)
    paths = set()
    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "license_path" and isinstance(item, str):
                    paths.add(item)
                elif key == "license_paths" and isinstance(item, list):
                    paths.update(item)
                else:
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    collect(metadata)
    if not paths or any(not (notices / PurePosixPath(path).name).is_file() for path in paths):
        raise OperationError("Avisos de bibliotecas do runtime estão incompletos")
    return {"minimum_macos": metadata.get("apple_sdk_deployment_target"), "target_triple": triple, "license_paths": sorted(paths), "supplemental_notices": recorded_supplements, "notice_files": inventory(notices)}


def wheel_provenance(wheelhouse: Path, pins: list[str]) -> list[dict]:
    expected = {re.sub(r"[-_.]+", "-", pin.split("==")[0]).lower(): pin.split("==")[1] for pin in pins}
    artifacts = []
    seen = set()
    for wheel in sorted(wheelhouse.iterdir()):
        if wheel.is_symlink() or not wheel.is_file() or wheel.suffix != ".whl":
            raise OperationError("Wheelhouse contém arquivo inesperado")
        name, version = wheel.name.split("-")[:2]
        name = re.sub(r"[-_.]+", "-", name).lower()
        if expected.get(name) != version or name in seen:
            raise OperationError("Wheelhouse não corresponde às versões fixadas")
        seen.add(name)
        with urllib.request.build_opener(HTTPSRedirect).open(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as response:
            metadata = json.load(response)
        matches = [entry for entry in metadata["urls"] if entry["filename"] == wheel.name]
        if len(matches) != 1 or matches[0]["digests"]["sha256"] != digest(wheel):
            raise OperationError("Wheel difere do hash publicado no PyPI")
        parsed = urllib.parse.urlsplit(matches[0]["url"])
        if parsed.scheme != "https" or parsed.hostname != "files.pythonhosted.org" or parsed.username or parsed.password:
            raise OperationError("Origem de wheel não é o PyPI oficial")
        # Preserve readable license material as well as the original wheel bytes.
        with zipfile.ZipFile(wheel) as archive:
            notices = [entry.filename for entry in archive.infolist() if not entry.is_dir() and (".dist-info/licenses/" in entry.filename or re.match(r"(?i)(license|copying|notice|authors)(\.|$)", PurePosixPath(entry.filename).name))]
        if not notices:
            raise OperationError(f"Wheel sem avisos de licença: {wheel.name}")
        artifacts.append({"filename": wheel.name, "source_url": matches[0]["url"], "sha256": digest(wheel), "notice_members": notices})
    if seen != set(expected):
        raise OperationError("Wheelhouse está incompleto")
    return artifacts


def verify_prepared(runtime: Path, wheelhouse: Path, target_platform: str, architecture: str, cache: Path, *, source: Path = ROOT) -> None:
    """Authenticate bytes against pinned upstream inputs, not their own manifest.

    Suitable for verifying the Linux companion on a Mac: this never executes
    the foreign runtime. The reviewed release hashes authenticate extraction;
    PyPI's verified HTTPS metadata authenticates exact locked wheel archives.
    """
    lock = json.loads((ROOT / "scripts/macos-runtime-lock.json").read_text())
    target = lock["targets"][target_platform + "-" + architecture]
    cache.mkdir(parents=True, exist_ok=True)
    base = "https://github.com/astral-sh/python-build-standalone/releases/download/" + lock["release"] + "/"
    for name, sha in ((target["archive"], target["sha256"]), (target["license_archive"], target["license_archive_sha256"])):
        download(base + urllib.parse.quote(name), cache / name, sha)
    supplements = []
    for entry in lock.get("supplemental_notices", []):
        path = cache / entry["archive_name"]
        download(entry["source_url"], path, entry["archive_sha256"])
        supplements.append((entry, path))
    with tempfile.TemporaryDirectory(prefix="mia-runtime-origin-verification-") as stage:
        expected_runtime = Path(stage) / "runtime"
        extract_runtime(cache / target["archive"], expected_runtime)
        preserve_runtime_notices(cache / target["license_archive"], expected_runtime, target["triple"], supplemental=supplements)
        if inventory(runtime) != inventory(expected_runtime):
            raise OperationError("Runtime preparado não corresponde aos bytes oficiais fixados")
    pins = [line.strip() for line in (source / "requirements.lock").read_text().splitlines() if line.strip()] + list(BOOTSTRAP)
    wheel_provenance(wheelhouse, pins)


def prepare(output: Path, target_platform: str, architecture: str, cache: Path, *, source: Path = ROOT) -> dict:
    current_arch = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "x86_64"}.get(platform.machine())
    expected_system = "Darwin" if target_platform == "macos" else "Linux"
    if platform.system() != expected_system or current_arch != architecture:
        raise OperationError("Prepare no sistema/arquitetura nativos; não executar runtime de outro alvo")
    if output.exists() or output.is_symlink():
        raise OperationError("Use diretório novo para artefatos")
    lock = json.loads((ROOT / "scripts/macos-runtime-lock.json").read_text())
    target = lock["targets"][target_platform + "-" + architecture]
    output.mkdir(parents=True)
    cache.mkdir(parents=True, exist_ok=True)
    base = "https://github.com/astral-sh/python-build-standalone/releases/download/" + lock["release"] + "/"
    for name, sha in ((target["archive"], target["sha256"]), (target["license_archive"], target["license_archive_sha256"])):
        download(base + urllib.parse.quote(name), cache / name, sha)
    supplements = []
    for entry in lock.get("supplemental_notices", []):
        destination = cache / entry["archive_name"]
        download(entry["source_url"], destination, entry["archive_sha256"])
        supplements.append((entry, destination))
    runtime = output / "runtime"
    extract_runtime(cache / target["archive"], runtime)
    notices = preserve_runtime_notices(cache / target["license_archive"], runtime, target["triple"], supplemental=supplements)
    if target_platform == "macos" and tuple(map(int, notices["minimum_macos"].split("."))) > (13, 0):
        raise OperationError("Runtime não suporta macOS mínimo da demo")
    pins = [line.strip() for line in (source / "requirements.lock").read_text().splitlines() if line.strip()] + list(BOOTSTRAP)
    requirement_file = output / "build-requirements.txt"
    requirement_file.write_text("\n".join(pins) + "\n")
    wheelhouse = output / "wheelhouse"
    wheelhouse.mkdir()
    subprocess.run([str(runtime / "bin/python3"), "-I", "-m", "pip", "download", "--only-binary=:all:", "--disable-pip-version-check", "--index-url", "https://pypi.org/simple/", "--dest", str(wheelhouse), "-r", str(requirement_file)], check=True)
    wheels = wheel_provenance(wheelhouse, pins)
    common = {"format": 1, "platform": target_platform, "architecture": architecture, "python_version": lock["python_version"]}
    runtime_manifest = {**common, "source_url": base + urllib.parse.quote(target["archive"]), "archive_sha256": target["sha256"], "official_checksum_source": lock["checksum_source"], "license_archive_url": base + urllib.parse.quote(target["license_archive"]), "license_archive_sha256": target["license_archive_sha256"], "notices": notices, "files": inventory(runtime)}
    wheel_manifest = {**common, "source_url": "https://pypi.org/simple/", "artifacts": wheels, "files": inventory(wheelhouse)}
    (output / "runtime-manifest.json").write_text(json.dumps(runtime_manifest, indent=2))
    (output / "wheelhouse-manifest.json").write_text(json.dumps(wheel_manifest, indent=2))
    if target_platform == "linux":
        # A separate verified companion ships in the Mac app. No runtime is
        # downloaded onto a participant's server during initial installation.
        from scripts.package_macos import copy_public_source, source_provenance
        companion = output / "remote-runtime"
        payload = companion / "payload"
        payload.mkdir(parents=True)
        shutil.copytree(runtime, payload / "runtime", symlinks=True)
        shutil.copytree(wheelhouse, payload / "wheelhouse")
        copy_public_source(source, payload / "source")
        version = tomllib.loads((source / "pyproject.toml").read_text())["project"]["version"]
        manifest = {"format": 1, "platform": "ubuntu24.04", "architecture": "amd64", "python_version": lock["python_version"], "version": version, "runtime_provenance": runtime_manifest, "wheelhouse_provenance": wheel_manifest, "source_provenance": source_provenance(source, payload / "source"), "files": inventory(payload)}
        (companion / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return {"platform": target_platform, "architecture": architecture, "output": str(output), "runtime_sha256": target["sha256"], "wheel_count": len(wheels), "mac_ui_tested": False}


def sign_app(app: Path, identity: str) -> dict:
    """Sign nested code before the outer resource seal; credentials stay local.

    Codesign changes runtime bytes, so retain the pre-sign inventory separately
    and recompute the installed runtime inventory before sealing the app. The
    signed outer bundle/feed authenticates that deliberate transformation.
    """
    if platform.system() != "Darwin" or not identity.startswith("Developer ID Application: "):
        raise OperationError("Assinatura exige Mac e identidade Developer ID Application")
    if app.is_symlink() or app.suffix != ".app" or not app.is_dir():
        raise OperationError("Assinatura exige bundle regular")
    identities = subprocess.check_output(["security", "find-identity", "-v", "-p", "codesigning"], text=True)
    if '"' + identity + '"' not in identities:
        raise OperationError("Identidade Developer ID não está disponível no Keychain")
    magic = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"}
    for file in sorted(app.rglob("*"), key=lambda path: len(path.parts), reverse=True):
        if file.is_symlink() or not file.is_file():
            continue
        with file.open("rb") as stream:
            native = stream.read(4) in magic
        if native:
            subprocess.run(["codesign", "--force", "--options", "runtime", "--timestamp", "--preserve-metadata=entitlements", "--sign", identity, str(file)], check=True)
    for folder in sorted(app.rglob("*"), key=lambda path: len(path.parts), reverse=True):
        if folder.is_symlink() or not folder.is_dir() or folder.suffix not in {".framework", ".app", ".xpc"}:
            continue
        subprocess.run(["codesign", "--force", "--options", "runtime", "--timestamp", "--preserve-metadata=entitlements", "--sign", identity, str(folder)], check=True)
    resources = app / "Contents/Resources"
    report_path = resources / "build-report.json"
    report = json.loads(report_path.read_text())
    original = report["runtime_provenance"]["files"]
    report["runtime_provenance"]["source_archive_files"] = original
    report["runtime_provenance"]["files"] = inventory(resources / "runtime")
    report["runtime_provenance"]["content_transformation"] = "Developer ID codesign of native runtime executables/libraries"
    report["signing_requested"] = True
    report["signed"] = False  # Assembly record; external verified receipt is authoritative.
    report["notarized"] = False
    report_path.unlink()
    report["files"] = inventory(app)
    report_path.write_text(json.dumps(report, indent=2))
    subprocess.run(["codesign", "--force", "--options", "runtime", "--timestamp", "--sign", identity, str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)], check=True)
    return {"signed": True, "notarized": False, "runtime_inventory_updated_after_signing": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--platform", choices=["macos", "linux"])
    parser.add_argument("--architecture", choices=["arm64", "x86_64"])
    parser.add_argument("--sign-app", type=Path)
    parser.add_argument("--sign-identity")
    parser.add_argument("--verify-prepared", type=Path, help="Authenticate prepared bytes against pinned upstream archives without executing the runtime")
    args = parser.parse_args()
    try:
        if args.sign_app is not None:
            if not args.sign_identity or any((args.output, args.cache, args.platform, args.architecture, args.verify_prepared)):
                parser.error("--sign-app exige --sign-identity e não aceita opções de preparação")
            result = sign_app(args.sign_app, args.sign_identity)
        elif args.verify_prepared is not None:
            if args.output or args.sign_identity or not all((args.cache, args.platform, args.architecture)):
                parser.error("--verify-prepared exige --cache --platform --architecture")
            verify_prepared(args.verify_prepared / "runtime", args.verify_prepared / "wheelhouse", args.platform, args.architecture, args.cache)
            result = {"upstream_bytes_verified": True, "runtime_executed": False}
        else:
            if args.sign_identity or not all((args.output, args.cache, args.platform, args.architecture)):
                parser.error("preparação exige --output --cache --platform --architecture")
            result = prepare(args.output, args.platform, args.architecture, args.cache)
        print(json.dumps(result, indent=2))
    except (OperationError, OSError, ValueError, KeyError, subprocess.CalledProcessError, tarfile.TarError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
