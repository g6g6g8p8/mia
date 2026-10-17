"""Authenticated backend updates; native Sparkle owns application replacement.

No default publisher or key is invented. Feed signatures cover the exact payload,
including artifact hash, size, compatibility and destination. Preparation never
executes a downloaded file; activation delegates to the installation's reviewed
manager and stable runtime with its snapshot/recovery transaction.
"""
from __future__ import annotations

import base64
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import ssl
import stat
import struct
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from mia import __version__
from mia.operations import OperationError, _read, _write

MAX_FEED = 2 * 1024**2
MAX_ARTIFACT = 512 * 1024**2
MAX_EXPANDED = 1024**3


class UpdateError(OperationError):
    pass


def _version(value: str) -> tuple:
    matched = re.fullmatch(r"(\d{1,4})\.(\d{1,4})\.(\d{1,4})(?:(a|b|rc)(\d{1,6}))?", value)
    if not matched:
        raise UpdateError("Formato de versão não suportado pelo canal de demonstração")
    return (int(matched[1]), int(matched[2]), int(matched[3]), {"a": 0, "b": 1, "rc": 2, None: 3}[matched[4]], int(matched[5] or 0))


def _json(data: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise UpdateError("Manifesto contém campos duplicados")
            result[key] = value
        return result
    try:
        value = json.loads(data, object_pairs_hook=unique)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise UpdateError("Manifesto de atualização inválido") from None


def _https(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError
        if any(ord(c) < 33 or ord(c) == 127 for c in value) or "\\" in value:
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise UpdateError("Canal de atualização exige HTTPS sem credenciais ou parâmetros") from None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise UpdateError("Redirecionamento de atualização recusado")


def _fetch(url: str, target: Path, limit: int, expected_size: int | None = None) -> None:
    opener = urllib.request.build_opener(_NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    request = urllib.request.Request(_https(url), headers={"User-Agent": "Mia-Update/1", "Accept-Encoding": "identity"})
    deadline, total = time.monotonic() + 120, 0
    try:
        with opener.open(request, timeout=15) as response, target.open("xb") as output:
            target.chmod(0o600)
            if response.status != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
                raise UpdateError("Resposta de atualização incompatível")
            declared = response.headers.get("Content-Length")
            if declared is not None and (not declared.isdecimal() or int(declared) > limit or expected_size is not None and int(declared) != expected_size):
                raise UpdateError("Tamanho da atualização difere do manifesto")
            while True:
                if time.monotonic() > deadline:
                    raise UpdateError("Download excedeu o prazo; tente novamente")
                block = response.read(min(256 * 1024, limit + 1 - total))
                if not block:
                    break
                total += len(block)
                if total > limit:
                    raise UpdateError("Download excedeu o limite da atualização")
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
        if not total or expected_size is not None and total != expected_size:
            raise UpdateError("Download incompleto; tente novamente")
    except UpdateError:
        raise
    except (OSError, urllib.error.URLError):
        raise UpdateError("Não foi possível baixar a atualização por HTTPS") from None


def _decode(value: str, size: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
        if len(decoded) != size:
            raise ValueError
        return decoded
    except (ValueError, TypeError):
        raise UpdateError("Chave ou assinatura de atualização inválida") from None


def validate_channel(channel: dict) -> dict:
    """Validate only public release trust configuration, usable by the builder."""
    if not isinstance(channel, dict) or channel.get("protocol") != 1:
        raise UpdateError("Protocolo do canal de atualização incompatível")
    if not isinstance(channel.get("channel"), str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,40}", channel["channel"]):
        raise UpdateError("Nome do canal de atualização inválido")
    allowed = {"protocol", "channel", "backend_feed_url", "backend_public_key", "appcast_url", "sparkle_public_key", "distribution_url", "beta_access_required"}
    if set(channel) - allowed:
        raise UpdateError("Configuração do canal contém campos não permitidos")
    for url_field, key_field in (("backend_feed_url", "backend_public_key"), ("appcast_url", "sparkle_public_key")):
        if bool(channel.get(url_field)) != bool(channel.get(key_field)):
            raise UpdateError("Canal de atualização precisa de endereço e chave pública juntos")
        if channel.get(url_field):
            _https(channel[url_field])
            _decode(channel[key_field], 32)
    if "beta_access_required" in channel and type(channel["beta_access_required"]) is not bool:
        raise UpdateError("Política de acesso beta deve ser booleana")
    if "distribution_url" in channel:
        _https(channel["distribution_url"])
        parsed = urllib.parse.urlsplit(channel["distribution_url"])
        if any(part in (".", "..") for part in parsed.path.split("/")) or "%" in parsed.path:
            raise UpdateError("Endereço da distribuição contém caminho não permitido")
    if channel.get("beta_access_required"):
        if not channel.get("distribution_url") or not channel.get("appcast_url"):
            raise UpdateError("Canal privado beta exige distribuição e appcast configurados")
        distribution = urllib.parse.urlsplit(channel["distribution_url"])
        appcast = urllib.parse.urlsplit(channel["appcast_url"])
        if (appcast.scheme, appcast.hostname, appcast.port or 443) != (distribution.scheme, distribution.hostname, distribution.port or 443) or not appcast.path.startswith(distribution.path.rstrip("/") + "/"):
            raise UpdateError("Appcast privado deve pertencer à distribuição autorizada")
    return channel


def _verify_signature(resources: Path, public_key: str, signature: str, payload: Path) -> None:
    key, sig = _decode(public_key, 32), _decode(signature, 64)
    if payload.stat().st_size > MAX_FEED:
        raise UpdateError("Manifesto de atualização excedeu o limite")
    if sys.platform == "darwin":
        helper = resources.parent / "MacOS/Mia"
        if not helper.is_file() or helper.is_symlink():
            raise UpdateError("Verificador nativo de atualização indisponível")
        arguments = [str(helper), "--verify-ed25519", public_key, signature, str(payload)]
        try:
            result = subprocess.run(arguments, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            raise UpdateError("Verificador nativo de atualização indisponível") from None
        if result.returncode:
            raise UpdateError("Assinatura da atualização não é válida")
        return
    # OpenSSL's Ed25519 implementation is only the non-Mac standard tool path;
    # official macOS artifacts use CryptoKit in the code-signed native binary.
    with tempfile.TemporaryDirectory() as temporary:
        keyfile, sigfile = Path(temporary) / "key.der", Path(temporary) / "signature"
        keyfile.write_bytes(bytes.fromhex("302a300506032b6570032100") + key)
        sigfile.write_bytes(sig)
        try:
            result = subprocess.run(["/usr/bin/openssl", "pkeyutl", "-verify", "-rawin", "-pubin", "-inkey", str(keyfile),
                "-keyform", "DER", "-sigfile", str(sigfile), "-in", str(payload)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            raise UpdateError("Verificador de atualização indisponível") from None
        if result.returncode:
            raise UpdateError("Assinatura da atualização não é válida")


def _private(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink():
            raise UpdateError("Atualização não aceita caminhos com links simbólicos")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise UpdateError("Estado da atualização precisa ser privado (0700)")


def _extract(package: Path, destination: Path) -> None:
    if destination.exists():
        raise UpdateError("Preparação anterior preservada; descarte-a explicitamente antes de repetir")
    if package.is_symlink() or not package.is_file() or package.stat().st_size > MAX_ARTIFACT:
        raise UpdateError("Pacote não é arquivo regular limitado")
    # Preflight the bounded central directory before ZipFile allocates every
    # descriptor. ZIP64/multidisk are unnecessary for the offered 512MiB package.
    size = package.stat().st_size
    with package.open("rb") as source:
        source.seek(max(0, size - 65557))
        tail = source.read(65557)
    position = tail.rfind(b"PK\x05\x06")
    if position < 0 or len(tail) - position < 22:
        raise UpdateError("Diretório do pacote inválido")
    _, disk, cd_disk, disk_count, count, cd_size, cd_offset, comment = struct.unpack("<4s4H2IH", tail[position:position + 22])
    eocd_offset = size - len(tail) + position
    if disk or cd_disk or disk_count != count or not 1 <= count <= 30000 or cd_size > 8 * 1024**2 or cd_offset + cd_size != eocd_offset or position + 22 + comment != len(tail):
        raise UpdateError("Diretório do pacote excedeu o limite ou é incompatível")
    try:
        with zipfile.ZipFile(package) as archive:
            records = archive.infolist()
            if not records or len(records) > 30000 or sum(r.file_size for r in records) > MAX_EXPANDED:
                raise UpdateError("Pacote de atualização excedeu o limite")
            seen = set()
            for record in records:
                path = PurePosixPath(record.filename)
                mode = record.external_attr >> 16
                components = record.filename.rstrip("/").split("/")
                if not record.filename or "\\" in record.filename or "\x00" in record.filename or path.is_absolute() or any(p in ("..", ".", "") for p in components):
                    raise UpdateError("Pacote contém caminho inseguro")
                if len(record.filename) > 512 or len(path.parts) > 32 or path.parts[0] not in ("source", "wheelhouse", "update.json"):
                    raise UpdateError("Pacote contém caminho não permitido")
                if record.flag_bits & 1 or stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise UpdateError("Pacote contém arquivo especial, criptografado ou link")
                if path.as_posix().casefold() in seen or any(p in (".env", ".git", "data", "__pycache__") for p in path.parts):
                    raise UpdateError("Pacote contém arquivo duplicado ou privado")
                if path.parts[0] == "wheelhouse" and not record.is_dir() and (len(path.parts) != 2 or path.suffix != ".whl"):
                    raise UpdateError("Wheelhouse contém arquivo não permitido")
                seen.add(path.as_posix().casefold())
            destination.mkdir(mode=0o700)
            for record in records:
                target = destination.joinpath(*PurePosixPath(record.filename).parts)
                if record.is_dir():
                    target.mkdir(parents=True, mode=0o700, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                with archive.open(record) as source, target.open("xb") as output:
                    target.chmod(0o600)
                    shutil.copyfileobj(source, output, length=256 * 1024)
    except (zipfile.BadZipFile, OSError, RuntimeError):
        raise UpdateError("Pacote de atualização inválido; preparação preservada") from None


class UpdateController:
    def __init__(self, resources: Path, home: Path | None = None):
        self.resources = Path(resources).resolve()
        self.base = Path(home or Path.home()) / "Library/Application Support/Mia"
        self.root = self.base / "installation"
        self.state = self.base / "updates"

    def _channel(self) -> dict:
        path = self.resources / "release-channel.json"
        if not path.exists():
            return {}
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024:
            raise UpdateError("Configuração do canal de atualização inválida")
        return validate_channel(_json(path.read_bytes()))

    @contextlib.contextmanager
    def _lock(self):
        _private(self.state)
        path = self.state / "update.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w") as output:
            try:
                fcntl.flock(output, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise UpdateError("Há outra atualização em andamento") from None
            yield

    def _read_state(self, name: str) -> dict:
        if any(p.is_symlink() for p in (self.state, *self.state.parents)):
            raise UpdateError("Estado da atualização não aceita links simbólicos")
        path = self.state / name
        if not path.exists():
            return {}
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FEED:
            raise UpdateError("Estado da atualização inválido")
        return _json(path.read_bytes())

    def _base_result(self) -> dict:
        channel = self._channel()
        active = _read(self.root / "active.json") if (self.root / "installation.json").is_file() else {}
        return {"app_version": __version__, "backend_version": active.get("version"),
            "channel": channel.get("channel"), "app_update_channel_configured": bool(channel.get("appcast_url")),
            "scope": "backend", "app_updated": False, "manager_updated": False, "runtime_updated": False}

    def _status(self) -> dict:
        result, channel = self._base_result(), self._channel()
        journal = self._read_state("journal.json")
        pending = (self.root / "journal.json").exists() or (self.root / "migration-pending.json").exists()
        if pending or journal.get("phase") == "applying":
            return {**result, "state": "recovery_required", "summary": "Atualização interrompida. Os dados e snapshots estão preservados; recupere antes de continuar."}
        if journal.get("phase") == "prepared":
            return {**result, "state": "prepared", "release": journal["release"], "plan_sha256": journal["plan_sha256"],
                "details": journal["plan"], "plan": journal["plan"],
                "summary": "Backend preparado e autenticado. Um snapshot preservará a biblioteca antes da troca; app, runtime e gerenciador mantêm suas versões."}
        if journal.get("phase") in ("downloading", "failed"):
            return {**result, "state": "interrupted", "summary": "Preparação incompleta preservada. Descarte o download e tente novamente; a biblioteca não foi alterada."}
        if not channel.get("backend_feed_url"):
            return {**result, "state": "unconfigured", "summary": "O canal oficial de atualização do backend ainda não foi configurado. Seus dados continuam disponíveis."}
        feed = self._read_state("releases.json")
        releases = self._available(feed.get("releases", []), result.get("backend_version"))
        return {**result, "state": "available" if releases else "idle", "releases": releases,
            "summary": "Há versões autenticadas para revisar." if releases else "Nenhuma versão posterior do backend está disponível no manifesto consultado." if feed else "Nenhuma atualização do backend foi consultada. Atualização do app é gerida pelo canal nativo."}

    @staticmethod
    def _available(releases: list, current: str | None) -> list:
        return [release for release in releases if current is None or _version(release["version"]) > _version(current)]

    def _check(self) -> dict:
        channel = self._channel()
        if not channel.get("backend_feed_url"):
            return self._status()
        downloaded = self.state / "feed.download"
        downloaded.unlink(missing_ok=True)
        _fetch(channel["backend_feed_url"], downloaded, MAX_FEED)
        envelope = _json(downloaded.read_bytes())
        try:
            payload = base64.b64decode(envelope["payload"], validate=True)
        except (KeyError, ValueError, TypeError):
            raise UpdateError("Manifesto assinado inválido") from None
        if len(payload) > MAX_FEED:
            raise UpdateError("Manifesto excedeu o limite")
        verified = self.state / "feed.payload"
        verified.write_bytes(payload)
        verified.chmod(0o600)
        _verify_signature(self.resources, channel["backend_public_key"], envelope.get("signature"), verified)
        feed = _json(payload)
        now = int(time.time())
        if feed.get("protocol") != 1 or feed.get("channel") != channel.get("channel") or not isinstance(feed.get("expires_at"), int) or feed["expires_at"] <= now:
            raise UpdateError("Manifesto expirado ou incompatível com o canal")
        if feed["expires_at"] > now + 30 * 86400 or not isinstance(feed.get("sequence"), int) or isinstance(feed["sequence"], bool) or feed["sequence"] < 1:
            raise UpdateError("Prazo ou sequência do manifesto inválido")
        previous = self._read_state("releases.json")
        if feed["sequence"] < previous.get("sequence", 0):
            raise UpdateError("Manifesto antigo recusado")
        releases = feed.get("releases")
        if not isinstance(releases, list) or len(releases) > 20:
            raise UpdateError("Lista de versões inválida")
        seen = set()
        for release in releases:
            if not isinstance(release, dict) or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", str(release.get("id", ""))) or release["id"] in seen:
                raise UpdateError("Identificador de versão inválido")
            if release.get("target") != "backend":
                raise UpdateError("Substituição do app exige o canal nativo de atualização")
            if not re.fullmatch(r"[A-Za-z0-9.+_-]{1,80}", str(release.get("version", ""))) or not isinstance(release.get("notes", ""), str) or len(release.get("notes", "")) > 8000:
                raise UpdateError("Informação de versão inválida")
            _version(release["version"])
            if not isinstance(release.get("size"), int) or isinstance(release["size"], bool) or not 1 <= release["size"] <= MAX_ARTIFACT:
                raise UpdateError("Tamanho de pacote inválido")
            if not re.fullmatch(r"[a-f0-9]{64}", str(release.get("sha256", ""))) or release.get("manager_protocol") != 2:
                raise UpdateError("Compatibilidade ou hash do pacote inválido")
            _https(release.get("url"))
            seen.add(release["id"])
        _write(self.state / "releases.json", feed)
        result = self._base_result()
        available = self._available(releases, result.get("backend_version"))
        return {**result, "state": "available" if available else "idle", "releases": available,
            "summary": "Versões autenticadas disponíveis para revisão." if available else "Nenhuma versão posterior do backend está disponível neste canal."}

    def _prepare(self, payload: dict) -> dict:
        journal = self._read_state("journal.json")
        if payload.get("discard") is True:
            if journal.get("phase") == "applying" or (self.root / "journal.json").exists():
                raise UpdateError("Atualização iniciada exige recuperação; não pode ser descartada")
            for name in ("artifact.zip", "artifact.download"):
                (self.state / name).unlink(missing_ok=True)
            package = self.state / "package"
            if package.is_symlink():
                raise UpdateError("Preparação não aceita link simbólico")
            if package.exists():
                shutil.rmtree(package)
            (self.state / "journal.json").unlink(missing_ok=True)
            return self._status()
        if journal:
            raise UpdateError("Há uma preparação preservada; revise, recupere ou descarte antes de repetir")
        feed = self._read_state("releases.json")
        self._verify_cached(feed)
        if feed.get("expires_at", 0) <= int(time.time()):
            raise UpdateError("Consulte o canal antes de preparar uma atualização")
        release = next((r for r in feed.get("releases", []) if r["id"] == payload.get("release_id")), None)
        if not release:
            raise UpdateError("Versão não encontrada no manifesto autenticado")
        current = self._base_result().get("backend_version")
        if current and _version(release["version"]) <= _version(current):
            raise UpdateError("O backend ativo já usa esta versão ou uma posterior. Recuperação usa snapshots, não instala versões antigas sobre seus dados.")
        journal = {"phase": "downloading", "release": release}
        _write(self.state / "journal.json", journal)
        temporary, artifact = self.state / "artifact.download", self.state / "artifact.zip"
        try:
            _fetch(release["url"], temporary, MAX_ARTIFACT, release["size"])
            with temporary.open("rb") as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != release["sha256"]:
                    raise UpdateError("Pacote difere da versão assinada; nada foi executado")
            os.rename(temporary, artifact)
            _extract(artifact, self.state / "package")
            manifest_path = self.state / "package/update.json"
            if not manifest_path.is_file() or manifest_path.stat().st_size > 16384:
                raise UpdateError("Pacote não contém manifesto compatível")
            manifest = _json(manifest_path.read_bytes())
            if manifest.get("protocol") != 1 or manifest.get("target") != "backend" or manifest.get("version") != release["version"]:
                raise UpdateError("Pacote não corresponde à versão revisada")
            if manifest.get("manager_protocol") != 2 or manifest.get("runtime_changed") is not False or manifest.get("manager_changed") is not False:
                raise UpdateError("Mudanças de runtime ou gerenciador exigem atualização coordenada do app")
            if not (self.state / "package/source/pyproject.toml").is_file() or not (self.state / "package/wheelhouse").is_dir():
                raise UpdateError("Pacote offline incompleto")
            metadata_file = self.state / "package/source/pyproject.toml"
            if metadata_file.stat().st_size > 65536:
                raise UpdateError("Manifesto do pacote excedeu o limite")
            try:
                metadata = tomllib.loads(metadata_file.read_text())["project"]
                if metadata.get("name") != "mia-personal-ai" or metadata.get("version") != release["version"]:
                    raise ValueError
            except (ValueError, KeyError):
                raise UpdateError("Fonte do backend não corresponde à versão autenticada") from None
            plan = {"release_id": release["id"], "sha256": release["sha256"], "version": release["version"], "target": "backend",
                "installation": str(self.root), "current_backend_version": current, "installation_state_sha256": self._installation_fingerprint(),
                "snapshot_required": True, "app_updated": False, "runtime_updated": False, "manager_updated": False}
            plan_hash = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            _write(self.state / "journal.json", {**journal, "phase": "prepared", "plan": plan, "plan_sha256": plan_hash})
        except Exception:
            _write(self.state / "journal.json", {**journal, "phase": "failed"})
            raise
        return self._status()

    def _installation_fingerprint(self) -> str:
        digest = hashlib.sha256()
        for name in ("installation.json", "active.json"):
            path = self.root / name
            if path.is_symlink():
                raise UpdateError("Estado da instalação não aceita link simbólico")
            digest.update(name.encode())
            if path.exists():
                if not path.is_file() or path.stat().st_size > 65536:
                    raise UpdateError("Estado da instalação inválido")
                digest.update(path.read_bytes())
        return digest.hexdigest()

    def _verify_cached(self, feed: dict) -> None:
        channel = self._channel()
        envelope = self._read_state("feed.download")
        try:
            payload = base64.b64decode(envelope["payload"], validate=True)
        except (KeyError, ValueError, TypeError):
            raise UpdateError("Consulte novamente o manifesto autenticado") from None
        if len(payload) > MAX_FEED or _json(payload) != feed or feed.get("expires_at", 0) <= int(time.time()):
            raise UpdateError("Manifesto preparado mudou ou expirou; consulte novamente o canal")
        if feed.get("protocol") != 1 or feed.get("channel") != channel.get("channel") or not channel.get("backend_feed_url"):
            raise UpdateError("O canal oficial mudou; consulte o novo canal antes de preparar ou atualizar")
        verified = self.state / "feed.payload"
        if verified.is_symlink():
            raise UpdateError("Manifesto não aceita link simbólico")
        verified.write_bytes(payload)
        verified.chmod(0o600)
        _verify_signature(self.resources, channel.get("backend_public_key"), envelope.get("signature"), verified)

    def _manager(self, action: str, extra: list[str]) -> dict:
        config = _read(self.root / "installation.json")
        manager = self.root / "manager.py"
        if config.get("manager_protocol") != 2 or manager.is_symlink() or not manager.is_file():
            raise UpdateError("Gerenciador não é compatível; atualize o app de forma coordenada")
        if config.get("manager_sha256") != hashlib.sha256(manager.read_bytes()).hexdigest():
            raise UpdateError("Gerenciador difere da instalação revisada")
        python = Path(config.get("python", ""))
        if not python.is_absolute() or not python.is_file() or not python.resolve().is_relative_to(self.base.resolve()):
            raise UpdateError("Runtime da instalação não é o runtime privado gerenciado")
        _private(self.root)
        log = self.state / "operation.log"
        with log.open("ab") as output:
            log.chmod(0o600)
            try:
                result = subprocess.run([str(python), "-I", str(manager), "--root", str(self.root), action, *extra],
                    stdout=output, stderr=output, timeout=600, env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL")})
            except (OSError, subprocess.TimeoutExpired):
                raise UpdateError("Operação interrompida. Preserve os dados e execute recuperação.") from None
        if result.returncode:
            raise UpdateError("Atualização não foi concluída. O gerenciador preservou o estado e os snapshots; confira a recuperação.")
        active = _read(self.root / "active.json")
        return {"version": active.get("version"), "recovery_required": (self.root / "journal.json").exists()}

    def _apply(self, payload: dict) -> dict:
        journal = self._read_state("journal.json")
        if journal.get("phase") != "prepared" or not payload.get("approve_sha256") or payload["approve_sha256"] != journal.get("plan_sha256"):
            raise UpdateError("Atualização exige aprovação do plano preparado atual")
        feed = self._read_state("releases.json")
        self._verify_cached(feed)
        if journal.get("release") not in feed.get("releases", []):
            raise UpdateError("Preparação não corresponde ao manifesto autenticado")
        if hashlib.sha256(json.dumps(journal.get("plan"), sort_keys=True, separators=(",", ":")).encode()).hexdigest() != journal["plan_sha256"]:
            raise UpdateError("Plano preparado mudou; atualização recusada")
        if journal["plan"].get("installation_state_sha256") != self._installation_fingerprint():
            raise UpdateError("Instalação mudou após a revisão; prepare um novo plano antes de atualizar")
        artifact = self.state / "artifact.zip"
        if artifact.is_symlink() or not artifact.is_file():
            raise UpdateError("Pacote preparado não é arquivo regular")
        with artifact.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != journal["release"]["sha256"]:
                raise UpdateError("Pacote preparado mudou; atualização recusada")
        # Re-extract from the authenticated binary instead of trusting writable
        # previously-extracted executable files between review and activation.
        package = self.state / "package"
        if package.is_symlink():
            raise UpdateError("Preparação não aceita link simbólico")
        shutil.rmtree(package)
        _extract(artifact, package)
        _write(self.state / "journal.json", {**journal, "phase": "applying"})
        result = self._manager("update", ["--source", str(package / "source"), "--wheelhouse", str(package / "wheelhouse"), "--offline"])
        if result["version"] != journal["release"]["version"] or result["recovery_required"]:
            raise UpdateError("Versão ativa não corresponde à atualização; recuperação necessária")
        _write(self.state / "last-update.json", {**journal, "phase": "applied_backend"})
        (self.state / "journal.json").unlink()
        return {**self._base_result(), "state": "applied_backend", "summary": "Backend atualizado com snapshot e verificação de saúde. App, runtime e gerenciador mantêm suas versões."}

    def handle(self, action: str, payload: dict) -> dict:
        if action not in ("updates_status", "updates_check", "updates_prepare", "updates_apply", "updates_recover") or not isinstance(payload, dict):
            raise UpdateError("Ação de atualização não suportada")
        allowed = {"updates_status": set(), "updates_check": set(), "updates_prepare": {"release_id", "discard"}, "updates_apply": {"approve_sha256"}, "updates_recover": set()}[action]
        if set(payload) - allowed:
            raise UpdateError("Parâmetros de atualização não permitidos")
        if action == "updates_status":
            return self._status()
        with self._lock():
            if action == "updates_check":
                return self._check()
            if action == "updates_prepare":
                return self._prepare(payload)
            if action == "updates_apply":
                return self._apply(payload)
            journal = self._read_state("journal.json")
            pending = (self.root / "journal.json").exists() or (self.root / "migration-pending.json").exists()
            if journal.get("phase") != "applying" and not pending:
                if journal:
                    raise UpdateError("A preparação não alterou a instalação. Revise ou descarte o download; recuperação não é necessária.")
                return {**self._base_result(), "state": "idle", "summary": "Nenhuma recuperação de atualização está pendente."}
            self._manager("recover", [])
            if journal:
                _write(self.state / "recovered.json", {**journal, "phase": "recovered"})
                (self.state / "journal.json").unlink()
            return {**self._base_result(), "state": "recovered", "summary": "Gerenciador recuperou a instalação em dados preservados. O app não foi substituído."}
