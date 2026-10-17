"""Operator tools for an authenticated, immutable demonstration release.

This module does not enroll an Apple account, invent trust keys, declare human
acceptance, deploy HTTPS, or invite anybody. Production staging requires signed
Apple build attestations and an explicit acceptance record for the exact DMGs.
State, signing material and generated artifacts belong outside the checkout.
"""
from __future__ import annotations

import base64
import contextlib
import datetime
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from mia.demo_distribution import DistributionError, _private_directory, create_distribution_app
from mia.updates import MAX_ARTIFACT, MAX_FEED, UpdateError, _decode, _https, _json, _version, validate_channel

ARCHITECTURES = ("arm64", "x86_64")
SPARKLE_VERSION = "2.10.0"
SPARKLE_SOURCE_REVISION = "eef1a539a373c1f1a320624b1130fc5de7b2e100"
SPARKLE_TOOL_ARCHIVE_SHA256 = "c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c"
SPARKLE_TOOL_ARCHIVE_URL = "https://github.com/sparkle-project/Sparkle/releases/download/2.10.0/Sparkle-2.10.0.tar.xz"
SPARKLE_NS = "http://www.andymatuschak.org/xml-namespaces/sparkle"
ACCEPTANCE_CHECKS = {
    "local": ("first_launch", "empty_installation", "import_and_today_sources", "quit_without_terminal", "restart_and_login", "sleep_and_resume", "snapshot_and_restore", "signed_app_update_preserves_context", "signed_backend_update_preserves_context"),
    "remote": ("first_launch", "verified_ssh_host", "empty_installation", "import_and_today_sources", "quit_without_terminal", "server_restart", "reconnect_and_login", "snapshot_and_restore", "signed_backend_update_preserves_context"),
}
APPLE_GATES = ("signed", "notarized", "codesign_verified", "notarization_accepted", "dmg_ticket_validated", "gatekeeper_assessed", "disk_image_integrity_verified", "native_backend_smoke_passed")


class PublicationError(ValueError):
    pass


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def digest(path: Path) -> str:
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _regular(path: Path, *, private: bool = False, maximum: int = 2 * 1024**3) -> Path:
    path = Path(path).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise PublicationError("Caminho de publicação não aceita links simbólicos")
    try:
        info = path.stat()
    except OSError:
        raise PublicationError("Arquivo de publicação não encontrado") from None
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
        raise PublicationError("Arquivo de publicação não é regular ou excedeu o limite")
    if private and (info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_nlink != 1):
        raise PublicationError("Material de assinatura precisa pertencer ao usuário, sem links e com permissão 0600")
    if not private and info.st_mode & 0o022:
        raise PublicationError("Arquivo de publicação não pode permitir escrita por outros usuários")
    return path


def read_json(path: Path, *, private: bool = False) -> dict:
    try:
        return _json(_regular(path, private=private, maximum=MAX_FEED).read_bytes())
    except (ValueError, OSError, UpdateError) as error:
        if isinstance(error, PublicationError):
            raise
        raise PublicationError("JSON de publicação inválido") from None


def _write_new(path: Path, value: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(descriptor, "wb") as output:
        output.write(value)
        output.flush()
        os.fsync(output.fileno())


def _run(arguments: list[str], *, timeout: int = 60, input: bytes | None = None) -> bytes:
    # Error text can contain key material or signed URLs. Return only a fixed
    # operator error, and never display native stdout from key-handling tools.
    try:
        result = subprocess.run(arguments, input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise PublicationError("Ferramenta de assinatura/verificação indisponível ou excedeu o prazo") from None
    if result.returncode:
        raise PublicationError("Ferramenta recusou a assinatura/verificação; nenhum artefato foi publicado")
    if len(result.stdout) > MAX_FEED:
        raise PublicationError("Resposta da ferramenta excedeu o limite")
    return result.stdout


class OpenSSLSigner:
    """Ed25519 signer for a private PEM file; no additional Mia dependency."""
    def __init__(self, key_file: Path):
        self.key_file = _regular(key_file, private=True, maximum=16384)
        public = _run(["/usr/bin/openssl", "pkey", "-in", str(self.key_file), "-pubout", "-outform", "DER"])
        if len(public) != 44 or public[:12] != bytes.fromhex("302a300506032b6570032100"):
            raise PublicationError("Chave privada não é Ed25519")
        self.public_key = base64.b64encode(public[-32:]).decode()

    def sign(self, payload: Path) -> str:
        _regular(self.key_file, private=True, maximum=16384)
        signature = _run(["/usr/bin/openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(self.key_file), "-in", str(_regular(payload))])
        if len(signature) != 64:
            raise PublicationError("Assinatura Ed25519 tem tamanho inválido")
        encoded = base64.b64encode(signature).decode()
        verify_ed25519(self.public_key, encoded, payload)
        return encoded


def verify_ed25519(public_key: str, signature: str, payload: Path, *, native_helper: Path | None = None) -> None:
    try:
        key, sig = _decode(public_key, 32), _decode(signature, 64)
    except (ValueError, UpdateError):
        raise PublicationError("Chave pública ou assinatura Ed25519 inválida") from None
    payload = _regular(payload)
    if native_helper is not None:
        # Only the already Apple-verified executable from the mounted DMG may
        # be supplied by attest_signed_dmg. Production CLI offers no arbitrary
        # executable parameter.
        _run([str(native_helper), "--verify-ed25519", public_key, signature, str(payload)], timeout=30)
        return
    if sys.platform == "darwin":
        # Apple's /usr/bin/openssl is not guaranteed to implement Ed25519.
        # Operator Macs already require Xcode command line tools to build the
        # release. This fixed CryptoKit program verifies the explicit public key
        # independently of the signing key selected in sign_update.
        program = b'''import Foundation
import CryptoKit
let args = CommandLine.arguments
guard args.count == 4, let key = Data(base64Encoded: args[1]), key.count == 32,
      let signature = Data(base64Encoded: args[2]), signature.count == 64,
      let publicKey = try? Curve25519.Signing.PublicKey(rawRepresentation: key),
      let payload = try? Data(contentsOf: URL(fileURLWithPath: args[3]), options: .mappedIfSafe),
      publicKey.isValidSignature(signature, for: payload) else { exit(1) }
'''
        _run(["/usr/bin/xcrun", "swift", "-", public_key, signature, str(payload)], input=program, timeout=120)
        return
    with tempfile.TemporaryDirectory(prefix="mia-public-key-") as temporary:
        root = Path(temporary).resolve()
        _write_new(root / "key.der", bytes.fromhex("302a300506032b6570032100") + key)
        _write_new(root / "signature", sig)
        _run(["/usr/bin/openssl", "pkeyutl", "-verify", "-rawin", "-pubin", "-keyform", "DER", "-inkey", str(root / "key.der"), "-sigfile", str(root / "signature"), "-in", str(payload)], timeout=30)


def extract_sparkle_tools(archive: Path, destination: Path) -> Path:
    """Extract only the authenticated signing tool and upstream license.

    The upstream executable is self-contained. Whole-archive validation occurs
    before writing anything; test apps and frameworks need not be redistributed.
    """
    archive = _regular(archive, maximum=32 * 1024**2)
    if digest(archive) != SPARKLE_TOOL_ARCHIVE_SHA256:
        raise PublicationError("Ferramentas Sparkle diferem do arquivo oficial fixado")
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise PublicationError("Destino das ferramentas já existe; foi preservado")
    try:
        with tarfile.open(archive, "r:xz") as source:
            records = source.getmembers()
            if len(records) > 2000 or sum(member.size for member in records) > 200 * 1024**2:
                raise PublicationError("Arquivo Sparkle excedeu o limite")
            seen = set()
            for member in records:
                name = member.name[2:] if member.name.startswith("./") else member.name
                path = PurePosixPath(name)
                if not name or path.is_absolute() or ".." in path.parts or "\\" in name or name in seen or not (member.isfile() or member.isdir() or member.issym()):
                    raise PublicationError("Arquivo Sparkle contém caminho inesperado")
                if member.issym() and (PurePosixPath(member.linkname).is_absolute() or ".." in PurePosixPath(member.linkname).parts):
                    raise PublicationError("Arquivo Sparkle contém link não permitido")
                seen.add(name)
            selected = {member.name.removeprefix("./"): member for member in records if member.name.removeprefix("./") in ("bin/sign_update", "LICENSE")}
            if set(selected) != {"bin/sign_update", "LICENSE"} or any(not member.isfile() for member in selected.values()):
                raise PublicationError("Ferramentas/avisos Sparkle estão incompletos")
            destination.mkdir(parents=True, mode=0o700)
            for name, member in selected.items():
                target = destination / PurePosixPath(name).name
                _write_new(target, source.extractfile(member).read(), mode=0o700 if name.startswith("bin/") else 0o600)
    except (OSError, tarfile.TarError):
        raise PublicationError("Não foi possível preparar ferramentas Sparkle verificadas") from None
    return destination / "sign_update"


class SparkleSigner:
    """Pinned native sign_update using an existing Keychain account/key file."""
    def __init__(self, archive: Path, public_key: str, *, account: str = "ed25519", key_file: Path | None = None):
        if sys.platform != "darwin":
            raise PublicationError("Ferramenta de assinatura Sparkle exige Mac; um teste Linux não substitui essa assinatura")
        try:
            _decode(public_key, 32)
        except (ValueError, UpdateError):
            raise PublicationError("Chave pública Sparkle inválida") from None
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", account):
            raise PublicationError("Nome da conta Keychain inválido")
        self.public_key, self.account = public_key, account
        self.key_file = _regular(key_file, private=True, maximum=16384) if key_file is not None else None
        self.temporary = tempfile.TemporaryDirectory(prefix="mia-sparkle-signing-")
        self.tool = extract_sparkle_tools(archive, Path(self.temporary.name).resolve() / "tools")

    def close(self):
        self.temporary.cleanup()

    def _arguments(self) -> list[str]:
        if self.key_file is not None:
            _regular(self.key_file, private=True, maximum=16384)
            return [str(self.tool), "--ed-key-file", str(self.key_file)]
        return [str(self.tool), "--account", self.account]

    def sign(self, payload: Path) -> str:
        if payload.suffix.lower() == ".xml":
            raise PublicationError("Use sign_appcast para XML; sua assinatura é incorporada pelo Sparkle")
        encoded = _run(self._arguments() + ["-p", str(_regular(payload))]).decode("ascii").strip()
        try:
            _decode(encoded, 64)
        except (ValueError, UpdateError):
            raise PublicationError("Resposta de assinatura Sparkle inválida") from None
        # sign_update's verification reads the public portion of the same
        # selected key. Attestation additionally verifies its public trust key
        # with the signed native helper; Linux staging uses OpenSSL.
        _run(self._arguments() + ["--verify", str(payload), encoded])
        return encoded

    def sign_appcast(self, path: Path) -> None:
        _run(self._arguments() + ["--disable-signing-warning", str(_regular(path))])
        _run(self._arguments() + ["--verify", str(path)])


def channel_for(origin: str, channel: str, architecture: str, backend_public_key: str, sparkle_public_key: str) -> dict:
    origin = _https(origin).rstrip("/")
    parsed = urllib.parse.urlsplit(origin)
    if parsed.path or architecture not in ARCHITECTURES:
        raise PublicationError("Publicação precisa de uma origem HTTPS e arquitetura suportada")
    result = {"protocol": 1, "channel": channel, "distribution_url": origin, "beta_access_required": True, "backend_feed_url": origin + "/updates/" + architecture + "/backend.json", "backend_public_key": backend_public_key,
              "appcast_url": origin + "/updates/" + architecture + "/appcast.xml", "sparkle_public_key": sparkle_public_key}
    try:
        validate_channel(result)
    except (ValueError, UpdateError):
        raise PublicationError("Configuração pública do canal inválida") from None
    return result


def _receipt_metadata(receipt: dict, artifact: Path, *, require_apple: bool = True, require_channel: bool = True) -> dict:
    artifact = _regular(artifact)
    if receipt.get("format") != 2 or receipt.get("artifact") != artifact.name or receipt.get("sha256") != digest(artifact) or receipt.get("size") != artifact.stat().st_size:
        raise PublicationError("Recibo não corresponde aos bytes/nome/tamanho do DMG final")
    architecture, version = receipt.get("architecture"), receipt.get("app_version")
    if architecture not in ARCHITECTURES or receipt.get("backend_version") != version:
        raise PublicationError("Recibo não identifica arquitetura e versões compatíveis")
    try:
        _version(version)
    except (ValueError, TypeError, UpdateError):
        raise PublicationError("Versão do recibo inválida") from None
    if require_apple and any(receipt.get(key) is not True for key in APPLE_GATES):
        raise PublicationError("Recibo não comprova assinatura, notarização, Gatekeeper e ensaio do artefato final")
    source = receipt.get("source_provenance", {})
    files = source.get("files")
    if source.get("clean_checkout") is not True or not re.fullmatch(r"[a-f0-9]{40}", str(source.get("revision", ""))) or not isinstance(files, dict) or not files or source.get("files_sha256") != hashlib.sha256(canonical(files)).hexdigest():
        raise PublicationError("Recibo exige inventário de fonte pública de um commit limpo e revisado")
    for name, entry in files.items():
        if not isinstance(name, str) or not isinstance(entry, dict) or not re.fullmatch(r"[a-f0-9]{64}", str(entry.get("sha256", ""))) or set(entry) != {"sha256", "executable"} or not isinstance(entry["executable"], bool):
            raise PublicationError("Inventário de fonte pública contém registro inválido")
    wheels = receipt.get("wheelhouse_provenance", {}).get("files")
    if not isinstance(wheels, dict) or not wheels:
        raise PublicationError("Recibo não vincula os wheels Mac autenticados")
    if require_channel:
        try:
            validate_channel(receipt.get("release_channel"))
        except (ValueError, UpdateError):
            raise PublicationError("Recibo não vincula o canal público embarcado") from None
        channel = receipt["release_channel"]
        if not channel.get("appcast_url") or not channel.get("backend_feed_url"):
            raise PublicationError("A demonstração publicada exige canais de app e backend configurados no bundle")
    if receipt.get("minimum_macos") != "13.0" or receipt.get("bundle_identifier") != "org.mia.demo":
        raise PublicationError("Recibo identifica requisitos/plataforma diferentes da demonstração revisada")
    return receipt


def _envelope(payload: bytes, signature: str) -> dict:
    return {"protocol": 1, "payload": base64.b64encode(payload).decode(), "signature": signature}


def read_attestation(path: Path, artifact: Path, public_key: str) -> dict:
    envelope = read_json(path)
    try:
        if envelope.get("protocol") != 1 or set(envelope) != {"protocol", "payload", "signature"}:
            raise ValueError
        payload = base64.b64decode(envelope["payload"], validate=True)
        if len(payload) > MAX_FEED:
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise PublicationError("Atestação de build assinada inválida") from None
    with tempfile.TemporaryDirectory(prefix="mia-build-attestation-") as temporary:
        verified = Path(temporary).resolve() / "payload.json"
        _write_new(verified, payload)
        verify_ed25519(public_key, envelope.get("signature"), verified)
    try:
        receipt = _json(payload)
    except (ValueError, UpdateError):
        raise PublicationError("Recibo atestado inválido") from None
    return _receipt_metadata(receipt, artifact)


@contextlib.contextmanager
def _mounted_dmg(artifact: Path):
    """Read-only mount limited to a newly created private mount point."""
    with tempfile.TemporaryDirectory(prefix="mia-release-mount-") as temporary:
        mount = Path(temporary).resolve() / "image"
        mount.mkdir(mode=0o700)
        attached = False
        try:
            response = _run(["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), "-plist", str(artifact)], timeout=120)
            attached = True
            data = plistlib.loads(response)
            points = [record.get("mount-point") for record in data.get("system-entities", []) if record.get("mount-point")]
            if points != [str(mount)]:
                raise PublicationError("DMG não foi montado no único destino privado esperado")
            yield mount
        finally:
            if attached:
                # Do not use force or detach any volume inferred from a name.
                _run(["/usr/bin/hdiutil", "detach", str(mount)], timeout=120)


def attest_signed_dmg(artifact: Path, receipt_path: Path, destination: Path, signer: SparkleSigner) -> dict:
    """Generate a build attestation only after actual Apple verification.

    Human UI acceptance remains a separate operator declaration. A JSON file
    with booleans can never substitute for these checks or for a signed receipt.
    """
    if sys.platform != "darwin" or not isinstance(signer, SparkleSigner):
        raise PublicationError("Atestação Apple requer Mac e ferramenta Sparkle autenticada")
    artifact = _regular(artifact)
    receipt = _receipt_metadata(read_json(receipt_path), artifact)
    _run(["/usr/bin/hdiutil", "verify", str(artifact)], timeout=120)
    _run(["/usr/bin/xcrun", "stapler", "validate", str(artifact)], timeout=120)
    _run(["/usr/sbin/spctl", "--assess", "--type", "open", "--context", "context:primary-signature", str(artifact)], timeout=120)
    with _mounted_dmg(artifact) as mounted:
        app = mounted / "Mia.app"
        if not app.is_dir() or app.is_symlink():
            raise PublicationError("DMG não contém o aplicativo Mia esperado")
        _run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)], timeout=120)
        _run(["/usr/sbin/spctl", "--assess", "--type", "execute", str(app)], timeout=120)
        _run(["/usr/bin/xcrun", "stapler", "validate", str(app)], timeout=120)
        info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
        from scripts.package_macos import inventory, macho_architecture
        resources = app / "Contents/Resources"
        helper = app / "Contents/MacOS/Mia"
        if macho_architecture(helper) != receipt["architecture"] or info.get("MiaBackendVersion") != receipt["app_version"] or info.get("CFBundleIdentifier") != receipt["bundle_identifier"] or info.get("LSMinimumSystemVersion") != receipt["minimum_macos"]:
            raise PublicationError("Aplicativo montado difere dos metadados do recibo")
        if receipt.get("app_files") != inventory(app) or receipt.get("app_inventory_sha256") != hashlib.sha256(canonical(receipt["app_files"])).hexdigest():
            raise PublicationError("Aplicativo montado difere do inventário do build final")
        if inventory(resources / "source") != receipt["source_provenance"]["files"] or inventory(resources / "wheelhouse") != receipt["wheelhouse_provenance"]["files"] or read_json(resources / "release-channel.json") != receipt["release_channel"]:
            raise PublicationError("Fonte, wheels ou canal montados diferem do recibo")
        receipt = {**receipt, "apple_attestation": {"protocol": 1, "verified_at": int(time.time()), "method": "read-only-dmg-apple-tools-and-byte-inventories"}}
        with tempfile.TemporaryDirectory(prefix="mia-attest-payload-") as temporary:
            payload = Path(temporary).resolve() / "receipt.json"
            _write_new(payload, canonical(receipt))
            signature = signer.sign(payload)
            verify_ed25519(signer.public_key, signature, payload, native_helper=helper)
            _write_new(Path(destination), canonical(_envelope(payload.read_bytes(), signature)) + b"\n")
    return {"attestation": str(destination), "artifact_sha256": receipt["sha256"], "architecture": receipt["architecture"], "version": receipt["app_version"], "verified": True}


def acceptance_template(receipts: list[dict]) -> dict:
    return {"protocol": 1, "operator_approved": False, "declaration": "Observações do operador em máquinas reais; não são verificações automáticas da Mia.", "artifacts": [
        {"architecture": receipt["architecture"], "artifact_sha256": receipt["sha256"], "version": receipt["app_version"], "offered_modes": list(ACCEPTANCE_CHECKS), "modes": {mode: {"operating_system": "", "checks": {check: {"status": "not_run", "observed_at": None, "evidence": ""} for check in checks}} for mode, checks in ACCEPTANCE_CHECKS.items()}}
        for receipt in receipts]}


def acceptance_failures(ledger: dict, receipts: list[dict], *, now: int | None = None) -> list[str]:
    now = int(time.time()) if now is None else now
    failures = []
    if ledger.get("protocol") != 1 or ledger.get("operator_approved") is not True:
        failures.append("operator_acceptance_approval")
    records = ledger.get("artifacts")
    if not isinstance(records, list) or len(records) != len(receipts):
        return failures + ["acceptance_artifact_inventory"]
    for receipt in receipts:
        matches = [record for record in records if isinstance(record, dict) and record.get("architecture") == receipt["architecture"]]
        if len(matches) != 1 or matches[0].get("artifact_sha256") != receipt["sha256"] or matches[0].get("version") != receipt["app_version"]:
            failures.append(receipt["architecture"] + ":acceptance_artifact_binding")
            continue
        offered = matches[0].get("offered_modes")
        # The bundled app currently presents both installation choices. An
        # operator cannot waive a visible path by editing the acceptance JSON.
        # A future narrower release must first bind its choices in the signed
        # application and portal, rather than merely weakening this ledger.
        if not isinstance(offered, list) or any(not isinstance(mode, str) for mode in offered) or len(offered) != len(ACCEPTANCE_CHECKS) or set(offered) != set(ACCEPTANCE_CHECKS):
            failures.append(receipt["architecture"] + ":offered_modes")
            continue
        for mode in offered:
            required = ACCEPTANCE_CHECKS[mode]
            record = matches[0].get("modes", {}).get(mode, {})
            operating_system = record.get("operating_system")
            if not isinstance(operating_system, str) or not 3 <= len(operating_system) <= 200:
                failures.append(receipt["architecture"] + ":" + mode + ":operating_system")
            checks = record.get("checks", {})
            for name in required:
                check = checks.get(name, {}) if isinstance(checks, dict) else {}
                stamp, evidence = check.get("observed_at"), check.get("evidence")
                if check.get("status") != "passed" or isinstance(stamp, bool) or not isinstance(stamp, int) or not 1 <= stamp <= now + 300 or not isinstance(evidence, str) or not 10 <= len(evidence) <= 2000:
                    failures.append(receipt["architecture"] + ":" + mode + ":" + name)
    return failures


def publication_plan(receipts: list[dict], acceptance: dict | None, *, origin: str, channel: str, build_public_key: str, now: int | None = None) -> dict:
    now = int(time.time()) if now is None else now
    try:
        _decode(build_public_key, 32)
    except (ValueError, UpdateError):
        raise PublicationError("Publicação exige chave pública de atestação de build revisada") from None
    if not 1 <= len(receipts) <= 2 or len({receipt.get("architecture") for receipt in receipts}) != len(receipts) or any(receipt.get("architecture") not in ARCHITECTURES for receipt in receipts):
        raise PublicationError("Publicação exige pelo menos uma arquitetura Mac explicitamente oferecida e revisada")
    first = receipts[0]
    if any(receipt["app_version"] != first["app_version"] or receipt["source_provenance"] != first["source_provenance"] for receipt in receipts):
        raise PublicationError("Artefatos Mac precisam ter a mesma versão e fonte pública revisada")
    backend_key, sparkle_key = first["release_channel"].get("backend_public_key"), first["release_channel"].get("sparkle_public_key")
    for receipt in receipts:
        expected = channel_for(origin, channel, receipt["architecture"], backend_key, sparkle_key)
        if receipt["release_channel"] != expected:
            raise PublicationError("Canal embarcado não corresponde à origem/chaves/arquitetura desta publicação")
    blocked = [receipt["architecture"] + ":" + gate for receipt in receipts for gate in APPLE_GATES if receipt.get(gate) is not True]
    blocked.extend(acceptance_failures(acceptance or {}, receipts, now=now))
    plan = {"protocol": 1, "version": first["app_version"], "channel": channel, "origin": origin.rstrip("/"), "source_commit": first["source_provenance"]["revision"], "source_files_sha256": first["source_provenance"]["files_sha256"],
            "artifacts": [{"architecture": receipt["architecture"], "artifact": receipt["artifact"], "sha256": receipt["sha256"], "size": receipt["size"]} for receipt in sorted(receipts, key=lambda item: item["architecture"])],
            "build_attestation_public_key": build_public_key, "backend_public_key": backend_key, "sparkle_public_key": sparkle_key,
            "acceptance_sha256": hashlib.sha256(canonical(acceptance or {})).hexdigest(), "blocked_gates": blocked, "ready_to_stage": not blocked,
            "offered_modes": {record["architecture"]: record.get("offered_modes", []) for record in (acceptance or {}).get("artifacts", []) if isinstance(record, dict)},
            "policy": {"initial_portal": "invitation-gated", "official_app_updates": "private-beta-capability-blob-60s-leases", "backend_source_packages": "public-open-source", "revocation": "distribution-and-updates-only-does-not-revoke-installed-library"}}
    return {**plan, "approve_sha256": hashlib.sha256(canonical(plan)).hexdigest()}


def _prepare_backend(source: Path, wheels: Path, receipt: dict, output: Path) -> dict:
    from scripts.package_macos import copy_public_source, inventory
    source, wheels = Path(source), Path(wheels)
    if wheels.is_symlink() or not wheels.is_dir() or any(path.is_symlink() or not path.is_file() or path.suffix != ".whl" for path in wheels.iterdir()):
        raise PublicationError("Atualização precisa dos wheels Mac regulares revisados")
    if inventory(wheels) != receipt["wheelhouse_provenance"]["files"]:
        raise PublicationError("Wheels diferem dos bytes autenticados no build Mac")
    with tempfile.TemporaryDirectory(prefix="mia-backend-release-") as temporary:
        public = Path(temporary).resolve() / "source"
        copy_public_source(source, public)
        if inventory(public) != receipt["source_provenance"]["files"]:
            raise PublicationError("Fonte de atualização difere da fonte pública do aplicativo Mac revisado")
        metadata = tomllib.loads((public / "pyproject.toml").read_text())["project"]
        if metadata.get("name") != "mia-personal-ai" or metadata.get("version") != receipt["app_version"]:
            raise PublicationError("Fonte de atualização não corresponde à versão do aplicativo")
        manifest = {"protocol": 1, "target": "backend", "version": receipt["app_version"], "manager_protocol": 2, "runtime_changed": False, "manager_changed": False}
        total = sum(path.stat().st_size for path in public.rglob("*") if path.is_file()) + sum(path.stat().st_size for path in wheels.iterdir())
        if total > 1024**3:
            raise PublicationError("Pacote offline excedeu o limite expandido")
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            entries = {"update.json": canonical(manifest), **{"source/" + path.relative_to(public).as_posix(): path.read_bytes() for path in public.rglob("*") if path.is_file()}, **{"wheelhouse/" + path.name: path.read_bytes() for path in wheels.iterdir()}}
            if len(entries) > 30000:
                raise PublicationError("Pacote offline excedeu o limite de arquivos")
            for name, content in sorted(entries.items()):
                info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, content)
        output.chmod(0o600)
    if output.stat().st_size > MAX_ARTIFACT:
        raise PublicationError("Pacote offline excedeu o limite de atualização")
    return {"sha256": digest(output), "size": output.stat().st_size}


def _appcast(receipt: dict, archive_url: str, signature: str, notes: str, now: int) -> bytes:
    from scripts.package_macos import bundle_version_metadata
    ET.register_namespace("sparkle", SPARKLE_NS)
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Mia · Demonstração " + receipt["architecture"]
    ET.SubElement(channel, "link").text = receipt["release_channel"]["appcast_url"]
    ET.SubElement(channel, "description").text = "Atualizações autenticadas da Mia; seu contexto permanece na sua instalação."
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = "Mia " + receipt["app_version"]
    ET.SubElement(item, "pubDate").text = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    ET.SubElement(item, "description").text = notes
    ET.SubElement(item, "{" + SPARKLE_NS + "}minimumSystemVersion").text = receipt["minimum_macos"]
    metadata = bundle_version_metadata(receipt["app_version"])
    ET.SubElement(item, "enclosure", {"url": archive_url, "length": str(receipt["size"]), "type": "application/octet-stream", "{" + SPARKLE_NS + "}version": metadata["CFBundleVersion"], "{" + SPARKLE_NS + "}shortVersionString": receipt["app_version"], "{" + SPARKLE_NS + "}edSignature": signature})
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)


@contextlib.contextmanager
def _publisher_lock(state: Path):
    state = _private_directory(state)
    descriptor = os.open(state / "publisher.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_nlink != 1:
            raise PublicationError("Trava do publicador precisa ser regular e privada")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise PublicationError("Outra publicação está em andamento") from None
        yield state
    finally:
        os.close(descriptor)


def stage_release(state: Path, *, source: Path, artifacts: dict[str, Path], attestations: dict[str, Path], wheelhouses: dict[str, Path], acceptance_path: Path,
                  origin: str, channel: str, build_public_key: str, backend_signer, sparkle_signer, approve_sha256: str, notes: str,
                  lifetime_days: int = 7, refresh: bool = False, now: int | None = None) -> dict:
    """Commit immutable artifacts after attestation, signatures and acceptance.

    The operator approves an exact plan hash. Publication state never changes
    before every candidate exists and verifies. Failed candidates are preserved
    in staging, and existing releases cannot be overwritten or replayed.
    """
    now = int(time.time()) if now is None else now
    if not artifacts or not set(artifacts).issubset(ARCHITECTURES) or set(attestations) != set(artifacts) or set(wheelhouses) != set(artifacts):
        raise PublicationError("É necessário fornecer DMG, atestação e wheels para cada arquitetura oferecida")
    if isinstance(lifetime_days, bool) or not 1 <= lifetime_days <= 30 or not isinstance(notes, str) or len(notes) > 8000:
        raise PublicationError("Prazo ou notas de publicação inválidos")
    receipts = [read_attestation(attestations[arch], artifacts[arch], build_public_key) for arch in sorted(artifacts)]
    if any(receipt.get("apple_attestation", {}).get("method") != "read-only-dmg-apple-tools-and-byte-inventories" for receipt in receipts):
        raise PublicationError("Build não possui atestação das verificações Apple executadas no DMG final")
    ledger = read_json(acceptance_path)
    plan = publication_plan(receipts, ledger, origin=origin, channel=channel, build_public_key=build_public_key, now=now)
    if not plan["ready_to_stage"]:
        raise PublicationError("Aceite real ainda não está concluído para os artefatos finais")
    if approve_sha256 != plan["approve_sha256"]:
        raise PublicationError("Publicação exige aprovação do hash exato dos artefatos, canais e aceites")
    if backend_signer.public_key != plan["backend_public_key"] or sparkle_signer.public_key != plan["sparkle_public_key"]:
        raise PublicationError("Chaves de assinatura não correspondem à confiança embarcada nos aplicativos")
    with _publisher_lock(state) as state:
        current_path = state / "current.json"
        previous = read_json(current_path, private=True) if current_path.exists() else {}
        if previous:
            if previous.get("origin") != plan["origin"] or previous.get("channel") != channel or previous.get("build_attestation_public_key") != build_public_key or previous.get("backend_public_key") != plan["backend_public_key"] or previous.get("sparkle_public_key") != plan["sparkle_public_key"]:
                raise PublicationError("Mudança de origem/canal/chaves exige migração explícita; não será inferida")
            comparison = _version(plan["version"]) > _version(previous["version"])
            if not refresh and not comparison:
                raise PublicationError("Versão repetida ou regressiva recusada; releases publicados são imutáveis")
            if refresh and (plan["version"] != previous["version"] or plan["artifacts"] != previous["artifacts"] or plan["source_files_sha256"] != previous["source_files_sha256"] or plan["acceptance_sha256"] != previous["acceptance_sha256"]):
                raise PublicationError("Renovação precisa conservar exatamente os artefatos, fonte e aceites publicados")
        elif refresh:
            raise PublicationError("Não existe publicação para renovar")
        sequence = previous.get("sequence", 0) + 1
        release_id = plan["version"] + "-s" + str(sequence)
        staging = state / "staging"
        releases = state / "releases"
        for directory in (staging, releases):
            _private_directory(directory)
        candidate, final = staging / release_id, releases / release_id
        if candidate.exists() or final.exists():
            raise PublicationError("Candidato anterior foi preservado; revise-o antes de nova publicação")
        candidate.mkdir(mode=0o700)
        files, routes, portals = {}, {}, {}
        for receipt in receipts:
            arch = receipt["architecture"]
            dmg_name, package_name = "Mia-" + arch + ".dmg", "backend-" + arch + ".zip"
            shutil.copyfile(artifacts[arch], candidate / dmg_name)
            (candidate / dmg_name).chmod(0o600)
            if digest(candidate / dmg_name) != receipt["sha256"]:
                raise PublicationError("DMG mudou durante a preparação; candidato preservado")
            signature = sparkle_signer.sign(candidate / dmg_name)
            verify_ed25519(plan["sparkle_public_key"], signature, candidate / dmg_name)
            package = _prepare_backend(source, wheelhouses[arch], receipt, candidate / package_name)
            package_url = plan["origin"] + "/releases/" + release_id + "/" + package_name
            feed = {"protocol": 1, "channel": channel, "expires_at": now + lifetime_days * 86400, "sequence": sequence,
                    "releases": [{"id": "backend-" + plan["version"] + "-" + arch, "version": plan["version"], "target": "backend", "manager_protocol": 2, "url": package_url, "size": package["size"], "sha256": package["sha256"], "notes": notes}]}
            payload = candidate / ("backend-" + arch + ".payload.json")
            _write_new(payload, canonical(feed))
            feed_signature = backend_signer.sign(payload)
            verify_ed25519(plan["backend_public_key"], feed_signature, payload)
            feed_name, appcast_name = "backend-" + arch + ".json", "appcast-" + arch + ".xml"
            _write_new(candidate / feed_name, canonical(_envelope(payload.read_bytes(), feed_signature)) + b"\n")
            payload.unlink()
            _write_new(candidate / appcast_name, _appcast(receipt, plan["origin"] + "/app-updates/" + release_id + "/" + arch, signature, notes, now))
            # The authenticated tool also signs the appcast itself. The signed
            # archive is independently verified using the bundled trust key.
            sparkle_signer.sign_appcast(candidate / appcast_name)
            for name in (dmg_name, package_name, feed_name, appcast_name):
                files[name] = {"sha256": digest(candidate / name), "size": (candidate / name).stat().st_size}
                if name == package_name:
                    routes["/releases/" + release_id + "/" + name] = name
            routes["/updates/" + arch + "/backend.json"] = feed_name
            routes["/updates/" + arch + "/appcast.xml"] = appcast_name
            portals[arch] = {"prefix": "/downloads/" + release_id + "/" + arch, "file": dmg_name, "sha256": receipt["sha256"]}
        manifest = {**plan, "sequence": sequence, "release_id": release_id, "published_at": now, "expires_at": now + lifetime_days * 86400,
                    "files": files, "routes": routes, "portals": portals, "refreshed_from": previous.get("release_id") if refresh else None, "production_acceptance": "operator-declared-for-exact-signed-dmg"}
        _write_new(candidate / "publication.json", canonical(manifest) + b"\n")
        # State and artifacts are renamed on the same filesystem; a crash before
        # the pointer commit leaves an immutable orphan for explicit review.
        os.rename(candidate, final)
        temporary = state / "current.next.json"
        _write_new(temporary, canonical(manifest) + b"\n")
        os.replace(temporary, current_path)
        descriptor = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return {"published": True, "release_id": release_id, "sequence": sequence, "version": plan["version"], "directory": str(final), "manifest_sha256": digest(final / "publication.json"), "consumer_acceptance": "operator-declared", "invitations_sent": 0}


def _verified_publication(state: Path, manifest: dict) -> tuple[Path, dict]:
    release_id = manifest.get("release_id")
    if not isinstance(release_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", release_id):
        raise PublicationError("Identificador de publicação inválido")
    root = Path(state) / "releases" / release_id
    if read_json(root / "publication.json", private=True) != manifest:
        raise PublicationError("Estado público difere do manifesto imutável")
    identities = {}
    files = manifest.get("files")
    offered_architectures = {item.get("architecture") for item in manifest.get("artifacts", []) if isinstance(item, dict)}
    if not isinstance(files, dict) or not offered_architectures or not offered_architectures.issubset(ARCHITECTURES) or len(files) != 4 * len(offered_architectures):
        raise PublicationError("Inventário de publicação incompleto")
    for name, entry in files.items():
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", name) or not isinstance(entry, dict):
            raise PublicationError("Arquivo de publicação inválido")
        path = _regular(root / name)
        info = path.stat()
        if info.st_size != entry.get("size") or digest(path) != entry.get("sha256"):
            raise PublicationError("Artefato publicado difere dos bytes aprovados; serviço pausado")
        identities[name] = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    return root, identities


def create_release_distribution_app(state: Path, invitation_state: Path) -> FastAPI:
    """Serve only the reviewed update files and invitation-gated portals.

    Old immutable portal paths keep interrupted downloads valid after a new
    release. The current pointer is loaded only at restart, so deployment plans
    explicitly include a service restart after a reviewed publication.
    """
    state = _private_directory(state)
    invitation_state = _private_directory(invitation_state)
    manifest = read_json(state / "current.json", private=True)
    root, identities = _verified_publication(state, manifest)
    app = FastAPI(title="Mia · Demonstração", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.publication = manifest
    routes = {}
    # Retain only complete historical manifests. Any malformed candidate stops
    # startup instead of silently serving guessed artifacts.
    for release in sorted((state / "releases").iterdir()):
        if release.is_symlink() or not release.is_dir():
            raise PublicationError("Diretório de releases contém entrada inesperada")
        previous = read_json(release / "publication.json", private=True)
        previous_root, previous_identities = _verified_publication(state, previous)
        for route, name in previous["routes"].items():
            if route.startswith("/releases/"):
                routes[route] = (previous_root / name, previous_identities[name], previous["files"][name]["sha256"])
        for arch, portal in previous["portals"].items():
            if arch not in ARCHITECTURES or not re.fullmatch(r"/downloads/[A-Za-z0-9._-]+/(arm64|x86_64)", portal.get("prefix", "")) or portal.get("file") != "Mia-" + arch + ".dmg" or portal.get("sha256") != previous["files"][portal["file"]]["sha256"]:
                raise PublicationError("Portal de arquitetura difere dos artefatos aprovados")
            app.mount(portal["prefix"], create_distribution_app(invitation_state, previous_root / portal["file"], sha256=portal["sha256"], url_prefix=portal["prefix"]))
    for route, name in manifest["routes"].items():
        if route.startswith("/updates/") and route.endswith("/backend.json"):
            routes[route] = (root / name, identities[name], manifest["files"][name]["sha256"])

    @app.middleware("http")
    async def no_query_secrets(request: Request, call_next):
        if request.url.query:
            return JSONResponse({"detail": "Parâmetros de URL não são aceitos"}, status_code=400)
        response = await call_next(request)
        response.headers.update({"Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY"})
        return response

    @app.get("/health")
    def health():
        return {"ok": True, "service": "mia-demo-distribution", "release_id": manifest["release_id"], "sequence": manifest["sequence"]}

    @app.get("/", response_class=HTMLResponse)
    @app.get("/invite", response_class=HTMLResponse)
    def landing():
        # The fragment is moved only after the participant chooses an arch. It
        # never reaches HTTP logs, query strings, an external resource or server.
        choices = "".join('<li><a class="architecture" href="' + html.escape(manifest["portals"][arch]["prefix"]) + '/invite">' + label + "</a></li>" for arch, label in (("arm64", "Mac com chip Apple (M1 ou posterior)"), ("x86_64", "Mac com processador Intel")) if arch in manifest["portals"])
        body = '<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Mia · Revisão local</title><main><h1>Ensaio privado da distribuição Mia</h1><p>Este servidor loopback confere os arquivos preparados. A distribuição beta e as atualizações oficiais usam o serviço Vercel autenticado.</p><p>Escolha seu Mac. Veja o chip em  → Sobre Este Mac.</p><ul>' + choices + '</ul></main><script>const token=location.hash;if(token)history.replaceState(null,"",location.pathname);for(const link of document.querySelectorAll(".architecture"))link.href+=token;</script></html>'
        script = body[body.index("<script>") + 8:body.index("</script>")].encode()
        csp_hash = base64.b64encode(hashlib.sha256(script).digest()).decode()
        return HTMLResponse(body, headers={"Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; script-src 'sha256-" + csp_hash + "'; base-uri 'none'; frame-ancestors 'none'"})

    @app.get("/{path:path}")
    def release_file(path: str):
        if path.startswith("updates/") and path.endswith("/appcast.xml"):
            raise HTTPException(401, "Atualizações oficiais exigem ativação beta no serviço Vercel")
        matched = routes.get("/" + path)
        if matched is None:
            raise HTTPException(404, "Arquivo de demonstração não encontrado")
        target, identity, sha = matched
        try:
            target = _regular(target)
            info = target.stat()
        except PublicationError:
            raise HTTPException(503, "Publicação pausada; artefato mudou") from None
        if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != identity:
            raise HTTPException(503, "Publicação pausada; artefato mudou")
        mutable = path.startswith("updates/")
        return FileResponse(target, media_type="application/rss+xml" if target.suffix == ".xml" else "application/json" if target.suffix == ".json" else "application/octet-stream", headers={"Cache-Control": "no-cache" if mutable else "public, max-age=31536000, immutable", "ETag": '"' + sha + '"'})
    return app
