"""Check pinned notices and release archives without network or extraction.

Run from any directory: python scripts/check_distribution.py [--installed]
                           [--archive path.whl --archive path.tar.gz]
This checks the recorded scope; it is not a license grant or legal clearance.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {
    ".git", ".venv", ".aws", ".ssh", ".codex", ".agents", ".pytest_cache",
    "__pycache__", "node_modules", "data", "backups", "logs", "attachments",
}
SECRET_PATTERN = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    rb"|\bgh[pousr]_[A-Za-z0-9]{25,}\b"
    rb"|\bgithub_pat_[A-Za-z0-9_]{30,}\b"
)


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def preserved_notice(root: Path, notice: dict) -> tuple[str, bytes]:
    relative = PurePosixPath(notice["path"])
    if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "THIRD_PARTY_LICENSES":
        raise ValueError("Invalid notice path in inventory")
    content = (root / str(relative)).read_bytes()
    if hashlib.sha256(content).hexdigest() != notice["sha256"]:
        raise ValueError(f"Notice checksum differs: {relative}")
    return str(relative), content


def inventory_files(root: Path = ROOT, *, installed: bool = False) -> dict[str, bytes]:
    """Fail on lock drift, omitted notices or modified notice bytes."""
    inventory = json.loads((root / "THIRD_PARTY_LICENSES/inventory.json").read_text())
    pinned = {}
    for line in (root / "requirements.lock").read_text().splitlines():
        if line.strip():
            name, version = line.split("==", 1)
            pinned[normalize(name)] = version
    recorded = {normalize(p["name"]): p["version"] for p in inventory["packages"]}
    if recorded != pinned or len(recorded) != len(inventory["packages"]):
        raise ValueError("Pinned requirements and third-party inventory differ; review notices")
    expected = {
        "THIRD_PARTY_NOTICES.md": (root / "THIRD_PARTY_NOTICES.md").read_bytes(),
        "THIRD_PARTY_LICENSES/inventory.json":
            (root / "THIRD_PARTY_LICENSES/inventory.json").read_bytes(),
    }
    for package in inventory["packages"]:
        if not package["files"]:
            raise ValueError(f"No preserved notice for {package['name']}")
        distribution = None
        if installed:
            distribution = importlib.metadata.distribution(package["name"])
            if distribution.version != package["version"]:
                raise ValueError(f"Installed version differs: {package['name']}")
        for notice in package["files"]:
            relative, content = preserved_notice(root, notice)
            expected[relative] = content
            if distribution and notice["source"].startswith("installed wheel: "):
                original = notice["source"].removeprefix("installed wheel: ")
                if distribution.locate_file(original).read_bytes() != content:
                    raise ValueError(f"Installed upstream notice differs: {package['name']}")

    rust_path = root / "THIRD_PARTY_LICENSES/rust-inventory.json"
    rust = json.loads(rust_path.read_text())
    expected["THIRD_PARTY_LICENSES/rust-inventory.json"] = rust_path.read_bytes()
    parents = set()
    for source in rust["source_archives"]:
        if pinned.get(normalize(source["package"])) != source["version"]:
            raise ValueError("Rust source inventory differs from pinned Python runtime")
        parent = source["package"] + "==" + source["version"]
        parents.add(parent)
        entries = sum(parent in package["parents"] for package in rust["packages"])
        if entries != source["registry_entry_count"]:
            raise ValueError("Rust source registry count differs from recorded closure")
    seen = set()
    for package in rust["packages"]:
        identity = package["name"], package["version"]
        if identity in seen or not package["files"] or not package["parents"]:
            raise ValueError("Duplicate crate or missing Rust notices/provenance")
        seen.add(identity)
        if not set(package["parents"]).issubset(parents):
            raise ValueError("Rust source inventory has an unknown parent")
        for notice in package["files"]:
            relative, content = preserved_notice(root, notice)
            expected[relative] = content
    actual_paths = {str(path.relative_to(root)) for path in (root / "THIRD_PARTY_LICENSES").rglob("*") if path.is_file()}
    recorded_paths = {path for path in expected if path.startswith("THIRD_PARTY_LICENSES/")}
    if actual_paths != recorded_paths:
        raise ValueError("Third-party directory includes unrecorded files or missing notices")
    return expected


def safe_member(name: str, content: bytes) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"Unsafe archive path: {name}")
    if any(part in FORBIDDEN_PARTS for part in path.parts):
        raise ValueError(f"Local/private directory in archive: {name}")
    if (path.name.startswith(".env") and path.name != ".env.example") or path.suffix in {".pem", ".key", ".db", ".sqlite", ".sqlite3"}:
        raise ValueError(f"Local/private file in archive: {name}")
    if SECRET_PATTERN.search(content):
        raise ValueError(f"Selected credential pattern in archive: {name}")


def archive_files(archive: Path) -> dict[str, bytes]:
    """Read archives in memory; never extract or follow symbolic links."""
    files = {}
    if archive.suffix == ".whl":
        with zipfile.ZipFile(archive) as wheel:
            for member in wheel.infolist():
                if member.is_dir():
                    continue
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f"Symbolic link in archive: {member.filename}")
                if member.filename in files:
                    raise ValueError(f"Duplicate archive member: {member.filename}")
                content = wheel.read(member)
                safe_member(member.filename, content)
                files[member.filename] = content
    else:
        with tarfile.open(archive, "r:gz") as sdist:
            for member in sdist.getmembers():
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError(f"Nonregular member in archive: {member.name}")
                if member.name in files:
                    raise ValueError(f"Duplicate archive member: {member.name}")
                stream = sdist.extractfile(member)
                if stream is None:
                    raise ValueError(f"Unreadable archive member: {member.name}")
                content = stream.read()
                safe_member(member.name, content)
                files[member.name] = content
    return files


def check_archive(archive: Path, expected: dict[str, bytes]) -> None:
    files = archive_files(archive)
    for relative, content in expected.items():
        # Legacy setuptools flattens license filenames; current versions retain paths.
        filename = PurePosixPath(relative).name
        matches = [value for name, value in files.items()
                   if name == relative or name.endswith("/" + relative)
                   or (".dist-info/" in name and name.endswith("/" + filename))]
        if not matches or any(value != content for value in matches):
            raise ValueError(f"Missing or altered notice in {archive.name}: {relative}")
    required_assets = ["mia/static/index.html", "mia/static/assets/app.js", "mia/static/assets/app.css"]
    if not all(any(name.endswith(asset) for name in files) for asset in required_assets):
        raise ValueError(f"Missing interface assets in {archive.name}")
    if archive.suffix != ".whl":
        for relative in ["README.md", "requirements.lock", "docs/PILOT.md", "docs/PILOT-RESULT-TEMPLATE.json"]:
            if not any(name.endswith("/" + relative) for name in files):
                raise ValueError(f"Missing installation/pilot material: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", action="store_true", help="also compare installed runtime versions/notices")
    parser.add_argument("--archive", type=Path, action="append", default=[], help="check wheel or gzip sdist; repeatable")
    args = parser.parse_args()
    try:
        expected = inventory_files(installed=args.installed)
        for archive in args.archive:
            check_archive(archive, expected)
            print(f"PASS: {archive.name}: notices, assets and selected private-file checks")
        print("PASS: pinned runtime notice inventory and checksums")
    except (OSError, ValueError, KeyError, importlib.metadata.PackageNotFoundError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
