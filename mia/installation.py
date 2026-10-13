"""Reviewable, explicit user-service activation. No browser/automatic host edits."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from mia.operations import Manager, OperationError, _read, _write


def service_plan(manager: Manager, kind: str, *, home: Path | None = None) -> dict:
    manager._check()
    home = (home or Path.home()).resolve()
    configuration = _read(manager.root / "installation.json")
    start = [configuration["python"], str(manager.root / "manager.py"), "--root", str(manager.root), "start"]
    identity = hashlib.sha256(str(manager.root).encode()).hexdigest()[:12]
    if kind == "systemd":
        name = "mia-" + identity + ".service"
        destination = home / ".config/systemd/user" / name
        commands = [start, ["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", name]]
        availability = "Inicia na sessão do usuário. Para funcionar sem login após boot, um operador precisa habilitar linger para esse usuário; este plano não usa sudo nem altera linger."
    elif kind == "launchd":
        name = "local.mia." + identity
        destination = home / "Library/LaunchAgents" / (name + ".plist")
        commands = [start, ["launchctl", "bootstrap", "gui/" + str(os.getuid()), str(destination)]]
        availability = "Inicia após login no Mac; o computador precisa estar ligado e acordado. Fechar o navegador ou launcher não para Mia."
    else:
        raise OperationError("Serviço suportado: systemd ou launchd")
    plan = {"format": 1, "kind": kind, "root": str(manager.root), "destination": str(destination),
            "content": manager.service_template(kind=kind), "commands": commands,
            "availability": availability, "network_changes": False, "scope": "current-user",
            "restart_policy": "Até três falhas em 60 segundos; parada explícita e recuperação pendente bloqueiam tentativas. Use start para desbloquear.",
            "stop": "Parar Mia pausa o serviço e afeta outros dispositivos. Fechar janela/navegador não para o serviço."}
    plan["sha256"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    return plan


def apply_service_plan(manager: Manager, plan: dict, *, approve_sha256: str, home: Path | None = None) -> dict:
    expected = service_plan(manager, plan.get("kind"), home=home)
    if plan != expected or approve_sha256 != expected["sha256"]:
        raise OperationError("Plano mudou ou hash aprovado não corresponde; gere e revise o plano novamente")
    if (plan["kind"] == "systemd" and sys.platform != "linux") or (plan["kind"] == "launchd" and sys.platform != "darwin"):
        raise OperationError("Ativação deve ocorrer no sistema operacional do plano")
    destination = Path(plan["destination"])
    # Never overwrite another user installation or follow a substituted link.
    for parent in (destination, *destination.parents):
        if parent.is_symlink():
            raise OperationError("Caminho de serviço não pode conter link simbólico")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or destination.read_text() != plan["content"]:
            raise OperationError("Arquivo de serviço existente difere; não foi substituído")
    else:
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w") as file:
            file.write(plan["content"])
            file.flush()
            os.fsync(file.fileno())
    # Explicit apply resumes a paused installation. No implicit recover/rollback.
    manager._pending()
    for command in plan["commands"]:
        subprocess.run(command, check=True)
    _write(manager.root / "service-registration.json", {"kind": plan["kind"], "destination": str(destination), "sha256": plan["sha256"]})
    return {"applied": True, "availability": plan["availability"], "status": manager.status()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Revise o plano completo antes de ativar um serviço somente para este usuário.")
    parser.add_argument("--root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("service-plan")
    plan.add_argument("--kind", choices=("systemd", "launchd"), required=True)
    plan.add_argument("--output", type=Path)
    apply = commands.add_parser("service-apply")
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--approve-sha256", required=True)
    args = parser.parse_args()
    manager = Manager(args.root)
    try:
        if args.command == "service-plan":
            result = service_plan(manager, args.kind)
            if args.output:
                if args.output.exists() or args.output.is_symlink():
                    raise OperationError("Use um arquivo de plano novo")
                _write(args.output, result)
        else:
            if args.plan.is_symlink() or not args.plan.is_file():
                raise OperationError("Plano deve ser arquivo regular")
            result = apply_service_plan(manager, _read(args.plan), approve_sha256=args.approve_sha256)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OperationError, OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
