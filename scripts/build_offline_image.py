#!/usr/bin/env python3
"""Build/review Docker with verified local wheels and an explicit public context.

The Dockerfile in the checkout is unchanged. With --hash-manifest, both the
host-side verification and Docker RUN steps can work without network; otherwise
the host checks wheel hashes against PyPI over verified HTTPS first. The base
image must already be available or retrievable by Docker with its normal trust.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib
import urllib.request

from check_distribution import ROOT, inventory_files, normalize, safe_member

BOOTSTRAP = ("pip==25.0.1", "setuptools==75.8.0", "wheel==0.45.1")
ONLINE_INSTALL = """RUN pip install --no-cache-dir -r requirements.lock \\
    && pip install --no-cache-dir --no-deps ."""
OFFLINE_INSTALL = """COPY offline-wheels /tmp/mia-wheels
COPY offline-bootstrap.lock offline-runtime.lock /tmp/
RUN python -m pip --isolated install --no-cache-dir --no-index --find-links=/tmp/mia-wheels --require-hashes -r /tmp/offline-bootstrap.lock \\
    && python -m pip --isolated install --no-cache-dir --no-index --find-links=/tmp/mia-wheels --require-hashes --no-deps -r /tmp/offline-runtime.lock \\
    && python -m pip --isolated install --no-cache-dir --no-index --find-links=/tmp/mia-wheels --no-deps --no-build-isolation . \\
    && python -m pip check \\
    && rm -rf /tmp/mia-wheels /tmp/offline-bootstrap.lock /tmp/offline-runtime.lock"""
PACKAGE_SUFFIXES = {".py", ".html", ".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".woff", ".woff2", ".ttf"}


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def public_source_files(root: Path) -> dict[str, bytes]:
    """Copy only known build inputs and public package source, never a checkout."""
    paths = {"Dockerfile", "pyproject.toml", "README.md", "requirements.lock"}
    notices = inventory_files(root)
    paths.update(notices)
    listing = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "mia"], cwd=root
    ).decode().split("\0")
    paths.update(path for path in listing if path and Path(path).suffix in PACKAGE_SUFFIXES)
    result = {}
    for relative in sorted(paths):
        source = root / relative
        if source.is_symlink() or any(parent.is_symlink() for parent in source.parents if parent != root.parent):
            raise ValueError(f"Symbolic link in public build input: {relative}")
        content = source.read_bytes()
        safe_member(relative, content)
        result[relative] = content
    if "mia/app.py" not in result:
        raise ValueError("No public Mia package in source")
    return result


def offline_dockerfile(original: str) -> str:
    if original.count(ONLINE_INSTALL) != 1:
        raise ValueError("Dockerfile installation block changed; review the offline substitution")
    return original.replace(ONLINE_INSTALL, OFFLINE_INSTALL)


def requirements(root: Path) -> list[str]:
    result = [line.strip() for line in (root / "requirements.lock").read_text().splitlines() if line.strip()]
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+", line) for line in result):
        raise ValueError("Offline builds require exact ordinary pinned requirements")
    return result


def verify_wheels(wheelhouse: Path, pins: list[str], recorded: dict | None = None) -> tuple[dict[str, Path], dict]:
    """Verify only required wheels against PyPI or an explicitly trusted manifest."""
    selected = {}
    packages = {}
    for pin in pins:
        name, version = pin.split("==", 1)
        candidates = [path for path in wheelhouse.glob("*.whl")
                      if len(path.name.split("-")) >= 5
                      and normalize(path.name.split("-")[0]) == normalize(name)
                      and path.name.split("-")[1] == version]
        if not candidates:
            raise ValueError(f"Wheelhouse lacks {pin}")
        for path in candidates:
            if path.is_symlink() or not path.is_file():
                raise ValueError("Wheelhouse must contain regular files")
            selected[path.name] = path
        packages[pin] = [path.name for path in candidates]

    trusted = {}
    if recorded is not None:
        if recorded.get("schema_version") != 1:
            raise ValueError("Unsupported wheel hash manifest")
        trusted = recorded["files"]
    else:
        def published(pin: str) -> dict[str, dict]:
            name, version = pin.split("==", 1)
            address = f"https://pypi.org/pypi/{name}/{version}/json"
            with urllib.request.urlopen(address, timeout=30) as response:
                metadata = json.load(response)
            return {artifact["filename"]: {"sha256": artifact["digests"]["sha256"],
                                           "source": artifact["url"], "index": address}
                    for artifact in metadata["urls"] if artifact["packagetype"] == "bdist_wheel"}
        with ThreadPoolExecutor(max_workers=4) as executor:
            for artifacts in executor.map(published, packages):
                trusted.update(artifacts)

    verified = {}
    for name, path in selected.items():
        entry = trusted.get(name)
        if not isinstance(entry, dict) or not re.fullmatch(r"[a-f0-9]{64}", entry.get("sha256", "")):
            raise ValueError(f"No trusted published wheel hash for {name}")
        if digest(path.read_bytes()) != entry["sha256"]:
            raise ValueError(f"Wheel checksum differs: {name}")
        verified[name] = entry
    return selected, {"schema_version": 1, "verification": "published PyPI hashes over verified HTTPS; or explicitly supplied manifest",
                      "packages": packages, "files": verified}


def write_context(context: Path, public: dict[str, bytes], wheels: dict[str, Path], verified: dict, pins: list[str]) -> dict:
    for relative, content in public.items():
        target = context / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (context / "Dockerfile").write_text(offline_dockerfile(public["Dockerfile"].decode()))
    wheel_directory = context / "offline-wheels"
    wheel_directory.mkdir()
    for name, source in wheels.items():
        content = source.read_bytes()
        if digest(content) != verified["files"][name]["sha256"]:
            raise ValueError(f"Wheel changed after verification: {name}")
        (wheel_directory / name).write_bytes(content)
    for filename, selected_pins in [("offline-bootstrap.lock", BOOTSTRAP), ("offline-runtime.lock", pins)]:
        lines = []
        for pin in selected_pins:
            hashes = " ".join("--hash=sha256:" + verified["files"][name]["sha256"]
                              for name in verified["packages"][pin])
            lines.append(pin + " " + hashes)
        (context / filename).write_text("\n".join(lines) + "\n")
    manifest = {"schema_version": 1, "source_files": {name: digest(content) for name, content in public.items()},
                "generated_dockerfile_sha256": digest((context / "Dockerfile").read_bytes()),
                "wheels": verified["files"], "build_network": "none"}
    # Runtime review uses the image's unprivileged UID and read-only mounts.
    # Normalize only these temporary public copies, never checkout permissions.
    context.chmod(0o755)
    for path in context.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    return manifest


INSTALLED_CHECK = r"""
import importlib.metadata as metadata,importlib.util,tomllib
from pathlib import Path
spec=importlib.util.spec_from_file_location('checks','/checks/check_distribution.py')
checks=importlib.util.module_from_spec(spec);spec.loader.exec_module(checks)
expected=checks.inventory_files(Path('/source'),installed=True)
distribution=metadata.distribution('mia-personal-ai')
version=tomllib.loads(Path('/source/pyproject.toml').read_text())['project']['version']
assert distribution.version==version
files={str(f):distribution.locate_file(f).read_bytes() for f in distribution.files if '.dist-info/' in str(f)}
for relative,content in expected.items():
    matches=[value for name,value in files.items() if name.endswith('/'+relative) or name.endswith('/'+Path(relative).name)]
    assert matches and all(value==content for value in matches),relative
print('PASS: installed Docker runtime and',len(expected),'original notice/inventory files; version',version)
"""
HTTP_PERSISTENCE = r"""
import http.cookiejar,json,time,urllib.request,sys
origin='http://127.0.0.1:8123'
client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def request(path,payload=None):
    encoded=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(origin+path,data=encoded,headers={'Content-Type':'application/json','Origin':origin})
    with client.open(req,timeout=3) as response:return json.load(response)
for attempt in range(100):
    try:
        status=request('/api/status');break
    except OSError:time.sleep(.1)
else:raise RuntimeError('Docker service did not start')
if sys.argv[1]=='create':
    assert status['configured'] is False
    request('/api/setup',{'name':'Synthetic Docker review','email':'review@example.test','password':'synthetic-review-password-2030','timezone':'UTC','area_name':'Synthetic area','area_description':'Disposable validation only'})
    area=request('/api/areas')[0]['id']
    request('/api/tasks',{'title':'Synthetic Docker persistence','area_id':area})
    assert len(request('/api/tasks'))==1
    print('PASS: empty Docker installation, local authentication and synthetic task')
else:
    assert status['configured'] is True
    request('/api/login',{'password':'synthetic-review-password-2030'})
    tasks=request('/api/tasks')
    assert len(tasks)==1 and tasks[0]['title']=='Synthetic Docker persistence'
    print('PASS: Docker restart preserves identity and a single synthetic task')
"""


def validate_image(tag: str, root: Path, context: Path) -> None:
    base = ["docker", "run", "--rm", "--network", "none", "--workdir", "/tmp", "--entrypoint", "python"]
    with tempfile.TemporaryDirectory(prefix="mia-public-docker-checks-") as directory:
        checks = Path(directory)
        checks.chmod(0o755)
        for filename in ["package_smoke.py", "check_distribution.py"]:
            source = root / "scripts" / filename
            if source.is_symlink():
                raise ValueError("Validation script must be a regular public file")
            target = checks / filename
            target.write_bytes(source.read_bytes())
            target.chmod(0o644)
        mount = ["--mount", f"type=bind,source={checks},target=/checks,readonly"]
        subprocess.run([*base, *mount, tag, "/checks/package_smoke.py"], check=True)
        subprocess.run([*base, *mount, "--mount", f"type=bind,source={context},target=/source,readonly",
                        tag, "-c", INSTALLED_CHECK], check=True)
    container = subprocess.check_output(["docker", "run", "-d", "--network", "none", "-e", "MIA_AI_ENABLED=false", tag]).decode().strip()
    try:
        subprocess.run(["docker", "exec", container, "python", "-c", HTTP_PERSISTENCE, "create"], check=True)
        subprocess.run(["docker", "restart", container], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["docker", "exec", container, "python", "-c", HTTP_PERSISTENCE, "verify"], check=True)
    finally:
        subprocess.run(["docker", "rm", "-f", container], check=True, stdout=subprocess.DEVNULL)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--hash-manifest", type=Path, help="reuse explicitly trusted wheel hashes instead of contacting PyPI")
    parser.add_argument("--write-hash-manifest", type=Path, help="save reviewed wheel hashes outside the checkout, without overwriting")
    parser.add_argument("--manifest-output", type=Path, help="save public build inputs/digests outside the checkout, without overwriting")
    parser.add_argument("--validate", action="store_true", help="check installed HTTP/assets/notices and synthetic restart persistence")
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,254}", args.tag):
            raise ValueError("Invalid local image tag")
        for output in [args.write_hash_manifest, args.manifest_output]:
            if output is not None and (output.exists() or output.is_symlink()):
                raise ValueError("Output manifest already exists; reuse it or choose a new path")
            if output is not None and (output.resolve() == ROOT or ROOT in output.resolve().parents):
                raise ValueError("Save build manifests outside the source checkout")
        public = public_source_files(ROOT)
        pins = requirements(ROOT)
        recorded = None if args.hash_manifest is None else json.loads(args.hash_manifest.read_text())
        wheels, verified = verify_wheels(args.wheelhouse, [*BOOTSTRAP, *pins], recorded)
        if args.write_hash_manifest:
            args.write_hash_manifest.write_text(json.dumps(verified, indent=2, sort_keys=True) + "\n")
        with tempfile.TemporaryDirectory(prefix="mia-public-docker-") as temporary:
            context = Path(temporary)
            manifest = write_context(context, public, wheels, verified, pins)
            source_sha = digest(json.dumps(manifest["source_files"], sort_keys=True).encode())
            print(f"Verified {len(wheels)} required wheels; explicit public source digest {source_sha}", flush=True)
            subprocess.run(["docker", "build", "--network", "none", "--tag", args.tag, str(context)], check=True)
            image_id = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", args.tag]).decode().strip()
            manifest.update(image_id=image_id, tag=args.tag, source_sha256=source_sha)
            if args.manifest_output:
                args.manifest_output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            if args.validate:
                validate_image(args.tag, ROOT, context)
            print(f"PASS: offline Docker build {args.tag} ({image_id}); checkout Dockerfile unchanged", flush=True)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
