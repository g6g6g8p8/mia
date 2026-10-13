"""Conscious native operations. No shell execution or browser-triggered commands.

The manager uses only the standard library so recovery does not depend on an
importable application or a usable database schema. Private state stays outside
the source checkout. Supported platforms are Unix (macOS and Linux).
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.request
import uuid


BOOTSTRAP = ("pip==25.0.1", "setuptools==75.8.0", "wheel==0.45.1")
CONTROLLED_ENV = {"MIA_DATA_DIR", "MIA_OPERATIONS_ROOT", "MIA_BIND"}


class OperationError(RuntimeError):
    pass


def _sync(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path: Path, value: dict) -> None:
    fd, name = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        _sync(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def _read(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _copy_private(source: Path, target: Path) -> None:
    """Copy regular files only; never follow user-controlled links."""
    if source.is_symlink() or not source.is_dir():
        raise OperationError("A origem deve ser um diretório real, sem links")
    target.mkdir(mode=0o700)
    for path in sorted(source.iterdir()):
        output = target / path.name
        if path.is_symlink():
            raise OperationError("Links simbólicos não são aceitos nos dados/configuração")
        if path.is_dir():
            _copy_private(path, output)
        elif path.is_file():
            with path.open("rb") as incoming, output.open("xb") as outgoing:
                os.chmod(output, 0o600)
                shutil.copyfileobj(incoming, outgoing)
                outgoing.flush()
                os.fsync(outgoing.fileno())
        else:
            raise OperationError("Arquivo especial não é aceito em snapshots")
    _sync(target)


def _manifest(directory: Path) -> dict:
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise OperationError("Snapshot contém link simbólico")
        if path.is_file() and path != directory / "snapshot.json":
            with path.open("rb") as handle:
                result[str(path.relative_to(directory))] = hashlib.file_digest(handle, "sha256").hexdigest()
    return result


def _birth(pid: int) -> str | None:
    try:
        path = Path(f"/proc/{pid}/stat")
        if path.exists():
            # Names may contain spaces and parentheses; the final ')' ends comm.
            return "linux:" + path.read_text().rsplit(")", 1)[1].split()[19]
        output = subprocess.check_output(["ps", "-p", str(pid), "-o", "lstart="], text=True).strip()
        return "unix:" + output if output else None
    except (OSError, subprocess.CalledProcessError, IndexError):
        return None


@contextlib.contextmanager
def _lock(path: Path, *, blocking: bool = False):
    with path.open("a+") as handle:
        os.chmod(path, 0o600)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as error:
            raise OperationError("Outra operação/processo da Mia está em execução") from error
        try:
            yield handle
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _busy(path: Path) -> bool:
    try:
        with _lock(path):
            return False
    except OperationError:
        return True


def _validate_env(path: Path) -> None:
    # This file is parsed as configuration, never evaluated by a shell.
    if path.is_symlink() or not path.is_file():
        raise OperationError("Configuração deve ser um arquivo local regular")
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, separator, _ = line.partition("=")
            if not separator or not re.fullmatch(r"MIA_[A-Z0-9_]+", key.strip()) or key.strip() in CONTROLLED_ENV:
                raise OperationError("machine.env aceita somente variáveis MIA_; diretório e bind pertencem ao gerenciador")


class Manager:
    def __init__(self, root: Path):
        original = Path(root).expanduser()
        if original.is_symlink():
            raise OperationError("Diretório da instalação não pode ser link simbólico")
        self.root = original.resolve()

    def _check(self) -> None:
        if not (self.root / "installation.json").is_file():
            raise OperationError("Instalação gerenciada não encontrada")
        if self.root.stat().st_uid != os.getuid() or self.root.stat().st_mode & 0o077:
            raise OperationError("A instalação precisa pertencer ao usuário e ter permissão 0700")

    def _path(self, value: str) -> Path:
        path = (self.root / value).resolve()
        if not path.is_relative_to(self.root):
            raise OperationError("Estado aponta para fora da instalação")
        return path

    def active(self) -> dict:
        self._check()
        active = _read(self.root / "active.json")
        if not active:
            raise OperationError("Instalação incompleta; não há versão ativa")
        return active

    def _python(self, active: dict) -> Path:
        return self._path(active["release"]) / "venv/bin/python"

    def _pending(self) -> None:
        if (self.root / "journal.json").exists():
            raise OperationError("Operação interrompida: execute recover antes de iniciar/atualizar")

    def _release(self, source: Path, wheelhouse: Path | None = None, offline: bool = False) -> dict:
        source = source.resolve()
        if source.is_relative_to(self.root) or self.root.is_relative_to(source):
            raise OperationError("Fonte e instalação devem estar em diretórios separados")
        metadata = tomllib.loads((source / "pyproject.toml").read_text())["project"]
        version = metadata["version"]
        if metadata["name"] != "mia-personal-ai" or not re.fullmatch(r"[A-Za-z0-9._+-]{1,80}", version):
            raise OperationError("Fonte não é uma versão identificada da Mia")
        identity = version + "-" + uuid.uuid4().hex[:12]
        relative = "releases/" + identity
        release = self.root / relative
        release.mkdir(mode=0o700)
        code = release / "source"
        code.mkdir(mode=0o700)
        try:
            for name in ("pyproject.toml", "requirements.lock"):
                path = source / name
                if path.is_symlink() or not path.is_file():
                    raise OperationError("Manifesto/lockfile ausente ou não regular")
                shutil.copyfile(path, code / name)
            for path in sorted(source.iterdir()):
                if path.name == "README.md" or re.fullmatch(r"(?:LICENSE|NOTICE|THIRD_PARTY)[A-Za-z0-9_.-]*", path.name):
                    if path.is_symlink():
                        raise OperationError("Aviso de distribuição não é arquivo regular")
                    if path.is_dir() and path.name == "THIRD_PARTY_LICENSES":
                        _copy_private(path, code / path.name)
                    elif path.is_file():
                        shutil.copyfile(path, code / path.name)
                    else:
                        raise OperationError("Aviso de distribuição não é arquivo regular")
            # No .env, data, backups, credentials, tests or source history copied.
            package = code / "mia"
            package.mkdir(mode=0o700)
            for path in sorted((source / "mia").rglob("*")):
                if path.is_symlink():
                    raise OperationError("Fonte do pacote contém link simbólico")
                rel = path.relative_to(source / "mia")
                if "__pycache__" in rel.parts:
                    continue
                if path.is_file() and (path.suffix == ".py" or rel.parts[0] == "static"):
                    target = package / rel
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    shutil.copyfile(path, target)
            locked = (code / "requirements.lock").read_text().splitlines()
            if not locked or any(line.strip() and not line.startswith("#") and not re.fullmatch(r"[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9_.+!-]+", line.strip()) for line in locked):
                raise OperationError("requirements.lock deve fixar todas as versões, sem URLs ou opções")
            subprocess.run([sys.executable, "-m", "venv", str(release / "venv")], check=True)
            python = release / "venv/bin/python"
            arguments = []
            if wheelhouse:
                arguments += ["--find-links", str(wheelhouse.resolve())]
            if offline:
                if not wheelhouse:
                    raise OperationError("Instalação offline exige --wheelhouse")
                arguments += ["--no-index"]
            env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
            env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
            subprocess.run([str(python), "-m", "pip", "install", *arguments, *BOOTSTRAP], env=env, check=True)
            subprocess.run([str(python), "-m", "pip", "install", *arguments, "-r", str(code / "requirements.lock")], env=env, check=True)
            subprocess.run([str(python), "-m", "pip", "install", "--no-deps", "--no-build-isolation", str(code)], env=env, check=True)
            result = subprocess.check_output([str(python), "-I", "-c", "import mia; print(mia.__version__)"], cwd=self.root, text=True).strip()
            if result != version:
                raise OperationError("Versão do pacote instalado não corresponde ao manifesto")
            manifest = _manifest(code)
            _write(release / "release.json", {"version": version, "source_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()})
            _sync(release.parent)
            return {"release": relative, "version": version}
        except BaseException:
            shutil.rmtree(release)
            raise

    def install(self, source: Path, *, port: int = 8123, host: str = "127.0.0.1", env_file: Path | None = None, wheelhouse: Path | None = None, offline: bool = False) -> dict:
        if sys.version_info < (3, 12):
            raise OperationError("Python 3.12+ é necessário")
        ipaddress.ip_address(host)
        if not 1 <= port <= 65535:
            raise OperationError("Porta inválida")
        if self.root.exists():
            raise OperationError("Instalação exige um diretório novo; não sobrescreve arquivos existentes")
        if self.root.is_relative_to(source.resolve()):
            raise OperationError("Instalação deve ficar fora do checkout")
        if env_file:
            _validate_env(env_file)
        self.root.mkdir(parents=True, mode=0o700)
        for name in ("releases", "snapshots", "data", "history"):
            (self.root / name).mkdir(mode=0o700)
        (self.root / "data/initial").mkdir(mode=0o700)
        machine = self.root / "machine.env"
        machine.write_text(env_file.read_text() if env_file else "# Configuração privada desta instalação.\nMIA_AI_ENABLED=false\nMIA_COOKIE_SECURE=false\n")
        machine.chmod(0o600)
        shutil.copyfile(Path(__file__).resolve(), self.root / "manager.py")
        (self.root / "manager.py").chmod(0o600)
        _write(self.root / "installation.json", {"format": 1, "host": host, "port": port, "python": sys._base_executable})
        with _lock(self.root / "operation.lock"):
            release = self._release(source, wheelhouse, offline)
            _write(self.root / "active.json", {**release, "data": "data/initial"})
        return self.status()

    def _record(self) -> dict:
        record = _read(self.root / "process.json")
        if not record:
            return {}
        if not _busy(self.root / "service.lock"):
            return {}
        if record.get('birth') and _birth(record["pid"]) == record['birth']:
            return record
        # SIGKILL of the supervisor must not hide its still-running child.
        if record.get("child_pid") and record.get('child_birth') and _birth(record["child_pid"]) == record['child_birth']:
            return {**record, "pid": record["child_pid"], "birth": record["child_birth"]}
        return {}

    def status(self) -> dict:
        active = self.active()
        pending = _read(self.root / "journal.json")
        return {"managed": True, "version": active["version"], "release": Path(active["release"]).name,
                "running": bool(self._record()), "recovery_required": bool(pending),
                "operation": pending.get("phase"), "last_update": _read(self.root / "last-update.json").get("id"),
                "instructions": "Use o terminal desta instalação: status, stop, update, recover ou rollback. Atualização exige fonte local confiável; o navegador não executa comandos."}

    def _idle_database(self, active: dict) -> None:
        path = self._path(active["data"]) / "mia.db"
        if path.exists():
            with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
                if db.execute("SELECT 1 FROM runs WHERE state='running' LIMIT 1").fetchone():
                    raise OperationError("Há uma geração em andamento/interrompida. Aguarde ou reinicie a versão atual antes de atualizar")

    def _stop(self) -> None:
        record = self._record()
        if not record:
            if _busy(self.root / "service.lock"):
                raise OperationError("Processo sem identidade verificável; não foi enviado sinal")
            return
        # Birth identity plus held lock prevents signalling an unrelated reused PID.
        if not record.get('birth') or _birth(record["pid"]) != record["birth"]:
            raise OperationError("Identidade do processo mudou; parada recusada")
        os.kill(record["pid"], signal.SIGTERM)
        deadline = time.monotonic() + 20
        while _busy(self.root / "service.lock") and time.monotonic() < deadline:
            time.sleep(0.05)
        if _busy(self.root / "service.lock"):
            raise OperationError("Processo não parou; atualização não será executada")

    def stop(self) -> dict:
        self._check()
        with _lock(self.root / "operation.lock"):
            self._stop()
        return self.status()

    def service_template(self, *, kind: str) -> str:
        """Render only; never install, enable or change host services."""
        self._check()
        config = _read(self.root / "installation.json")
        arguments = [config["python"], str(self.root / "manager.py"), "--root", str(self.root), "serve"]
        if kind == "launchd":
            return plistlib.dumps({"Label": "local.mia", "ProgramArguments": arguments,
                                   "RunAtLoad": True, "KeepAlive": False, "ProcessType": "Background",
                                   "StandardOutPath": str(self.root / "service.log"), "StandardErrorPath": str(self.root / "service.log")}).decode()
        if kind != "systemd":
            raise OperationError("Serviço suportado: systemd ou launchd")
        def quote(value):
            if "\n" in value or "\r" in value:
                raise OperationError("Caminho com quebra de linha não é aceito em unidade systemd")
            return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$") + '"'
        return "[Unit]\nDescription=Mia personal AI (native)\n\n[Service]\nType=simple\nExecStart=" + " ".join(map(quote, arguments)) + "\nRestart=no\nTimeoutStopSec=25\nKillMode=control-group\nUMask=0077\n\n[Install]\nWantedBy=default.target\n"

    def _start(self, *, recovering: bool = False, operation_fd: int | None = None) -> None:
        if not recovering:
            self._pending()
        active = self.active()
        running = self._record()
        if not running and _busy(self.root / "service.lock"):
            raise OperationError("Processo em execução não tem identidade verificável")
        if running and any(running.get(key) != active[key] for key in ("release", "data", "version")):
            raise OperationError("Processo em execução não corresponde à versão e aos dados ativos")
        _validate_env(self.root / "machine.env")
        child = None
        if not running:
            with (self.root / "service.log").open("ab") as log:
                os.chmod(self.root / "service.log", 0o600)
                command = [_read(self.root / "installation.json")["python"], str(self.root / "manager.py"), "--root", str(self.root), "serve"]
                if recovering:
                    command += ["--recovery-id", _read(self.root / "journal.json")["id"]]
                if operation_fd is not None:
                    command += ["--operation-fd", str(operation_fd)]
                child = subprocess.Popen(command, cwd=self.root, stdout=log, stderr=log, start_new_session=True, pass_fds=(() if operation_fd is None else (operation_fd,)))
        installation = _read(self.root / "installation.json")
        address = installation["host"]
        address = "127.0.0.1" if address == "0.0.0.0" else "::1" if address == "::" else address
        host = f"[{address}]" if ":" in address else address
        origin = f"http://{host}:{installation['port']}"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if child and child.poll() is not None:
                raise OperationError("Inicialização falhou; veja service.log privado")
            record = self._record()
            if record and record.get("ready") and all(record.get(key) == active[key] for key in ("release", "data", "version")):
                try:
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with opener.open(origin + "/health", timeout=0.5) as response:
                        health = json.load(response)
                    with opener.open(origin + "/api/status", timeout=0.5) as response:
                        status = json.load(response)
                    if health.get("ok") is True and health.get("version") == active["version"] == status.get("version") and self._record() and (not child or child.poll() is None):
                        return
                except (OSError, ValueError):
                    pass
            time.sleep(0.05)
        self._stop()
        raise OperationError("Versão não ficou saudável por HTTP; atualização não foi confirmada")

    def start(self) -> dict:
        self._check()
        with _lock(self.root / "operation.lock") as operation:
            self._start(operation_fd=operation.fileno())
        return self.status()

    def serve(self, *, recovery_id: str | None = None, operation_fd: int | None = None) -> None:
        """Serialize startup with updates, then supervise one identifiable child."""
        self._check()
        with contextlib.ExitStack() as startup:
            if operation_fd is None:
                startup.enter_context(_lock(self.root / "operation.lock"))
            else:
                # A passed, already-held descriptor authorizes only the manager's
                # internal startup. It shares the updater's open file description.
                expected = (self.root / "operation.lock").stat()
                received = os.fstat(operation_fd)
                if (expected.st_dev, expected.st_ino) != (received.st_dev, received.st_ino):
                    raise OperationError("Descritor de operação inválido")
                try:
                    fcntl.flock(operation_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise OperationError("Outra operação está em execução") from error
                startup.callback(os.close, operation_fd)
            pending = _read(self.root / "journal.json")
            if pending and (operation_fd is None or pending.get("id") != recovery_id):
                self._pending()
            active = self.active()
            config = _read(self.root / "installation.json")
            _validate_env(self.root / "machine.env")
            with _lock(self.root / "service.lock") as service_lock:
                record = {"pid": os.getpid(), "birth": _birth(os.getpid()), **active, "ready": False}
                if not record['birth']:
                    raise OperationError('Não foi possível verificar a identidade do supervisor')
                _write(self.root / "process.json", record)
                listener = socket.socket(socket.AF_INET6 if ":" in config["host"] else socket.AF_INET, socket.SOCK_STREAM)
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                child = None
                read_fd = write_fd = None
                stop_requested = False
                def terminate(_signal, _frame):
                    nonlocal stop_requested
                    stop_requested = True
                    if child and child.poll() is None:
                        child.terminate()
                old_signals = {sig: signal.signal(sig, terminate) for sig in (signal.SIGTERM, signal.SIGINT)}
                try:
                    listener.bind((config["host"], config["port"]))
                    listener.listen(128)
                    # machine.env is authoritative, including after recovery.
                    env = {key: value for key, value in os.environ.items() if not key.startswith("MIA_") and key not in {"PYTHONPATH", "PYTHONHOME"}}
                    env.update(MIA_DATA_DIR=str(self._path(active["data"])), MIA_OPERATIONS_ROOT=str(self.root), MIA_BIND=config["host"])
                    read_fd, write_fd = os.pipe()
                    child = subprocess.Popen([str(self._python(active)), "-I", str(self.root / "manager.py"), "--root", str(self.root), "child", "--ready-fd", str(read_fd), "--socket-fd", str(listener.fileno()), "--service-lock-fd", str(service_lock.fileno())], env=env, cwd=self.root, pass_fds=(read_fd, listener.fileno(), service_lock.fileno()))
                    os.close(read_fd)
                    read_fd = None
                    record.update(ready=True, child_pid=child.pid, child_birth=_birth(child.pid))
                    if not record["child_birth"] or stop_requested:
                        raise OperationError("Inicialização interrompida antes de registrar processo")
                    # The child waits for this durable record. Parent death before
                    # the byte means EOF, and it exits without importing the app.
                    _write(self.root / "process.json", record)
                    os.write(write_fd, b"1")
                    os.close(write_fd)
                    write_fd = None
                    startup.close()
                    code = child.wait()
                    if code and not stop_requested:
                        raise OperationError("Servidor encerrou com falha")
                finally:
                    for descriptor in (read_fd, write_fd):
                        if descriptor is not None:
                            os.close(descriptor)
                    listener.close()
                    if child and child.poll() is None:
                        child.terminate()
                        try:
                            child.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            child.kill()
                            child.wait()
                    (self.root / "process.json").unlink(missing_ok=True)
                    for sig, previous in old_signals.items():
                        signal.signal(sig, previous)

    def child(self, *, ready_fd: int, socket_fd: int, service_lock_fd: int) -> None:
        """Private startup handshake; exec keeps the recorded PID and birth."""
        try:
            authorized = os.read(ready_fd, 1) == b"1"
        finally:
            os.close(ready_fd)
        if not authorized:
            return
        os.set_inheritable(socket_fd, True)
        os.set_inheritable(service_lock_fd, True)
        os.execv(sys.executable, [sys.executable, "-I", "-m", "uvicorn", "mia.app:app", "--env-file", str(self.root / "machine.env"), "--fd", str(socket_fd), "--workers", "1"])

    def _snapshot(self, active: dict, identity: str) -> str:
        relative = "snapshots/" + identity
        target = self.root / relative
        target.mkdir(mode=0o700)
        try:
            _copy_private(self._path(active["data"]), target / "data")
            original = target / "data/mia.db"
            if original.exists():
                # Consistent SQLite backup, rather than publishing copied WAL.
                original.unlink()
                for suffix in ("-wal", "-shm"):
                    (target / ("data/mia.db" + suffix)).unlink(missing_ok=True)
                with sqlite3.connect((self._path(active["data"]) / "mia.db").as_uri() + "?mode=ro", uri=True) as source:
                    with sqlite3.connect(original) as destination:
                        source.backup(destination)
                original.chmod(0o600)
                self._verify_db(original)
            for name in ("machine.env", "installation.json", "manager.py"):
                shutil.copyfile(self.root / name, target / name)
                (target / name).chmod(0o600)
            # SQLite and copied configuration must reach disk before the
            # verified manifest and then the recovery journal are published.
            for path in target.rglob("*"):
                if path.is_file():
                    with path.open("rb") as handle:
                        os.fsync(handle.fileno())
                elif path.is_dir():
                    _sync(path)
            _write(target / "snapshot.json", {"files": _manifest(target), "active": active})
            _sync(target)
            _sync(target.parent)
            return relative
        except BaseException:
            shutil.rmtree(target)
            raise

    @staticmethod
    def _verify_db(path: Path) -> None:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or db.execute("PRAGMA foreign_key_check").fetchone():
                raise OperationError("Banco não passou na verificação de integridade")
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"owner", "areas", "tasks", "runs", "sessions", "login_attempts"} <= tables:
                raise OperationError("Snapshot não é um banco da Mia")

    def _verify_snapshot(self, relative: str) -> Path:
        snapshot = self._path(relative)
        manifest = _read(snapshot / "snapshot.json")
        if not manifest or _manifest(snapshot) != manifest["files"]:
            raise OperationError("Snapshot incompleto ou alterado; recuperação recusada")
        if (snapshot / "data/mia.db").exists():
            self._verify_db(snapshot / "data/mia.db")
        return snapshot

    def _restore(self, journal: dict, operation_fd: int | None = None) -> dict:
        self._stop()
        snapshot = self._verify_snapshot(journal["snapshot"])
        if journal.get("restored_active"):
            # Resume this precise restored directory after a crash; never drop
            # newer state by making a second restoration from the old snapshot.
            old = journal["restored_active"]
            restored_data = self._path(old['data'])
            if not restored_data.is_dir() or restored_data.is_symlink():
                raise OperationError('Diretório recuperado ausente; dados não serão recriados vazios')
            restored_db = restored_data / "mia.db"
            if (snapshot / 'data/mia.db').exists() and not restored_db.is_file():
                raise OperationError('Banco recuperado ausente; recuperação recusada')
            if restored_db.exists():
                self._verify_db(restored_db)
        else:
            relative = "data/recovered-" + uuid.uuid4().hex
            _copy_private(snapshot / "data", self.root / relative)
            restored_db = self.root / relative / "mia.db"
            if restored_db.exists():
                with sqlite3.connect(restored_db) as db:
                    db.execute("DELETE FROM sessions")
                    db.execute("DELETE FROM login_attempts")
                    db.commit()
                self._verify_db(restored_db)
                with restored_db.open("rb") as handle:
                    os.fsync(handle.fileno())
            _sync(self.root / relative)
            _sync(self.root / 'data')
            old = {**journal["old"], "data": relative}
            journal.update(phase="recovery-prepared", restored_active=old)
            # Record the recovery target before switching the active pointer.
            _write(self.root / "journal.json", journal)
        # Configuration restored before startup is also repeatable. The manager
        # remains the current recovery implementation, not an older executable.
        for name in ("machine.env", "installation.json"):
            fd, temporary = tempfile.mkstemp(prefix=".restore-", dir=self.root)
            with os.fdopen(fd, "wb") as output:
                output.write((snapshot / name).read_bytes())
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.root / name)
        _write(self.root / "active.json", old)
        journal["phase"] = "recovered-starting"
        _write(self.root / "journal.json", journal)
        self._start(recovering=True, operation_fd=operation_fd)
        return old

    def _finish(self, journal: dict, outcome: str) -> None:
        _write(self.root / "history" / (journal["id"] + "-" + outcome + ".json"), {**journal, "outcome": outcome})
        (self.root / "journal.json").unlink()
        _sync(self.root)

    def update(self, source: Path, *, wheelhouse: Path | None = None, offline: bool = False) -> dict:
        self._check()
        with _lock(self.root / "operation.lock") as operation:
            self._pending()
            old = self.active()
            self._idle_database(old)
            candidate = self._release(source, wheelhouse, offline)
            self._stop()
            self._idle_database(old)
            identity = uuid.uuid4().hex
            snapshot = self._snapshot(old, identity)
            journal = {"id": identity, "phase": "prepared", "old": old, "new": {**candidate, "data": old["data"]}, "snapshot": snapshot}
            _write(self.root / "journal.json", journal)
            try:
                self._verify_snapshot(snapshot)
                _write(self.root / "active.json", journal["new"])
                journal["phase"] = "switched"
                _write(self.root / "journal.json", journal)
                self._start(recovering=True, operation_fd=operation.fileno())
                _write(self.root / "last-update.json", journal)
                self._finish(journal, "updated")
            except Exception as error:
                try:
                    self._restore(journal, operation_fd=operation.fileno())
                    self._finish(journal, "automatic-recovery")
                except Exception as recovery_error:
                    raise OperationError("Atualização falhou e recuperação está pendente; execute recover. Dados e snapshot preservados") from recovery_error
                raise OperationError("Atualização falhou; versão anterior restaurada em dados novos. Banco da tentativa preservado") from error
        return self.status()

    def recover(self) -> dict:
        self._check()
        with _lock(self.root / "operation.lock") as operation:
            journal = _read(self.root / "journal.json")
            if journal:
                self._restore(journal, operation_fd=operation.fileno())
                self._finish(journal, "recovered")
            else:
                self._start(operation_fd=operation.fileno())
        return self.status()

    def rollback(self, *, acknowledge_post_update_loss: bool = False) -> dict:
        self._check()
        if not acknowledge_post_update_loss:
            raise OperationError("Rollback usa o snapshot prévio: alterações posteriores ficam preservadas, mas fora do banco ativo. Use --acknowledge-post-update-loss após revisar")
        with _lock(self.root / "operation.lock") as operation:
            self._pending()
            prior = _read(self.root / "last-update.json")
            if not prior:
                raise OperationError("Não há atualização confirmada para retornar")
            active = self.active()
            if active["release"] != prior["new"]["release"]:
                raise OperationError("Atualização já foi revertida; nenhuma alteração aplicada")
            self._idle_database(active)
            self._stop()
            retained = self._snapshot(active, "before-rollback-" + uuid.uuid4().hex)
            journal = {**prior, "id": uuid.uuid4().hex, "phase": "rollback-prepared", "retained": retained}
            _write(self.root / "journal.json", journal)
            self._restore(journal, operation_fd=operation.fileno())
            self._finish(journal, "rolled-back")
        return self.status()


def public_status() -> dict:
    root = os.environ.get("MIA_OPERATIONS_ROOT")
    if not root:
        return {"managed": False, "version": None, "release": None, "running": True, "recovery_required": False, "operation": None, "last_update": None,
                "instructions": "Instalação manual/Docker: registre a versão, pare o serviço, verifique backup e restaure em dados novos para retornar. Veja docs/OPERATIONS.md; o navegador não executa comandos."}
    try:
        return Manager(Path(root)).status()
    except (OSError, ValueError, KeyError, OperationError):
        return {"managed": True, "version": None, "release": None, "running": True, "recovery_required": True, "operation": "state-unavailable", "last_update": None,
                "instructions": "Estado operacional indisponível. Verifique status no terminal; preserve diretório de dados e snapshots."}


def main() -> None:
    parser = argparse.ArgumentParser(description="Operação nativa explícita; fontes locais confiáveis e dados privados fora do checkout.")
    parser.add_argument("--root", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("install", "update"):
        operation = commands.add_parser(command)
        operation.add_argument("--source", required=True, type=Path)
        operation.add_argument("--wheelhouse", type=Path)
        operation.add_argument("--offline", action="store_true")
        if command == "install":
            operation.add_argument("--port", type=int, default=8123)
            operation.add_argument("--host", default="127.0.0.1")
            operation.add_argument("--env-file", type=Path)
    for command in ("start", "stop", "status", "recover"):
        commands.add_parser(command)
    foreground = commands.add_parser("serve")
    foreground.add_argument("--recovery-id", help=argparse.SUPPRESS)
    foreground.add_argument("--operation-fd", type=int, help=argparse.SUPPRESS)
    child = commands.add_parser("child", help=argparse.SUPPRESS)
    for name in ("ready-fd", "socket-fd", "service-lock-fd"):
        child.add_argument("--" + name, type=int, required=True, help=argparse.SUPPRESS)
    template = commands.add_parser("service-template")
    template.add_argument("--kind", choices=("systemd", "launchd"), required=True)
    rollback = commands.add_parser("rollback")
    rollback.add_argument("--acknowledge-post-update-loss", action="store_true")
    args = vars(parser.parse_args())
    manager = Manager(args.pop("root"))
    command = args.pop("command")
    try:
        result = getattr(manager, command.replace("-", "_"))(**args)
        if result is not None:
            print(result if isinstance(result, str) else json.dumps(result, ensure_ascii=False))
    except (OperationError, OSError, ValueError, KeyError, sqlite3.Error, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
