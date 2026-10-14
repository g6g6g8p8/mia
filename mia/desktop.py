"""Private desktop operations, reachable only by the native process bridge.

The web page has no privileged bridge. Every installation uses the exact bundled
offline inputs reviewed in the native UI; an interrupted install is an explicit
recovery operation, never a reason to replace somebody's existing library.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tomllib
import uuid
import urllib.request

from mia import __version__
from mia.installation import apply_service_plan, service_plan
from mia.launcher import runtime_inventory
from mia.operations import Manager, OperationError, _lock, _sync, _write


class DesktopError(OperationError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _no_links(path: Path) -> None:
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise DesktopError("unsafe_path", "O caminho da Mia contém um link simbólico. Escolha uma instalação segura sem substituir arquivos.")


def _json(path: Path, *, limit: int = 512 * 1024) -> dict:
    _no_links(path)
    if not path.exists():
        return {}
    if not path.is_file() or path.stat().st_size > limit:
        raise DesktopError("invalid_state", "Um arquivo da instalação não pode ser verificado. Os dados foram preservados.")
    try:
        with path.open("rb") as incoming:
            value = json.loads(incoming.read(limit + 1))
    except (ValueError, UnicodeError, RecursionError):
        raise DesktopError("invalid_state", "O estado da instalação não pode ser lido. Os dados foram preservados.") from None
    if not isinstance(value, dict):
        raise DesktopError("invalid_state", "O estado da instalação é inválido. Os dados foram preservados.")
    return value


MACHINE_ENV = "# Configuração privada desta instalação.\nMIA_AI_ENABLED=false\nMIA_COOKIE_SECURE=false\nMIA_INSTALLATION_MODE=local\n"
PRIVATE_MACHINE_ENV = MACHINE_ENV + "MIA_SETUP_REQUIRE_TOKEN=true\n"
LOCAL_ACTIONS = {"status", "local_plan", "local_install", "local_start", "local_stop", "local_recover", "local_snapshot", "local_bundle_plan", "local_bundle_update"}
REMOTE_ACTIONS = {"remote_preflight", "remote_install", "remote_connect", "remote_disconnect", "https_connect"}
UPDATE_ACTIONS = {"updates_status", "updates_check", "updates_prepare", "updates_apply", "updates_recover"}


class DesktopController:
    def __init__(self, resources: Path, home: Path | None = None):
        self.resources = Path(resources).absolute()
        self.home = Path(home or Path.home()).absolute()
        _no_links(self.resources)
        _no_links(self.home)
        self.base = self.home / "Library/Application Support/Mia"
        self.root = self.base / "installation"
        self.journal = self.base / "desktop-install.json"
        self._paths()

    def _paths(self) -> None:
        for path in (self.base, self.root, self.journal, self.base / "desktop.lock"):
            _no_links(path)
        if self.home.exists() and (not self.home.is_dir() or self.home.stat().st_uid != os.getuid()):
            raise DesktopError("unsafe_path", "A pasta pessoal precisa pertencer ao usuário atual.")
        for path in (self.base, self.root):
            if path.exists() and (not path.is_dir() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077):
                raise DesktopError("unsafe_path", "A pasta privada da Mia precisa pertencer ao usuário atual e estar protegida.")
        if self.journal.exists() and self.journal.stat().st_mode & 0o077:
            raise DesktopError("unsafe_path", "O registro privado da instalação não está protegido.")

    def _prepare_base(self) -> None:
        self._paths()
        self.base.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._paths()

    def _manager(self) -> Manager:
        self._paths()
        for name in ("installation.json", "active.json", "manager.py", "machine.env", "journal.json", "migration-pending.json", "service-registration.json", "process.json", "operation.lock", "service.lock", "runner.lock", "paused.json", "restart-blocked.json", "last-update.json"):
            _no_links(self.root / name)
        return Manager(self.root)

    def _local(self) -> dict:
        state = _json(self.journal)
        result = {"installed": False, "installation_id": state.get("installation_id"), "url": None,
                  "running": False, "paused": False, "version": None, "recovery_required": self.root.exists() or state.get("phase") not in (None, "planned", "complete")}
        if not self.root.exists():
            return result
        configuration = _json(self.root / "installation.json")
        if not configuration or not _json(self.root / "active.json"):
            return result
        manager = self._manager()
        status = manager.status()
        if configuration.get("host") != "127.0.0.1" or isinstance(configuration.get("port"), bool) or not isinstance(configuration.get("port"), int) or not 1 <= configuration["port"] <= 65535:
            raise DesktopError("unsafe_destination", "Esta instalação não usa o destino local esperado. Conecte pelo endereço HTTPS verificado.")
        identity = configuration.get("installation_id") or state.get("installation_id")
        if not identity:
            # A legacy root retains a stable cookie-store identity without
            # changing its configuration, and a replacement root gets another.
            info = self.root.stat()
            identity = "legacy-" + _hash([str(self.root), info.st_dev, info.st_ino])[:32]
        result.update(installed=True, installation_id=identity, url=f"http://127.0.0.1:{configuration['port']}/",
                      running=status["running"], paused=status["paused"], version=status["version"],
                      recovery_required=status["recovery_required"] or state.get("phase") not in (None, "planned", "complete"))
        if result["running"]:
            token = self._bootstrap_token(manager, result)
            if token is not None:
                result["bootstrap_token"] = token
        return result

    def _http_json(self, origin: str, path: str) -> dict:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *_args, **_kwargs):
                return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(origin.rstrip("/") + path, timeout=1) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                raise ValueError("unexpected response")
            raw = response.read(16 * 1024 + 1)
        if len(raw) > 16 * 1024:
            raise ValueError("bounded response")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("invalid response")
        return value

    def _bootstrap_token(self, manager: Manager, local: dict) -> str | None:
        # The status JSON is private native IPC, never the public HTTP API. Do
        # not deliver a token to a reused port, redirect, unready process or an
        # instance whose first owner already exists.
        record = manager._record()
        if not record or record.get("ready") is not True:
            return None
        try:
            status = self._http_json(local["url"], "/api/status")
            if status.get("configured") is not False or status.get("version") != local["version"]:
                return None
            info = self._http_json(local["url"], "/api/installation")
            if info.get("installation_id") != local["installation_id"] or info.get("bootstrap_protected") is not True or info.get("version") != local["version"] or type(info.get("desktop_protocol")) is not int or info["desktop_protocol"] != 1 or info.get("cookie_secure") is not False or info.get("transport_policy") != "private_connection_only":
                return None
        except (OSError, ValueError, UnicodeError, RecursionError):
            return None
        return _private_bootstrap_token(manager.root / "bootstrap-token")

    def _bundle(self) -> dict:
        report = _json(self.resources / "build-report.json", limit=16 * 1024 * 1024)
        runtime = report.get("runtime_provenance", {})
        wheels = report.get("wheelhouse_provenance", {})
        architecture = "arm64" if platform.machine() == "aarch64" else platform.machine()
        if runtime.get("platform") != "macos" or runtime.get("architecture") != architecture or architecture not in ("arm64", "x86_64") or runtime.get("python_version") not in ("3.12", "3.13"):
            raise DesktopError("unsupported_runtime", "O runtime incluído não corresponde a este Mac. Baixe a versão indicada para sua arquitetura.")
        if any(wheels.get(key) != runtime.get(key) for key in ("platform", "architecture", "python_version")):
            raise DesktopError("invalid_bundle", "Os componentes do aplicativo não correspondem à plataforma verificada.")
        for directory, expected in (("runtime", runtime.get("files")), ("wheelhouse", wheels.get("files"))):
            _no_links(self.resources / directory)
            if not expected or runtime_inventory(self.resources / directory) != expected:
                raise DesktopError("invalid_bundle", "Um componente do aplicativo foi alterado. Nenhuma instalação foi executada.")
        wheel_paths = list((self.resources / "wheelhouse").iterdir())
        if not wheel_paths or any(path.is_symlink() or not path.is_file() or path.suffix != ".whl" for path in wheel_paths):
            raise DesktopError("invalid_bundle", "O aplicativo precisa incluir todos os pacotes offline verificados.")
        _no_links(self.resources / "source")
        source_files = runtime_inventory(self.resources / "source")
        expected_source = {key.removeprefix("Contents/Resources/source/"): value for key, value in report.get("files", {}).items() if key.startswith("Contents/Resources/source/")}
        if not expected_source or source_files != expected_source:
            raise DesktopError("invalid_bundle", "O código incluído não corresponde ao pacote revisado.")
        metadata = tomllib.loads((self.resources / "source/pyproject.toml").read_text())["project"]
        if metadata.get("name") != "mia-personal-ai" or metadata.get("version") != __version__:
            raise DesktopError("invalid_bundle", "As versões do aplicativo e do backend não correspondem.")
        python = self.resources / "runtime/bin/python3"
        if not python.is_file() or not python.stat().st_mode & 0o111:
            raise DesktopError("invalid_bundle", "O runtime incluído não pode iniciar a Mia.")
        relative_python = str(python.resolve().relative_to((self.resources / "runtime").resolve()))
        return {"resources": str(self.resources), "version": metadata["version"], "architecture": architecture,
                "source_sha256": _hash(source_files), "runtime_sha256": _hash(runtime["files"]),
                "wheelhouse_sha256": _hash(wheels["files"]), "report_sha256": hashlib.sha256((self.resources / "build-report.json").read_bytes()).hexdigest(),
                "python_relative": relative_python}

    @staticmethod
    def _port_available(port: int) -> bool:
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                return False
        return True

    def _activation(self, python: Path, port: int) -> dict:
        name = "local.mia." + hashlib.sha256(str(self.root).encode()).hexdigest()[:12]
        destination = self.home / "Library/LaunchAgents" / (name + ".plist")
        _no_links(destination)
        arguments = [str(python), str(self.root / "manager.py"), "--root", str(self.root), "service-run"]
        content = plistlib.dumps({"Label": name, "ProgramArguments": arguments, "RunAtLoad": True, "KeepAlive": False, "ProcessType": "Background",
                                 "StandardOutPath": str(self.root / "service.log"), "StandardErrorPath": str(self.root / "service.log")}).decode()
        if destination.exists() and (not destination.is_file() or destination.read_text() != content):
            raise DesktopError("service_conflict", "Já existe um serviço diferente neste destino. Nenhum serviço foi substituído.")
        return {"kind": "launchd", "destination": str(destination), "content": content,
                "commands": [[str(python), str(self.root / "manager.py"), "--root", str(self.root), "start"],
                             ["launchctl", "bootstrap", "gui/" + str(os.getuid()), str(destination)]],
                "port": port, "network_changes": False, "scope": "current-user"}

    def _plan(self) -> tuple[dict, dict]:
        self._paths()
        if sys.platform != "darwin":
            raise DesktopError("unsupported_platform", "A instalação local deste aplicativo funciona no macOS.")
        if self.root.exists():
            raise DesktopError("recovery_required", "Já existe uma instalação neste Mac. Abra ou recupere essa instalação; seus dados não serão substituídos.")
        bundle = self._bundle()
        state = _json(self.journal)
        if state.get("phase") not in (None, "planned"):
            raise DesktopError("recovery_required", "Uma instalação foi interrompida. Use Recuperar para continuar com os dados preservados.")
        identity = state.get("installation_id") or str(uuid.uuid4())
        try:
            uuid.UUID(identity)
        except (ValueError, TypeError, AttributeError):
            raise DesktopError("invalid_state", "A identidade da instalação não pode ser verificada.") from None
        preferred = state.get("port")
        port = preferred if isinstance(preferred, int) and not isinstance(preferred, bool) and 8123 <= preferred <= 8223 and self._port_available(preferred) else next((number for number in range(8123, 8224) if self._port_available(number)), None)
        if port is None:
            raise DesktopError("port_unavailable", "Não há um endereço local disponível. Nenhum outro aplicativo foi parado.")
        stable = self.base / "runtimes" / bundle["runtime_sha256"]
        _no_links(stable)
        activation = self._activation(stable / bundle["python_relative"], port)
        details = {"protocol": 1, "bundle": bundle, "root": str(self.root), "runtime": str(stable), "installation_id": identity,
                   "port": port, "host": "127.0.0.1", "machine_env": PRIVATE_MACHINE_ENV, "private_bootstrap": True, "activation": activation,
                   "offline": True, "empty_installation": True}
        plan = {"sha256": _hash(details), "summary": ["Criar sua Mia vazia, em armazenamento privado neste Mac.",
                "Usar os componentes verificados incluídos no aplicativo, sem instalar Python ou Git.",
                "Iniciar em segundo plano após seu login. Este Mac precisa estar ligado e acordado.",
                "Importar contexto será sua próxima escolha. A IA começa desativada."], "details": details}
        return plan, {"format": 1, "phase": "planned", "installation_id": identity, "port": port, "bundle": bundle, "plan": plan}

    def _runtime(self, state: dict, *, recover: bool = False) -> Path:
        bundle = state["bundle"]
        root = self.base / "runtimes"
        stable = root / bundle["runtime_sha256"]
        temporary = root / (bundle["runtime_sha256"] + "-copying")
        for path in (root, stable, temporary):
            _no_links(path)
        root.mkdir(mode=0o700, exist_ok=True)
        if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
            raise DesktopError("unsafe_path", "O diretório de runtimes precisa pertencer ao usuário atual e estar protegido.")
        expected = _json(self.resources / "build-report.json", limit=16 * 1024 * 1024)["runtime_provenance"]["files"]
        if stable.exists():
            if stable.stat().st_uid != os.getuid() or stable.stat().st_mode & 0o077 or runtime_inventory(stable) != expected:
                raise DesktopError("runtime_changed", "O runtime privado mudou. Ele foi preservado e não será substituído.")
            return stable
        if temporary.exists():
            if not recover:
                raise DesktopError("recovery_required", "A cópia do runtime foi interrompida. Use Recuperar para continuar.")
            # Preserve the interrupted copy, including unexpected contents;
            # rename does not follow anything inside it and never deletes it.
            if not temporary.is_dir() or temporary.stat().st_uid != os.getuid():
                raise DesktopError("unsafe_path", "A cópia interrompida não pertence a esta instalação.")
            retained = root / (bundle["runtime_sha256"] + "-interrupted-" + uuid.uuid4().hex)
            os.rename(temporary, retained)
            _sync(root)
        shutil.copytree(self.resources / "runtime", temporary, symlinks=True)
        temporary.chmod(0o700)
        if runtime_inventory(temporary) != expected:
            raise DesktopError("invalid_bundle", "A cópia do runtime não passou na verificação. Use Recuperar; seus dados foram preservados.")
        os.rename(temporary, stable)
        _sync(root)
        return stable

    def _worker(self, state: dict, *, recover: bool) -> None:
        stable = self._runtime(state, recover=recover)
        command = [str(stable / state["bundle"]["python_relative"]), "-I", "-B", "-c",
                   "import sys; sys.path.insert(0, sys.argv[1]); from mia.desktop import _installation_worker; _installation_worker(sys.argv[2], sys.argv[3], sys.argv[4])",
                   str(self.resources / "source"), str(self.resources), str(self.home), "recover" if recover else "install"]
        # No inherited MIA/Python/pip configuration reaches a new installation.
        environment = {"HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "PIP_CONFIG_FILE": os.devnull, "PIP_NO_INDEX": "1"}
        log = self.base / "installer.log"
        _no_links(log)
        descriptor = os.open(log, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "ab") as output:
            os.chmod(log, 0o600)
            try:
                subprocess.run(command, env=environment, cwd=self.base, stdout=output, stderr=output, check=True, timeout=900)
            except (subprocess.SubprocessError, OSError):
                raise DesktopError("recovery_required", "A instalação não terminou. Os componentes e dados foram preservados; use Recuperar para continuar.") from None

    def _install(self, payload: dict) -> dict:
        self._prepare_base()
        with _lock(self.base / "desktop.lock"):
            plan, state = self._plan()
            # Read-only fresh plan first: stale approval causes no journal/runtime
            # mutation, and an occupied port cannot silently select another.
            if payload.get("approve_sha256") != plan["sha256"]:
                raise DesktopError("approval_changed", "O plano mudou. Confira a instalação novamente antes de continuar.")
            state["phase"] = "installing"
            _write(self.journal, state)
            self._worker(state, recover=False)
            state["phase"] = "complete"
            _write(self.journal, state)
            return self._local()

    def _recover(self) -> dict:
        self._prepare_base()
        with _lock(self.base / "desktop.lock"):
            state = _json(self.journal)
            if state.get("phase") in ("installing", "recovering"):
                if self._bundle() != state.get("bundle") or _hash(state.get("plan", {}).get("details")) != state.get("plan", {}).get("sha256"):
                    raise DesktopError("bundle_changed", "Recupere com o mesmo aplicativo que iniciou a instalação. Nada será substituído.")
                state["phase"] = "recovering"
                _write(self.journal, state)
                self._worker(state, recover=True)
                state["phase"] = "complete"
                _write(self.journal, state)
            elif self.root.exists():
                self._manager().recover()
            else:
                raise DesktopError("not_installed", "Não existe uma instalação para recuperar. Escolha Neste Mac para começar.")
            return self._local()

    def _snapshot(self) -> dict:
        manager = self._manager()
        manager._check()
        identity = "desktop-" + uuid.uuid4().hex
        with _lock(self.root / "operation.lock") as operation:
            manager._pending()
            active = manager.active()
            manager._idle_database(active)
            running = bool(manager._record())
            manager._stop()
            try:
                relative = manager._snapshot(active, identity)
                manager._verify_snapshot(relative)
            finally:
                if running:
                    manager._start(operation_fd=operation.fileno())
        return {"snapshot_id": identity, "verified": True,
                "summary": ["Cópia privada verificada da biblioteca e das configurações.", "Arquivos ainda não aprovados para importação precisam ser enviados novamente após uma restauração."],
                "details": {"path": str(self.root / relative), "external_backup": False}}

    def _bundle_plan(self) -> dict:
        if sys.platform != "darwin":
            raise DesktopError("unsupported_platform", "A atualização local deste aplicativo funciona no macOS.")
        manager = self._manager()
        manager._check()
        manager._pending()
        manager._background_capability()
        state = _json(self.journal)
        if state.get("phase") != "complete":
            raise DesktopError("recovery_required", "Conclua a recuperação da instalação antes de atualizar.")
        bundle = self._bundle()
        previous = state.get("bundle", {})
        if any(bundle.get(key) != previous.get(key) for key in ("runtime_sha256", "architecture", "python_relative")):
            raise DesktopError("runtime_upgrade_required", "Esta versão requer atualização coordenada do runtime. Sua biblioteca foi preservada; o backend atual continua disponível.")
        stable = self.base / "runtimes" / bundle["runtime_sha256"]
        _no_links(stable)
        if _hash(runtime_inventory(stable)) != bundle["runtime_sha256"]:
            raise DesktopError("runtime_changed", "O runtime privado mudou. A atualização foi interrompida com seus dados preservados.")
        configuration = _json(self.root / "installation.json")
        if configuration.get("python") != str(stable / bundle["python_relative"]):
            raise DesktopError("runtime_upgrade_required", "O backend usa outro runtime. Ele não será substituído automaticamente.")
        active = manager.active()
        def version(value):
            match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?", value)
            if not match:
                raise DesktopError("unsupported_version", "Esta versão precisa de um plano de compatibilidade antes de atualizar.")
            return tuple(map(int, match.groups()[:3])) + ({"a": 0, "b": 1, "rc": 2, None: 3}[match[4]], int(match[5] or 0))
        if version(bundle["version"]) < version(active["version"]):
            raise DesktopError("downgrade_rejected", "O aplicativo contém uma versão anterior. Use a recuperação revisada para retornar de versão.")
        details = {"protocol": 1, "root": str(self.root), "installation_id": self._local()["installation_id"], "active": active,
                   "bundle": bundle, "manager_sha256": configuration["manager_sha256"], "runtime": str(stable),
                   "command": [configuration["python"], str(self.root / "manager.py"), "--root", str(self.root), "update",
                               "--source", str(self.resources / "source"), "--wheelhouse", str(self.resources / "wheelhouse"), "--offline"]}
        return {"sha256": _hash(details), "current_version": active["version"], "candidate_version": bundle["version"],
                "update_available": bundle["version"] != active["version"],
                "summary": ["Atualizar sua instalação com o backend incluído neste aplicativo.", "Criar e verificar uma cópia da biblioteca antes de trocar a versão.",
                            "Se a inicialização falhar, recuperar a versão anterior com os dados preservados."], "details": details}

    def _bundle_update(self, payload: dict) -> dict:
        self._prepare_base()
        with _lock(self.base / "desktop.lock"):
            plan = self._bundle_plan()
            if payload.get("approve_sha256") != plan["sha256"]:
                raise DesktopError("approval_changed", "O plano mudou. Confira a atualização novamente antes de continuar.")
            if plan["update_available"]:
                was_paused = self._local()["paused"]
                log = self.base / "installer.log"
                _no_links(log)
                descriptor = os.open(log, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
                environment = {"HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "PIP_CONFIG_FILE": os.devnull, "PIP_NO_INDEX": "1"}
                with os.fdopen(descriptor, "ab") as output:
                    os.chmod(log, 0o600)
                    try:
                        subprocess.run(plan["details"]["command"], env=environment, cwd=self.base, stdout=output, stderr=output, check=True, timeout=900)
                    except (subprocess.SubprocessError, OSError):
                        if was_paused:
                            self._manager().stop()
                        raise DesktopError("update_failed", "A atualização não terminou. Confira o estado da Mia; a biblioteca e a cópia de recuperação foram preservadas.") from None
                if was_paused:
                    self._manager().stop()
                state = _json(self.journal)
                state["bundle"] = plan["details"]["bundle"]
                _write(self.journal, state)
            return self._local()

    def handle(self, action: str, payload: dict) -> dict:
        if not isinstance(action, str) or not isinstance(payload, dict):
            raise DesktopError("invalid_request", "A solicitação do aplicativo é inválida.")
        if action in REMOTE_ACTIONS:
            from mia.desktop_remote import RemoteController
            return RemoteController(self.resources, self.home).handle(action, payload)
        if action in UPDATE_ACTIONS:
            from mia.updates import UpdateController
            return UpdateController(self.resources, self.home).handle(action, payload)
        if action not in LOCAL_ACTIONS:
            raise DesktopError("unknown_action", "Esta operação não está disponível nesta versão da Mia.")
        allowed = {"approve_sha256"} if action in ("local_install", "local_bundle_update") else set()
        if set(payload) - allowed:
            raise DesktopError("invalid_request", "A solicitação contém opções que este aplicativo não aceita.")
        self._paths()
        if action == "status":
            connections = []
            try:
                from mia.desktop_remote import RemoteController
                connections = RemoteController(self.resources, self.home).connections()
            except ImportError:
                pass
            return {"protocol": 1, "app_version": __version__, "local": self._local(), "connections": connections}
        if sys.platform != "darwin":
            raise DesktopError("unsupported_platform", "As operações locais deste aplicativo funcionam no macOS.")
        if action == "local_plan":
            self._prepare_base()
            with _lock(self.base / "desktop.lock"):
                plan, state = self._plan()
                _write(self.journal, state)
                return plan
        if action == "local_install":
            return self._install(payload)
        if action == "local_recover":
            return self._recover()
        if action == "local_snapshot":
            return self._snapshot()
        if action == "local_bundle_plan":
            return self._bundle_plan()
        if action == "local_bundle_update":
            return self._bundle_update(payload)
        if self._local()["recovery_required"]:
            raise DesktopError("recovery_required", "A Mia precisa de recuperação. Seus dados serão preservados.")
        manager = self._manager()
        if action == "local_start":
            manager.start()
        else:
            manager.stop()
        return self._local()


def _installation_worker(resources: str, home: str, mode: str) -> None:
    """Fixed internal subprocess; the runtime creating venvs has a stable path."""
    controller = DesktopController(Path(resources), Path(home))
    state = _json(controller.journal)
    if sys.platform != "darwin" or mode not in ("install", "recover") or state.get("phase") not in ("installing", "recovering"):
        raise OperationError("Operação interna de instalação inválida")
    if controller._bundle() != state.get("bundle"):
        raise OperationError("Componentes da instalação mudaram")
    plan = state["plan"]
    details = plan["details"]
    if _hash(details) != plan["sha256"] or details["root"] != str(controller.root) or details["installation_id"] != state["installation_id"]:
        raise OperationError("Plano interno inválido")
    manager = controller._manager()
    source, wheelhouse = controller.resources / "source", controller.resources / "wheelhouse"
    environment = controller.base / "desktop-machine.env"
    _no_links(environment)
    if environment.exists() and (not environment.is_file() or environment.read_text() != MACHINE_ENV):
        raise OperationError("Configuração de instalação mudou")
    if not environment.exists():
        descriptor = os.open(environment, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(MACHINE_ENV)
            output.flush()
            os.fsync(output.fileno())
    if not controller.root.exists():
        manager.install(source, port=state["port"], host="127.0.0.1", env_file=environment, wheelhouse=wheelhouse, offline=True,
                        installation_id=state["installation_id"], private_bootstrap=True)
    elif mode == "install":
        raise OperationError("Instalação existente preservada")
    elif not (controller.root / "active.json").exists():
        _resume_empty_install(controller, state, source, wheelhouse)
    manager._check()
    configuration = _json(controller.root / "installation.json")
    if configuration.get("host") != "127.0.0.1" or configuration.get("port") != state["port"] or configuration.get("python") != details["activation"]["commands"][0][0] or configuration.get("private_bootstrap") is not True:
        raise OperationError("Destino ou runtime da instalação mudou")
    if (controller.root / "machine.env").read_text() != PRIVATE_MACHINE_ENV:
        raise OperationError("Configuração privada da instalação mudou")
    _private_bootstrap_token(controller.root / "bootstrap-token")
    if not configuration.get("installation_id"):
        configuration["installation_id"] = state["installation_id"]
        _write(controller.root / "installation.json", configuration)
    elif configuration["installation_id"] != state["installation_id"]:
        raise OperationError("Identidade da instalação mudou")
    activation = service_plan(manager, "launchd", home=controller.home)
    if any(activation.get(key) != details["activation"][key] for key in ("kind", "destination", "content", "commands", "scope", "network_changes")):
        raise OperationError("O serviço mudou depois da aprovação")
    if not _json(controller.root / "service-registration.json"):
        apply_service_plan(manager, activation, approve_sha256=activation["sha256"], home=controller.home)
    else:
        if _json(controller.root / "service-registration.json").get("sha256") != activation["sha256"]:
            raise OperationError("Registro do serviço mudou")
        manager.start()


def _resume_empty_install(controller: DesktopController, state: dict, source: Path, wheelhouse: Path) -> None:
    """Resume only the attested, never-started root created by this journal.

    Incomplete releases remain preserved. No directory or existing library is
    deleted, and any unexpected content causes refusal before reconstruction.
    """
    root = controller.root
    controller._paths()
    allowed = {"releases", "snapshots", "data", "history", "machine.env", "manager.py", "installation.json", "operation.lock", "bootstrap-token"}
    if any(path.name not in allowed or path.is_symlink() for path in root.iterdir()):
        raise OperationError("A instalação incompleta contém estado inesperado")
    for name in ("snapshots", "history"):
        directory = root / name
        if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
            raise OperationError("A instalação incompleta contém dados preservados")
    data = root / "data"
    if data.exists() and (not data.is_dir() or any(path.name != "initial" or path.is_symlink() or not path.is_dir() or any(path.iterdir()) for path in data.iterdir())):
        raise OperationError("Dados existentes impedem reconstrução da instalação")
    manager_source = source / "mia/operations.py"
    expected_config = {"format": 1, "host": "127.0.0.1", "port": state["port"], "python": sys._base_executable, "installation_id": state["installation_id"], "private_bootstrap": True,
                       "manager_protocol": 2, "manager_sha256": hashlib.sha256(manager_source.read_bytes()).hexdigest()}
    existing = _json(root / "installation.json")
    if existing and any(existing.get(key) != value for key, value in expected_config.items()):
        raise OperationError("Metadados da instalação incompleta mudaram")
    for name, expected in (("machine.env", PRIVATE_MACHINE_ENV.encode()), ("manager.py", manager_source.read_bytes())):
        path = root / name
        permitted = {expected, MACHINE_ENV.encode()} if name == "machine.env" and not existing else {expected}
        if path.exists() and (not path.is_file() or path.read_bytes() not in permitted):
            raise OperationError("Configuração da instalação incompleta mudou")
    for name in ("releases", "snapshots", "data", "history", "data/initial"):
        path = root / name
        _no_links(path)
        path.mkdir(mode=0o700, exist_ok=True)
    for name, expected in (("machine.env", PRIVATE_MACHINE_ENV.encode()), ("manager.py", manager_source.read_bytes())):
        if not (root / name).exists():
            descriptor = os.open(root / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(expected)
                output.flush()
                os.fsync(output.fileno())
        elif name == "machine.env" and (root / name).read_bytes() == MACHINE_ENV.encode():
            # A kill between initial environment creation and protection flag
            # publication may leave only the reviewed empty-install defaults.
            # No owner/data/active release exists, so completing the same flag
            # cannot inherit or overwrite somebody's configuration.
            import tempfile
            descriptor, temporary = tempfile.mkstemp(prefix=".bootstrap-env-", dir=root)
            try:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(expected)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, root / name)
                _sync(root)
            finally:
                Path(temporary).unlink(missing_ok=True)
    if (root / "bootstrap-token").exists():
        _private_bootstrap_token(root / "bootstrap-token")
    else:
        if existing:
            # Manager publishes configuration only after creating this token.
            # Its absence then signals altered state rather than an interrupted
            # unpublished install, and recovery must not silently rotate it.
            raise OperationError("O acesso inicial privado da instalação mudou")
        descriptor = os.open(root / "bootstrap-token", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(secrets.token_urlsafe(32) + "\n")
            output.flush()
            os.fsync(output.fileno())
    if not existing:
        _write(root / "installation.json", expected_config)
    manager = controller._manager()
    with _lock(root / "operation.lock"):
        release = manager._release(source, wheelhouse, offline=True)
        _write(root / "active.json", {**release, "data": "data/initial"})


def _private_bootstrap_token(path: Path) -> str:
    _no_links(path)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as incoming:
            metadata = os.fstat(incoming.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_mode & 0o777 != 0o600 or metadata.st_size != 44:
                raise ValueError
            raw = incoming.read(45)
    except (OSError, ValueError):
        raise DesktopError("bootstrap_unavailable", "O acesso inicial privado não pôde ser verificado. Os dados foram preservados; confira a instalação.") from None
    if not re.fullmatch(rb"[A-Za-z0-9_-]{43}\n", raw):
        raise DesktopError("bootstrap_unavailable", "O acesso inicial privado não pôde ser verificado. Os dados foram preservados.")
    return raw[:-1].decode("ascii")
