#!/usr/bin/env python3
"""Read-only Mia inventory: metadata only; never read secrets or stop services.

Run with the system Python before loading an existing Mia runtime. Searches only
known candidates and explicit --candidate paths, not the user's notes or home.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import stat
import subprocess
import sys

LIMIT = 256 * 1024
SERVICE = re.compile(r"(?:mia(?:-[0-9a-f]{12})?\.service|local\.mia(?:\.[0-9a-f]{12})?\.plist)\Z")


def no_links(path: Path) -> bool:
    """Refuse substituted files and any linked ancestor, including explicit paths."""
    return not any(part.is_symlink() for part in (path, *path.parents))


def file_metadata(path: Path) -> dict:
    result = {"path": str(path), "exists": path.exists() or path.is_symlink()}
    if not result["exists"]:
        return result
    result["symlink_or_linked_ancestor"] = not no_links(path)
    if result["symlink_or_linked_ancestor"]:
        result["inspection"] = "skipped-linked-path"
        return result
    info = path.stat()
    result.update(kind="directory" if stat.S_ISDIR(info.st_mode) else "file" if stat.S_ISREG(info.st_mode) else "special",
                  bytes=info.st_size, uid=info.st_uid, permissions=oct(stat.S_IMODE(info.st_mode)))
    return result


def small_file(path: Path) -> bytes | None:
    if not no_links(path) or not path.is_file() or path.stat().st_size > LIMIT:
        return None
    with path.open("rb") as file:
        data = file.read(LIMIT + 1)
    return data if len(data) <= LIMIT else None


def json_file(path: Path) -> dict:
    raw = small_file(path)
    if raw is None:
        return {}
    try:
        result = json.loads(raw)
    except (UnicodeError, ValueError):
        return {}
    return result if isinstance(result, dict) else {}


def relative_child(root: Path, value: object, prefix: str | None = None) -> Path | None:
    if not isinstance(value, str) or not value or len(value) > 4096 or any(ord(char) < 32 for char in value):
        return None
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        return None
    if prefix is not None and relative.parts[0] != prefix:
        return None
    return root / relative


def absolute_candidate(value: object) -> Path | None:
    if not isinstance(value, str) or not value or len(value) > 4096 or any(ord(char) < 32 for char in value):
        return None
    path = Path(value)
    return path if path.is_absolute() and ".." not in path.parts else None


def legacy_configuration(configuration: dict, active: dict, root: Path) -> bool:
    """a11 had format=1 and no protocol; recognize only a cautious candidate."""
    if configuration.get("format") != 1 or "manager_protocol" in configuration:
        return False
    port = configuration.get("port")
    if type(port) is not int or not 0 < port < 65536 or absolute_candidate(configuration.get("python")) is None:
        return False
    try:
        ipaddress.ip_address(configuration.get("host"))
    except (ValueError, TypeError):
        return False
    version = active.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9][0-9A-Za-z.+-]{0,39}", version):
        return False
    if relative_child(root, active.get("release"), "releases") is None or relative_child(root, active.get("data"), "data") is None:
        return False
    manager = small_file(root / "manager.py")
    return bool(manager and manager.startswith(b'"""Conscious native operations.') and b"class Manager:" in manager and b'"mia.app:app"' in manager)


def probe(arguments: list[str]) -> dict:
    """No shell, no elevated access and no stderr/command-line disclosure."""
    if not shutil.which(arguments[0]):
        return {"available": False}
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"available": True, "completed": False}
    return {"available": True, "completed": True, "ok": result.returncode == 0,
            "output": result.stdout[:1024 * 1024]}


def candidate(path: Path) -> dict:
    result = file_metadata(path)
    if result.get("kind") != "directory":
        return result
    configuration = json_file(path / "installation.json")
    active = json_file(path / "active.json")
    source = small_file(path / "pyproject.toml")
    source_is_mia = bool(source and re.search(rb'^name\s*=\s*[\"\']mia-personal-ai[\"\']', source, re.MULTILINE))
    result["identification"] = "managed-mia" if configuration.get("manager_protocol") in (1, 2) and no_links(path / "manager.py") and (path / "manager.py").is_file() else "mia-source-checkout" if source_is_mia else "unverified-candidate"
    if result["identification"] == "unverified-candidate" and legacy_configuration(configuration, active, path):
        result["identification"] = "managed-mia-legacy-candidate"
    result["cleanup_authorized_by_inventory"] = False
    result["secret_configuration_present"] = any((path / name).exists() for name in (".env", "machine.env"))
    result["git_metadata_present"] = (path / ".git").exists()
    result["venv_present"] = (path / ".venv").is_dir()
    result["databases"] = [file_metadata(path / "data/mia.db")]
    if result["identification"].startswith("managed-mia"):
        version = active.get("version", "")
        result["version"] = version if isinstance(version, str) and re.fullmatch(r"[0-9][0-9A-Za-z.+-]{0,39}", version) else "unknown"
        data = relative_child(path, active.get("data"))
        if data:
            result["databases"].append(file_metadata(data / "mia.db"))
        release = relative_child(path, active.get("release"), "releases")
        result["application_runtime_candidate"] = file_metadata(release / "venv/bin/python") if release else None
        bootstrap = absolute_candidate(configuration.get("python"))
        result["bootstrap_python_candidate"] = file_metadata(bootstrap) if bootstrap else None
        result["runtime_verification"] = "Paths only; never executed. The application runtime contains Mia; the bootstrap Python may not."
        record = json_file(path / "process.json")
        result["recorded_pid"] = record.get("pid") if type(record.get("pid")) is int and 0 < record["pid"] < 2**31 else None
        result["paused"] = (path / "paused.json").exists()
        result["recovery_pending"] = any((path / name).exists() for name in ("journal.json", "migration-pending.json"))
        result["service_registration_present"] = (path / "service-registration.json").exists()
        port, host = configuration.get("port"), configuration.get("host")
        result["port"] = port if type(port) is int and 0 < port < 65536 else None
        result["bind"] = host if isinstance(host, str) and re.fullmatch(r"[A-Za-z0-9.:-]{1,253}", host) else "unknown"
    elif source_is_mia:
        result["application_runtime_candidate"] = file_metadata(path / ".venv/bin/python")
        result["bootstrap_python_candidate"] = None
        version_source = small_file(path / "mia/__init__.py")
        declared = re.search(rb'^__version__\s*=\s*[\"\']([0-9][0-9A-Za-z.+-]{0,39})[\"\']', version_source or b"", re.MULTILINE)
        result["checkout_version"] = declared.group(1).decode("ascii") if declared else "unknown"
        result["installed_runtime_version"] = "not-executed"
        response = probe(["git", "-C", str(path), "rev-parse", "--verify", "HEAD"])
        commit = response.get("output", "").strip()
        result["commit"] = commit if re.fullmatch(r"[0-9a-f]{40,64}", commit) else "unavailable"
    return result


def registrations(home: Path) -> list[dict]:
    result = []
    for directory in (home / ".config/systemd/user", home / "Library/LaunchAgents"):
        if not no_links(directory) or not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if not SERVICE.fullmatch(path.name):
                continue
            entry = file_metadata(path)
            raw = small_file(path)
            entry["mia_program_marker"] = False
            if raw:
                if path.suffix == ".plist":
                    try:
                        plist = plistlib.loads(raw)
                        arguments = plist.get("ProgramArguments", []) if isinstance(plist, dict) else []
                        entry["mia_program_marker"] = isinstance(arguments, list) and any(isinstance(a, str) and (a == "mia.app:app" or a.endswith("/manager.py")) for a in arguments)
                    except (ValueError, plistlib.InvalidFileException, TypeError):
                        pass
                else:
                    entry["mia_program_marker"] = b"mia.app:app" in raw or b"/manager.py" in raw
                entry["sha256"] = hashlib.sha256(raw).hexdigest()
            entry["cleanup_authorized_by_inventory"] = False
            result.append(entry)
    return result


def listeners(port: int) -> dict:
    response = probe(["lsof", "-nP", "-iTCP:" + str(port), "-sTCP:LISTEN", "-Fpcu"])
    result = {"port": port, "available": response["available"], "processes": []}
    if response["available"]:
        records = []
        record = None
        for line in response.get("output", "").splitlines():
            if re.fullmatch(r"p[0-9]+", line):
                record = {"pid": int(line[1:])}
                records.append(record)
            elif record is not None and line.startswith("c"):
                record["executable_name"] = line[1:][:120]
            elif record is not None and re.fullmatch(r"u[0-9]+", line):
                record["uid"] = int(line[1:])
        result["processes"] = records
        result["completed"] = response.get("completed", False)
        result["empty_result_requires_cross_check"] = not records
        # lsof returns 1 when no listener exists; this is not proof of no data users.
        return result
    response = probe(["ss", "-ltnp", "( sport = :" + str(port) + " )"])
    result.update(available=response["available"], completed=response.get("completed", False))
    for name, pid in re.findall(r'\("([^"\n]{1,120})",pid=(\d+),', response.get("output", "")):
        result["processes"].append({"pid": int(pid), "executable_name": name})
    result["pid_visibility_may_require_owner"] = True
    return result


def containers() -> dict:
    # Deliberately omit Command, environment, mounts and arbitrary labels.
    response = probe(["docker", "ps", "-a", "--format", '{{json .ID}}\t{{json .Names}}\t{{json .Image}}\t{{json .Status}}\t{{json .Ports}}\t{{json (.Label "com.docker.compose.service")}}'])
    result = {"available": response["available"], "completed": response.get("completed", False), "mia_candidates": [], "other_containers_untouched": True}
    for line in response.get("output", "").splitlines():
        try:
            identifier, name, image, state, ports, service = [json.loads(value) for value in line.split("\t")]
        except (ValueError, TypeError):
            continue
        if service == "mia" or re.fullmatch(r"mia(?:[-_][A-Za-z0-9_.-]+)?", str(name)):
            result["mia_candidates"].append({"id": identifier, "name": name, "image": image, "state": state, "ports": ports, "compose_service": service,
                                             "cleanup_authorized_by_inventory": False})
    return result


def inventory(home: Path, extra: list[Path], ports: list[int]) -> dict:
    home = home.absolute()
    known = [home / "mia-onboarding", home / "mia-pilot", home / ".local/share/mia", home / "Library/Application Support/Mia/installation"]
    candidates = list(dict.fromkeys(known + [path.expanduser().absolute() for path in extra]))
    return {"format": 1, "read_only": True, "platform": platform.system(), "python": platform.python_version(), "uid": os.getuid(),
            "candidates": [candidate(path) for path in candidates], "service_files": registrations(home),
            "listeners": [listeners(port) for port in dict.fromkeys(ports)], "containers": containers(),
            "limits": ["No recursive search; custom data paths or service names may be absent.",
                       "No note contents, .env/machine.env files, environment queries or full process arguments. Service definitions are inspected for a Mia marker/hash only; their contents are never printed.",
                       "A candidate, PID or free port is not authority to stop or remove anything."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, action="append", default=[], help="Additional exact installation path; never scans recursively")
    parser.add_argument("--port", type=int, action="append", default=[], help="Additional listener port; always includes 8123")
    args = parser.parse_args()
    if any(not 0 < port < 65536 for port in args.port):
        parser.error("port must be between 1 and 65535")
    if not hasattr(os, "getuid"):
        parser.error("This inventory supports the Mac/Linux installations only")
    try:
        print(json.dumps(inventory(Path.home(), args.candidate, [8123, *args.port]), ensure_ascii=False, indent=2))
    except OSError as error:
        parser.exit(1, "Inventory could not inspect filesystem metadata (" + type(error).__name__ + "). No changes made.\n")


if __name__ == "__main__":
    main()
