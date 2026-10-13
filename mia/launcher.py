"""macOS graphical launcher foundation; backend remains a background service.

The app distribution supplies Python and wheels. This module never asks users
to install Python/Git/pip, weaken Gatekeeper, or expose a local port remotely.
Actual signed/notarized artifacts and clean-Mac acceptance remain release gates.
"""
from __future__ import annotations

import json
import ipaddress
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import re
import shutil
import urllib.parse
import webbrowser

from mia.installation import apply_service_plan, service_plan
from mia.operations import Manager, OperationError, _read, _write


def remote_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value.strip())
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError
        if any(ord(character) < 33 or ord(character) == 127 for character in value) or any(character in value for character in ("\\", "?", "#")):
            raise ValueError
        if parsed.path not in ("", "/") or parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError
        try:
            ipaddress.ip_address(parsed.hostname)
        except ValueError:
            name = parsed.hostname.encode("idna").decode("ascii")
            if len(name) > 253 or not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in name.split(".")):
                raise ValueError
        return urllib.parse.urlunsplit(("https", parsed.netloc, "/", "", ""))
    except (ValueError, UnicodeError):
        raise OperationError("Informe somente o endereço HTTPS da instalação, sem senha, caminho, token ou parâmetros") from None


def dialog(message: str, buttons: tuple[str, ...] = ("OK",)) -> str:
    source = "button returned of (display dialog " + json.dumps(message, ensure_ascii=False) + " with title \"Mia\" buttons {" + ",".join(json.dumps(button, ensure_ascii=False) for button in buttons) + "} default button " + json.dumps(buttons[-1], ensure_ascii=False) + ")"
    return subprocess.check_output(["osascript", "-e", source], text=True).strip()


def ask_remote() -> str:
    source = 'text returned of (display dialog "Endereço da sua Mia existente (HTTPS):" with title "Conectar à minha Mia" default answer "https://" buttons {"Cancelar", "Conectar"} default button "Conectar")'
    return remote_url(subprocess.check_output(["osascript", "-e", source], text=True).strip())


def open_local(manager: Manager) -> None:
    manager.start()
    config = _read(manager.root / "installation.json")
    if config["host"] not in ("127.0.0.1", "::1"):
        raise OperationError("O launcher local abre somente uma instalação loopback; conecte ao endereço HTTPS para acessar remotamente")
    host = "[::1]" if config["host"] == "::1" else "127.0.0.1"
    webbrowser.open("http://" + host + ":" + str(config["port"]) + "/")


def runtime_inventory(directory: Path) -> dict:
    """Match the reviewed builder's runtime provenance, including safe links."""
    if directory.is_symlink() or not directory.is_dir():
        raise OperationError("Runtime precisa ser diretório real")
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            link = os.readlink(path)
            if Path(link).is_absolute() or not path.resolve().is_relative_to(directory.resolve()) or not path.resolve().exists():
                raise OperationError("Runtime contém link externo ou quebrado")
            result[str(path.relative_to(directory))] = {"symlink": link}
        elif path.is_file():
            with path.open("rb") as file:
                result[str(path.relative_to(directory))] = {"sha256": hashlib.file_digest(file, "sha256").hexdigest(), "executable": bool(path.stat().st_mode & 0o111)}
        elif not path.is_dir():
            raise OperationError("Runtime contém arquivo especial")
    return result


def install_bundled(manager: Manager, resources: Path) -> None:
    """Put the runtime at a stable private path before creating environments.

    Moving/updating the launcher bundle must not invalidate the backend Python
    executable or per-release virtual environments. Reuse only exact verified
    runtime contents from this explicit bundle, never an arbitrary existing dir.
    """
    runtime = manager.root.parent / "runtime"
    expected = _read(resources / "build-report.json").get("runtime_provenance", {}).get("files")
    if not expected or runtime_inventory(resources / "runtime") != expected:
        raise OperationError("Runtime do app não corresponde à proveniência revisada")
    if not runtime.exists():
        temporary = runtime.parent / "runtime-copying"
        if temporary.exists() or temporary.is_symlink():
            raise OperationError("Cópia de runtime interrompida preservada; revise antes de repetir")
        shutil.copytree(resources / "runtime", temporary, symlinks=True)
        if runtime_inventory(temporary) != expected:
            raise OperationError("Cópia de runtime falhou na verificação")
        temporary.chmod(0o700)
        os.rename(temporary, runtime)
    if runtime_inventory(runtime) != expected:
        raise OperationError("Runtime existente difere; não foi sobrescrito")
    log = manager.root.parent / "installer.log"
    with log.open("ab") as output:
        log.chmod(0o600)
        subprocess.run([str(runtime / "bin/python3"), "-I", str(resources / "source/mia/operations.py"), "--root", str(manager.root), "install", "--source", str(resources / "source"), "--wheelhouse", str(resources / "wheelhouse"), "--offline"], stdout=output, stderr=output, check=True)


def main(resources: Path) -> None:
    if sys.platform != "darwin":
        raise OperationError("Este launcher gráfico é destinado ao macOS")
    root = Path.home() / "Library/Application Support/Mia/installation"
    preferences = root.parent / "launcher.json"
    preferences.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    selection = _read(preferences)
    if not selection:
        choice = dialog("Onde você quer usar Mia? Neste Mac os dados ficam nesta máquina e ela precisa estar ligada/acordada. Conectar abre sua instalação HTTPS existente, com os mesmos dados de outros dispositivos.", ("Cancelar", "Conectar à minha Mia", "Neste Mac"))
        if choice == "Cancelar":
            return
        selection = {"mode": "local"} if choice == "Neste Mac" else {"mode": "remote", "url": ask_remote()}
        _write(preferences, selection)
    if selection["mode"] == "remote":
        choice = dialog("Mia usa o contexto guardado na sua instalação existente. Você fará login no navegador. Nenhuma biblioteca será copiada para este Mac.", ("Fechar", "Trocar instalação", "Abrir Mia"))
        if choice == "Trocar instalação":
            preferences.unlink()
            return main(resources)
        if choice == "Abrir Mia":
            webbrowser.open(remote_url(selection["url"]))
        return
    manager = Manager(root)
    if not root.exists():
        if dialog("Instalar Mia vazia neste Mac? O serviço usa somente 127.0.0.1 e não abre acesso remoto. Seus arquivos atuais não serão alterados; importar contexto é uma ação posterior.", ("Cancelar", "Instalar")) != "Instalar":
            return
        install_bundled(manager, resources)
    registered = _read(root / "service-registration.json")
    if not registered:
        plan = service_plan(manager, "launchd")
        reviewed = root / "launchd-plan.json"
        _write(reviewed, plan)
        # Full exact plan, including file content and commands, is reviewable
        # before explicit activation. No service mutation when review is refused.
        subprocess.run(["open", "-t", str(reviewed)], check=True)
        if dialog("Revise o plano aberto: arquivo LaunchAgent e comandos exatos. Ativar inicia Mia após login, em segundo plano. Fechar esta janela ou navegador não para o serviço. Parar Mia é explícito; outros dispositivos perderão acesso. Nenhuma configuração de rede será alterada.", ("Cancelar", "Ativar serviço")) != "Ativar serviço":
            return
        apply_service_plan(manager, plan, approve_sha256=plan["sha256"])
    status = manager.status()
    state = "Em execução" if status["running"] else "Parada"
    if status["recovery_required"]:
        dialog("Mia precisa de recuperação operacional; dados e snapshots estão preservados. Não será iniciada automaticamente. Consulte o plano de recuperação desta instalação.")
        return
    choice = dialog(state + ". Fechar esta janela mantém o serviço no estado atual. O Mac precisa estar ligado/acordado.", ("Fechar", "Trocar instalação", "Parar Mia", "Abrir Mia"))
    if choice == "Abrir Mia":
        open_local(manager)
    elif choice == "Parar Mia":
        if dialog("Parar Mia também interrompe acesso de outros dispositivos. Seus dados ficam preservados.", ("Cancelar", "Parar")) == "Parar":
            manager.stop()
    elif choice == "Trocar instalação":
        # Changing client mode never silently stops/deletes the old backend.
        preferences.unlink()

