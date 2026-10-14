"""Own-server operations for the native client, never exposed to web content.

SSH authentication uses the system agent/an existing key. Host trust is pinned
before any authenticated command. Installation needs the exact Linux artifact
from the trusted app bundle; missing artifacts do not trigger downloads, apt,
global pip, or a pretend installation. A tunnel belongs to one recorded process
birth and one backend installation identity, independently of bridge lifetime.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import signal
import socket
import ssl
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import uuid

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mia.operations import OperationError, _birth, _write
from mia.launcher import remote_url


MAX_JSON = 256 * 1024
MAX_MANIFEST = 8 * 1024 * 1024
MAX_ARTIFACT = 2 * 1024**3
MAX_CONNECTIONS = 32


class RemoteError(OperationError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _fail(code: str, message: str):
    raise RemoteError(code, message)


def _private_path(path: Path, *, directory=False, existing=False) -> Path:
    """No symlink ancestor, private state owned by this user."""
    path = path.absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            _fail("unsafe_path", "O caminho contém um link; nenhum arquivo foi alterado.")
    if existing or path.exists():
        if not path.exists() or (directory and not path.is_dir()) or (not directory and not path.is_file()):
            _fail("unsafe_path", "O arquivo privado esperado não está disponível.")
        if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
            _fail("unsafe_path", "O armazenamento precisa ser privado e pertencer ao seu usuário.")
    return path


def _json_file(path: Path, maximum=MAX_JSON) -> dict:
    if not path.exists():
        return {}
    _private_path(path, existing=True)
    if path.stat().st_size > maximum:
        _fail("invalid_state", "O estado da conexão excede o limite esperado.")
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, UnicodeError):
        _fail("invalid_state", "O estado da conexão precisa de revisão; os dados foram preservados.")


def _payload(value: dict) -> dict:
    if not isinstance(value, dict):
        _fail("invalid_request", "Informe os dados de conexão do seu servidor.")
    host, user = value.get("host"), value.get("user")
    if not isinstance(host, str) or len(host) > 253 or host != host.strip() or host.startswith("-"):
        _fail("invalid_host", "Informe um endereço de servidor válido.")
    try:
        host = str(ipaddress.ip_address(host))
    except ValueError:
        if not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part) for part in host.split(".")):
            _fail("invalid_host", "Informe somente o nome ou IP do servidor.")
        host = host.lower()
    if not isinstance(user, str) or not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.-]{0,63}", user):
        _fail("invalid_user", "Informe um usuário SSH válido.")
    output = {"host": host, "user": user}
    for key, default in (("port", 22), ("remote_port", 8123)):
        port = value.get(key, default)
        if type(port) is not int or not 1 <= port <= 65535:
            _fail("invalid_port", "Informe uma porta válida.")
        output[key] = port
    key = value.get("key_path")
    if key:
        if not isinstance(key, str) or len(key) > 4096 or not Path(key).is_absolute() or any(ord(c) < 32 for c in key):
            _fail("invalid_key", "Escolha uma chave SSH existente no seu computador.")
        _private_path(Path(key), existing=True)
        output["key_path"] = key
    return output


def _fingerprint(key: str) -> str:
    try:
        raw = base64.b64decode(key, validate=True)
        if not 32 <= len(raw) <= 2048:
            raise ValueError
    except ValueError:
        _fail("host_key_unavailable", "Não foi possível verificar a chave do servidor.")
    return "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")


def _host_label(config: dict) -> str:
    return config["host"] if config["port"] == 22 else f"[{config['host']}]:{config['port']}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _fail("redirect_refused", "O endereço redirecionou para outro destino. Informe o endereço HTTPS final da sua Mia.")


def _http_json(url: str) -> dict:
    opener = urllib.request.build_opener(_NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()), urllib.request.ProxyHandler({}))
    try:
        with opener.open(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=5) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                raise ValueError
            body = response.read(MAX_JSON + 1)
            if len(body) > MAX_JSON:
                raise ValueError
            result = json.loads(body)
            if not isinstance(result, dict):
                raise ValueError
            return result
    except RemoteError:
        raise
    except (OSError, ValueError, urllib.error.URLError):
        _fail("connection_offline", "Não foi possível acessar esta Mia com segurança. Confira o endereço e a conexão; nada foi reinstalado.")


def _backend(health: dict, status: dict, installation: dict) -> dict:
    version = health.get("version")
    identity = installation.get("installation_id")
    try:
        if str(uuid.UUID(identity)) != identity:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        _fail("protocol_unsupported", "Esta Mia precisa de uma versão compatível com o aplicativo antes de conectar.")
    if health.get("ok") is not True or not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9._+-]{1,80}", version) or status.get("version") != version or installation.get("version") != version or type(installation.get("desktop_protocol")) is not int or installation["desktop_protocol"] != 1 or type(installation.get("cookie_secure")) is not bool or type(status.get("configured")) is not bool:
        _fail("protocol_unsupported", "A instalação não confirmou uma versão e identidade compatíveis.")
    secure = installation["cookie_secure"]
    if installation.get("transport_policy") != ("https_required" if secure else "private_connection_only"):
        _fail("protocol_unsupported", "A instalação não confirmou sua política de acesso.")
    return {"installation_id": identity, "version": version, "configured": status["configured"], "cookie_secure": secure}


# A fixed Python program; payload goes through stdin, never into shell text.
_PROBE = r'''
import json, os, pathlib, platform, pwd, shutil, socket, subprocess, sys, urllib.request
p=json.loads(sys.stdin.buffer.readline(65537))
if set(p)-{'remote_port'} or type(p.get('remote_port')) is not int or not 1<=p['remote_port']<=65535: raise ValueError()
home=pathlib.Path.home(); uid=os.getuid()
os_release={}
for line in pathlib.Path('/etc/os-release').read_text().splitlines():
 k,sep,v=line.partition('=')
 if sep: os_release[k]=v.strip('"')
safe=True
for path in (home,home/'.local',home/'.local/share',home/'.local/share/mia-demo'):
 if path.is_symlink() or path.exists() and (not path.is_dir() or path.stat().st_uid!=uid): safe=False
if (home/'.local/share/mia-demo').exists() and (home/'.local/share/mia-demo').stat().st_mode&0o077: safe=False
systemd=False
try:
 result=subprocess.run(['/usr/bin/systemctl','--user','show-environment'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
 systemd=result.returncode==0
except (OSError,subprocess.TimeoutExpired): pass
linger=(pathlib.Path('/var/lib/systemd/linger')/pwd.getpwuid(uid).pw_name).is_file()
available=False
s=socket.socket()
try: s.bind(('127.0.0.1',p['remote_port'])); available=True
except OSError: pass
finally: s.close()
backend=None
if not available:
 try:
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  class NoRedirect(urllib.request.HTTPRedirectHandler):
   def redirect_request(self,*args): raise ValueError()
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
  backend={}
  for name,path in [('health','health'),('status','api/status'),('installation','api/installation')]:
   with opener.open('http://127.0.0.1:'+str(p['remote_port'])+'/'+path,timeout=3) as response:
    raw=response.read(262145)
    if response.status!=200 or response.headers.get_content_type()!='application/json' or len(raw)>262144: raise ValueError()
    backend[name]=json.loads(raw)
 except Exception: backend=None
print(json.dumps({'platform':os_release.get('ID'),'platform_version':os_release.get('VERSION_ID'),'architecture':platform.machine(),'home_safe':safe,'free_bytes':shutil.disk_usage(home).free,'user_service':systemd,'linger':linger,'port_available':available,'backend':backend}))
'''


# Archive is generated from the verified bundle and sent only to the pinned host.
# Stage/installation/service names are derived solely from an approved UUID.
_INSTALL = r'''
import hashlib,json,os,pathlib,platform,pwd,shutil,socket,subprocess,sys,tarfile,tomllib,uuid
h=json.loads(sys.stdin.buffer.readline(8388609))
identity=h['identity']; assert str(uuid.UUID(identity))==identity
manifest=h['manifest']; assert manifest['format']==1 and manifest['platform']=='ubuntu24.04' and manifest['architecture']=='amd64'
port=h['remote_port']; assert type(port) is int and 1<=port<=65535
release={}
for line in pathlib.Path('/etc/os-release').read_text().splitlines():
 k,sep,v=line.partition('=')
 if sep: release[k]=v.strip('"')
assert release.get('ID')=='ubuntu' and release.get('VERSION_ID')=='24.04' and platform.machine()=='x86_64'
assert shutil.disk_usage(pathlib.Path.home()).free>=3221225472
assert (pathlib.Path('/var/lib/systemd/linger')/pwd.getpwuid(os.getuid()).pw_name).is_file()
check=subprocess.run(['/usr/bin/systemctl','--user','show-environment'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
assert check.returncode==0
with socket.socket() as check: check.bind(('127.0.0.1',port))
home=pathlib.Path.home(); base=home/'.local/share/mia-demo'
for p in (home,home/'.local',home/'.local/share',base):
 if p.is_symlink() or p.exists() and (not p.is_dir() or p.stat().st_uid!=os.getuid()): raise ValueError('unsafe path')
base.mkdir(parents=True,mode=0o700,exist_ok=True)
assert not base.stat().st_mode&0o077
artifacts=base/'artifacts'; installations=base/'installations'
for p in (artifacts,installations):
 if p.is_symlink(): raise ValueError('unsafe path')
 p.mkdir(mode=0o700,exist_ok=True)
 assert p.stat().st_uid==os.getuid() and not p.stat().st_mode&0o077
bundle=artifacts/identity; root=installations/identity; journal=base/('install-'+identity+'.json')
if root.exists() or bundle.exists() or journal.exists():
 print(json.dumps({'ok':False,'code':'recovery_required'})); sys.exit(0)
with os.fdopen(os.open(journal,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'w') as state: state.write(json.dumps({'phase':'extracting','installation_id':identity}))
bundle.mkdir(mode=0o700)
expected=manifest['files']; seen=set(); total=0; links=[]
try:
 with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
  for member in archive:
   path=pathlib.PurePosixPath(member.name)
   if path.is_absolute() or '..' in path.parts or len(path.parts)<2 or path.parts[0] not in ('runtime','source','wheelhouse') or member.name in seen: raise ValueError('invalid archive')
   target=bundle.joinpath(*path.parts)
   for parent in (target.parent,*target.parent.parents):
    if parent==bundle.parent: break
    if parent.is_symlink(): raise ValueError('link ancestor')
   if member.isdir(): target.mkdir(parents=True,mode=0o700,exist_ok=True); continue
   seen.add(member.name); entry=expected.get(member.name)
   if not entry: raise ValueError('unexpected file')
   target.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
   if member.issym():
    if path.parts[0]!='runtime' or entry!={'symlink':member.linkname} or pathlib.PurePosixPath(member.linkname).is_absolute(): raise ValueError('invalid link')
    target.symlink_to(member.linkname); links.append(target)
   elif member.isfile():
    total+=member.size
    if total>2147483648 or member.size<0: raise ValueError('artifact limit')
    digest=hashlib.sha256()
    with archive.extractfile(member) as incoming, target.open('xb') as outgoing:
     target.chmod(0o700 if entry.get('executable') else 0o600)
     while block:=incoming.read(1048576): digest.update(block); outgoing.write(block)
    if digest.hexdigest()!=entry.get('sha256'): raise ValueError('hash mismatch')
   else: raise ValueError('special file')
 if seen!=set(expected): raise ValueError('missing file')
 for link in links:
  if not link.resolve().is_relative_to(bundle/'runtime') or not link.resolve().is_file(): raise ValueError('external link')
 version=tomllib.loads((bundle/'source/pyproject.toml').read_text())['project']['version']
 if version!=manifest['version']: raise ValueError('version mismatch')
 env=bundle/'new-machine.env'; env.write_text('MIA_AI_ENABLED=false\nMIA_COOKIE_SECURE=false\nMIA_INSTALLATION_MODE=remote\n'); env.chmod(0o600)
 log=base/('install-'+identity+'.log')
 journal.write_text(json.dumps({'phase':'installing','installation_id':identity}))
 runtime=bundle/'runtime/bin/python3'
 with log.open('ab') as output:
  log.chmod(0o600)
  subprocess.run([str(runtime),'-I',str(bundle/'source/mia/operations.py'),'--root',str(root),'install','--source',str(bundle/'source'),'--wheelhouse',str(bundle/'wheelhouse'),'--offline','--port',str(port),'--env-file',str(env),'--installation-id',identity],stdout=output,stderr=output,check=True,timeout=600)
  activation="import sys;sys.path.insert(0,sys.argv[1]);from pathlib import Path;from mia.operations import Manager;from mia.installation import service_plan,apply_service_plan;m=Manager(Path(sys.argv[2]));p=service_plan(m,'systemd');apply_service_plan(m,p,approve_sha256=p['sha256'])"
  journal.write_text(json.dumps({'phase':'activating','installation_id':identity}))
  subprocess.run([str(runtime),'-I','-c',activation,str(bundle/'source'),str(root)],stdout=output,stderr=output,check=True,timeout=60)
 # The API identity is generated by Manager.install and checked again by client.
 journal.write_text(json.dumps({'phase':'complete','installation_id':identity}))
 installed=json.loads((root/'installation.json').read_text())['installation_id']
 assert str(uuid.UUID(installed))==installed
 print(json.dumps({'ok':True,'version':version,'root_id':identity,'installation_id':installed,'service_activated':True}))
except Exception:
 journal.write_text(json.dumps({'phase':'recovery_required','installation_id':identity}))
 print(json.dumps({'ok':False,'code':'recovery_required'}))
'''


class SystemSSH:
    """Structured commands with no user shell text and bounded output."""
    def __init__(self, home: Path):
        self.home = home

    def _env(self):
        value = {"HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C"}
        if os.environ.get("SSH_AUTH_SOCK"):
            value["SSH_AUTH_SOCK"] = os.environ["SSH_AUTH_SOCK"]
        return value

    def _run(self, command: list[str], *, incoming=None, timeout=15, maximum=MAX_JSON, allowed_codes=(0,)) -> bytes:
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            try:
                result = subprocess.run(command, stdin=incoming, stdout=output, stderr=errors, timeout=timeout, env=self._env(), check=False)
                output.seek(0)
                body = output.read(maximum + 1)
                if result.returncode not in allowed_codes or len(body) > maximum:
                    raise ValueError
                return body
            except (OSError, ValueError, subprocess.TimeoutExpired):
                _fail("ssh_unavailable", "Não foi possível conectar por SSH. Confira o servidor e sua chave ou agente; nenhuma senha foi registrada.")

    def scan(self, config: dict) -> str:
        result = self._run(["/usr/bin/ssh-keyscan", "-T", "5", "-p", str(config["port"]), "-t", "ed25519", config["host"]], maximum=65536)
        found = set()
        for line in result.decode("ascii").splitlines():
            fields = line.split()
            if fields and not fields[0].startswith("#") and len(fields) == 3 and fields[1] == "ssh-ed25519":
                _fingerprint(fields[2])
                found.add(fields[2])
        if len(found) != 1:
            _fail("host_key_unavailable", "O servidor não confirmou uma única chave Ed25519. Confira sua identidade antes de conectar.")
        return found.pop()

    def known(self, config: dict, key: str) -> tuple[bool, bool]:
        path = self.home / ".ssh/known_hosts"
        if not path.exists():
            return False, False
        if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid() or path.stat().st_size > 8 * 1024**2:
            return False, False
        result = self._run(["/usr/bin/ssh-keygen", "-F", _host_label(config), "-f", str(path)], maximum=1024**2, allowed_codes=(0, 1))
        keys = []
        for line in result.decode("ascii").splitlines():
            fields = line.split()
            if len(fields) == 4 and fields[0] == "@revoked" and fields[2] == "ssh-ed25519" and fields[3] == key:
                _fail("host_key_revoked", "Esta chave do servidor foi revogada no seu Mac. A conexão foi bloqueada e não pode ser aprovada novamente pelo app.")
            if len(fields) == 3 and fields[1] == "ssh-ed25519":
                keys.append(fields[2])
        return key in keys, bool(keys) and key not in keys

    def arguments(self, config: dict, known_hosts: Path) -> list[str]:
        args = ["/usr/bin/ssh", "-F", "/dev/null", "-T", "-p", str(config["port"]), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "HostKeyAlgorithms=ssh-ed25519", "-o", "UserKnownHostsFile=" + str(known_hosts), "-o", "GlobalKnownHostsFile=/dev/null", "-o", "ForwardAgent=no", "-o", "PermitLocalCommand=no", "-o", "ConnectTimeout=10", "-o", "ConnectionAttempts=1", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=2", "-o", "ExitOnForwardFailure=yes"]
        if config.get("key_path"):
            args += ["-o", "IdentitiesOnly=yes", "-i", config["key_path"]]
        return args

    def _program(self, config: dict, known: Path, program: str, incoming, timeout=30) -> dict:
        # Only this constant program is quoted. Untrusted values stay in JSON stdin.
        command = self.arguments(config, known) + [config["user"] + "@" + config["host"], "/usr/bin/python3 -I -c " + shlex.quote(program)]
        body = self._run(command, incoming=incoming, timeout=timeout)
        try:
            value = json.loads(body)
            if not isinstance(value, dict):
                raise ValueError
            return value
        except ValueError:
            _fail("invalid_server_response", "O servidor não confirmou o resultado esperado; preserve o estado antes de tentar novamente.")

    def probe(self, config: dict, known: Path) -> dict:
        with tempfile.TemporaryFile() as incoming:
            incoming.write(json.dumps({"remote_port": config["remote_port"]}).encode() + b"\n")
            incoming.seek(0)
            return self._program(config, known, _PROBE, incoming)

    def install(self, config: dict, known: Path, manifest: dict, payload: Path, identity: str) -> dict:
        with tempfile.TemporaryFile() as incoming:
            incoming.write(json.dumps({"manifest": manifest, "identity": identity, "remote_port": config["remote_port"]}).encode() + b"\n")
            with tarfile.open(fileobj=incoming, mode="w") as archive:
                for name in sorted(manifest["files"]):
                    archive.add(payload / name, arcname=name, recursive=False)
            incoming.seek(0)
            return self._program(config, known, _INSTALL, incoming, timeout=720)

    def http(self, url):
        return _http_json(url)

    def birth(self, pid):
        return _birth(pid)

    def stop(self, record):
        for prefix in ("", "child_"):
            pid, birth = record.get(prefix + "pid"), record.get(prefix + "birth")
            if type(pid) is int and birth and self.birth(pid) == birth:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def spawn(self, state: Path, resources: Path) -> None:
        script = resources / "source/mia/desktop_remote.py"
        if script.is_symlink() or not script.is_file():
            _fail("artifact_unavailable", "O aplicativo não contém o componente de conexão necessário.")
        log = state.parent / "tunnel.log"
        _private_path(log)
        with log.open("ab") as output:
            log.chmod(0o600)
            subprocess.Popen([sys.executable, "-I", str(script), "--tunnel-state", str(state)], stdin=subprocess.DEVNULL, stdout=output, stderr=output, env=self._env(), start_new_session=True, close_fds=True)


def artifact(resources: Path) -> tuple[dict, Path, str]:
    """Exact integrity of the Linux payload authenticated by the app bundle."""
    root = resources / "remote-runtime"
    manifest_path, payload = root / "manifest.json", root / "payload"
    if not manifest_path.exists() or not payload.exists():
        _fail("artifact_unavailable", "Esta versão do app ainda não inclui o instalador verificado para Ubuntu 24.04 amd64. Você pode conectar a uma Mia existente.")
    for path in (root, manifest_path, payload):
        if path.is_symlink():
            _fail("artifact_invalid", "O instalador de servidor não corresponde ao aplicativo verificado.")
    if manifest_path.stat().st_size > MAX_MANIFEST:
        _fail("artifact_invalid", "O manifesto do instalador excede o limite esperado.")
    try:
        manifest = json.loads(manifest_path.read_text())
        files = manifest["files"]
        if manifest["format"] != 1 or manifest["platform"] != "ubuntu24.04" or manifest["architecture"] != "amd64" or manifest["python_version"] not in ("3.12", "3.13") or not isinstance(files, dict) or not 1 <= len(files) <= 100000:
            raise ValueError
        inventory, total = {}, 0
        for path in sorted(payload.rglob("*")):
            relative = path.relative_to(payload).as_posix()
            first = PurePosixPath(relative).parts[0]
            if first not in ("runtime", "source", "wheelhouse"):
                raise ValueError
            parts = PurePosixPath(relative).parts
            if first == "source" and len(parts) > 1:
                public_root = parts[1]
                allowed = public_root in ("mia", "pyproject.toml", "requirements.lock", "README.md", "MANIFEST.in", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "THIRD_PARTY_LICENSES")
                if not allowed or public_root == "mia" and any(part in ("data", "__pycache__", ".git", ".env") for part in parts[2:]):
                    raise ValueError
            if path.is_symlink():
                link = os.readlink(path)
                if first != "runtime" or Path(link).is_absolute() or not path.resolve().is_relative_to((payload / "runtime").resolve()) or not path.resolve().is_file():
                    raise ValueError
                inventory[relative] = {"symlink": link}
            elif path.is_file():
                total += path.stat().st_size
                if total > MAX_ARTIFACT:
                    raise ValueError
                with path.open("rb") as incoming:
                    inventory[relative] = {"sha256": hashlib.file_digest(incoming, "sha256").hexdigest(), "executable": bool(path.stat().st_mode & 0o111)}
            elif not path.is_dir():
                raise ValueError
        if inventory != files:
            raise ValueError
        for kind in ("runtime", "wheelhouse"):
            provenance = manifest[kind + "_provenance"]
            origin = urllib.parse.urlsplit(provenance["source_url"])
            trusted = (origin.hostname in ("python.org", "www.python.org") or origin.hostname == "github.com" and origin.path.startswith("/astral-sh/python-build-standalone/")) if kind == "runtime" else origin.hostname in ("pypi.org", "files.pythonhosted.org")
            expected_subset = {name[len(kind) + 1:]: details for name, details in inventory.items() if name.startswith(kind + "/")}
            if provenance.get("format") != 1 or provenance.get("platform") != "linux" or provenance.get("architecture") not in ("amd64", "x86_64") or provenance.get("python_version") != manifest["python_version"] or provenance.get("files") != expected_subset or origin.scheme != "https" or origin.username or origin.password or origin.query or origin.fragment or not trusted:
                raise ValueError
        required = ("runtime/bin/python3", "source/mia/operations.py", "source/pyproject.toml", "source/requirements.lock", "source/LICENSE", "source/NOTICE", "source/THIRD_PARTY_NOTICES.md")
        if any(not (payload / path).is_file() for path in required) or not (payload / "runtime/bin/python3").stat().st_mode & 0o111:
            raise ValueError
        metadata = tomllib.loads((payload / "source/pyproject.toml").read_text())["project"]
        if metadata.get("name") != "mia-personal-ai" or metadata.get("version") != manifest["version"] or not re.fullmatch(r"[A-Za-z0-9._+-]{1,80}", manifest["version"]):
            raise ValueError
        if not list((payload / "wheelhouse").glob("*.whl")) or any(p.suffix != ".whl" or not p.is_file() or p.is_symlink() for p in (payload / "wheelhouse").iterdir()):
            raise ValueError
        return manifest, payload, hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    except (KeyError, ValueError, OSError, UnicodeError, TypeError):
        _fail("artifact_invalid", "O instalador de servidor falhou na verificação. Nenhum componente foi executado.")


class RemoteController:
    def __init__(self, resources: Path, home: Path | None = None, *, adapter=None):
        self.resources = Path(resources).absolute()
        self.home = Path(home or Path.home()).absolute()
        self.base = self.home / "Library/Application Support/Mia/remote"
        self.adapter = adapter or SystemSSH(self.home)

    def _base(self):
        _private_path(self.base, directory=True)
        self.base.mkdir(parents=True, mode=0o700, exist_ok=True)
        _private_path(self.base, directory=True, existing=True)
        return self.base

    def _identity(self, config: dict):
        return hashlib.sha256(json.dumps({key: config[key] for key in ("host", "user", "port", "remote_port")}, sort_keys=True).encode()).hexdigest()[:32]

    def _trust(self, config: dict, approved: str | None):
        key = self.adapter.scan(config)
        fingerprint = _fingerprint(key)
        known, changed = self.adapter.known(config, key)
        path = self._base() / (hashlib.sha256(_host_label(config).encode()).hexdigest() + ".known_hosts")
        if path.exists():
            _private_path(path, existing=True)
            if path.stat().st_size > 4096 or path.read_text() != _host_label(config) + " ssh-ed25519 " + key + "\n":
                _fail("host_key_changed", "A chave do servidor mudou. A conexão foi bloqueada; confirme a mudança fora da Mia antes de continuar.")
            known = True
        if changed:
            _fail("host_key_changed", "A chave difere daquela conhecida pelo seu Mac. A conexão foi bloqueada.")
        if approved is not None and approved != fingerprint:
            _fail("host_key_changed", "A chave mudou desde sua confirmação. Nenhum comando autenticado foi enviado.")
        if not known and approved is None:
            return fingerprint, False, None
        if not path.exists():
            with path.open("x") as outgoing:
                path.chmod(0o600)
                outgoing.write(_host_label(config) + " ssh-ed25519 " + key + "\n")
        return fingerprint, True, path

    def _verified(self, config: dict, payload: dict):
        fingerprint, known, path = self._trust(config, payload.get("approved_host_fingerprint"))
        if not known:
            _fail("host_approval_required", "Confirme a impressão digital do seu servidor antes de conectar.")
        return fingerprint, path

    def remote_preflight(self, payload: dict):
        config = _payload(payload)
        fingerprint, known, pin = self._trust(config, payload.get("approved_host_fingerprint"))
        result = {**{k: config[k] for k in ("host", "user", "port", "remote_port")}, "host_key_fingerprint": fingerprint, "host_key_known": known, "platform": None, "architecture": None, "supported": False, "install_ready": False, "summary": []}
        if not known:
            return {**result, "approval_required": True, "summary": ["Confira esta impressão digital com o administrador do seu servidor. Nenhum comando autenticado foi enviado."]}
        probe = self.adapter.probe(config, pin)
        supported = probe.get("platform") == "ubuntu" and probe.get("platform_version") == "24.04" and probe.get("architecture") == "x86_64"
        result.update(platform=" ".join(str(probe.get(x, "")) for x in ("platform", "platform_version")), architecture=probe.get("architecture"), supported=supported, user_service=probe.get("user_service") is True, linger=probe.get("linger") is True, port_available=probe.get("port_available") is True)
        if probe.get("backend"):
            try:
                result["existing_installation"] = _backend(**probe["backend"])
            except (RemoteError, TypeError):
                result["existing_installation"] = {"compatible": False}
        if not supported:
            result["summary"] = ["A instalação guiada desta versão atende Ubuntu 24.04 amd64. Outros sistemas podem conectar a uma Mia existente."]
            return result
        if probe.get("home_safe") is not True or type(probe.get("free_bytes")) is not int or probe["free_bytes"] < 3 * 1024**3:
            result["summary"] = ["O servidor precisa de armazenamento privado gravável e pelo menos 3 GiB livres."]
            return result
        if probe.get("user_service") is not True or probe.get("linger") is not True:
            result["summary"] = ["O serviço do usuário precisa estar disponível e autorizado a funcionar após logout. O app não altera permissões administrativas nem outros serviços."]
            result["requirement"] = "persistent_user_service"
            return result
        if probe.get("port_available") is not True:
            result["summary"] = ["A porta escolhida está ocupada. Conecte à Mia existente ou escolha outra porta; nenhum serviço será parado."]
            return result
        try:
            manifest, _, checksum = artifact(self.resources)
        except RemoteError as error:
            result.update(artifact_state=error.code, summary=[str(error)])
            return result
        connection_id = self._identity(config)
        plan_path = self._base() / (connection_id + ".plan.json")
        prior = _json_file(plan_path)
        inputs = {"config": config, "fingerprint": fingerprint, "artifact_sha256": checksum}
        identity = prior.get("identity") if prior.get("inputs") == inputs else str(uuid.uuid4())
        summary = ["Criar uma Mia vazia em um diretório privado novo no seu servidor.", "Usar apenas o runtime e dependências verificados incluídos neste app.", "Ativar somente o serviço desta Mia para o seu usuário; preservar outros aplicativos e arquivos.", "Conectar por túnel SSH privado; acesso por iPhone exige HTTPS posterior."]
        plan = {"format": 1, "inputs": inputs, "identity": identity, "version": manifest["version"], "summary": summary}
        checksum_plan = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        _write(plan_path, {**plan, "sha256": checksum_plan})
        return {**result, "install_ready": True, "artifact_state": "verified", "plan_sha256": checksum_plan, "version": manifest["version"], "summary": summary}

    def remote_install(self, payload: dict):
        config = _payload(payload)
        fingerprint, pin = self._verified(config, payload)
        plan_path = self._base() / (self._identity(config) + ".plan.json")
        approved = _json_file(plan_path)
        plan_body = {key: value for key, value in approved.items() if key != "sha256"}
        plan_checksum = hashlib.sha256(json.dumps(plan_body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if not approved or payload.get("approve_sha256") != approved.get("sha256") or plan_checksum != approved.get("sha256"):
            _fail("plan_approval_required", "Confira e confirme o plano de instalação antes de continuar.")
        manifest, directory, checksum = artifact(self.resources)
        if approved.get("inputs") != {"config": config, "fingerprint": fingerprint, "artifact_sha256": checksum}:
            _fail("plan_changed", "O destino ou instalador mudou. Revise um novo plano antes de continuar.")
        probe = self.adapter.probe(config, pin)
        if probe.get("platform") != "ubuntu" or probe.get("platform_version") != "24.04" or probe.get("architecture") != "x86_64" or probe.get("home_safe") is not True or probe.get("user_service") is not True or probe.get("linger") is not True or probe.get("port_available") is not True or type(probe.get("free_bytes")) is not int or probe["free_bytes"] < 3 * 1024**3:
            _fail("preflight_changed", "As condições do servidor mudaram. Nenhuma instalação foi iniciada; confira o destino novamente.")
        result = self.adapter.install(config, pin, manifest, directory, approved["identity"])
        if result.get("ok") is not True or result.get("service_activated") is not True or result.get("version") != manifest["version"] or result.get("root_id") != approved["identity"]:
            _fail("recovery_required", "A instalação não terminou. O estado e o log privados foram preservados no servidor; não será reinstalada automaticamente.")
        try:
            connection = self.remote_connect(payload)
            if connection["version"] != manifest["version"] or connection.get("configured") is not False or connection["installation_id"] != result.get("installation_id"):
                _fail("installation_verification_failed", "A instalação não confirmou uma Mia vazia na versão esperada. Nenhum contexto foi importado.")
            return connection
        except RemoteError as error:
            if error.code == "connection_offline":
                _fail("installation_pending_connection", "O serviço foi ativado, mas a conexão ainda não foi confirmada. Seus dados estão preservados; tente conectar sem reinstalar.")
            raise

    def _directory(self, connection_id):
        if not isinstance(connection_id, str) or not re.fullmatch(r"[0-9a-f]{32}", connection_id):
            _fail("invalid_connection", "Escolha uma conexão da Mia.")
        directory = self._base() / connection_id
        _private_path(directory, directory=True)
        if not directory.exists():
            if sum(p.is_dir() and re.fullmatch(r"[0-9a-f]{32}", p.name) is not None for p in self.base.iterdir()) >= MAX_CONNECTIONS:
                _fail("connection_limit", "O limite de conexões salvas foi atingido.")
            directory.mkdir(mode=0o700)
        return directory

    def _record(self, directory):
        record = _json_file(directory / "process.json")
        child_live = type(record.get("child_pid")) is int and record.get("child_birth") and self.adapter.birth(record["child_pid"]) == record["child_birth"]
        if child_live and type(record.get("pid")) is int and record.get("birth") and self.adapter.birth(record["pid"]) == record["birth"]:
            return record
        if child_live:
            return {**record, "pid": record["child_pid"], "birth": record["child_birth"]}
        return {}

    def _check_http(self, url):
        return _backend(self.adapter.http(url + "health"), self.adapter.http(url + "api/status"), self.adapter.http(url + "api/installation"))

    def _connection(self, value, *, running=False, backend=None):
        allowed = ("connection_id", "installation_id", "mode", "url", "version", "host", "user", "port", "remote_port", "configured")
        result = {key: value[key] for key in allowed if key in value}
        if backend:
            result.update({key: backend[key] for key in ("installation_id", "version", "configured")})
        return {**result, "running": running}

    def remote_connect(self, payload: dict):
        if isinstance(payload, dict) and set(payload) == {"connection_id"}:
            directory = self._directory(payload["connection_id"])
            stored = _json_file(directory / "connection.json")
            if stored.get("mode") != "ssh" or self._identity(stored) != payload["connection_id"]:
                _fail("invalid_connection", "Esta conexão SSH não está disponível no aplicativo.")
            payload = {key: stored[key] for key in ("host", "user", "port", "remote_port", "key_path") if key in stored}
        config = _payload(payload)
        _, pin = self._verified(config, payload)
        probe = self.adapter.probe(config, pin)
        try:
            backend = _backend(**probe["backend"])
        except (KeyError, TypeError):
            _fail("connection_offline", "A Mia não respondeu no servidor e porta escolhidos. Nenhuma instalação foi criada.")
        if backend["cookie_secure"]:
            _fail("https_required", "Esta Mia exige HTTPS. Conecte ao endereço HTTPS existente; sua política de segurança será preservada.")
        identity = self._identity(config)
        directory = self._directory(identity)
        path = directory / "connection.json"
        prior = _json_file(path)
        if prior.get("installation_id") and prior["installation_id"] != backend["installation_id"]:
            _fail("installation_changed", "Este destino agora respondeu com outra instalação. Revise a nova Mia antes de iniciar uma sessão.")
        record = self._record(directory)
        if record and record.get("ready") is True:
            live = self._check_http(prior["url"])
            if live["installation_id"] != backend["installation_id"]:
                _fail("installation_changed", "O túnel respondeu com outra instalação; a conexão foi bloqueada.")
            return self._connection(prior, running=True, backend=live)
        port = prior.get("local_port")
        with socket.socket() as available:
            try:
                available.bind(("127.0.0.1", port if type(port) is int and 1024 <= port <= 65535 else 0))
            except OSError:
                available.bind(("127.0.0.1", 0))
            port = available.getsockname()[1]
        connection = {"connection_id": identity, **config, **backend, "mode": "ssh", "local_port": port, "url": f"http://127.0.0.1:{port}/", "known_hosts": str(pin)}
        _write(path, connection)
        self.adapter.spawn(path, self.resources)
        deadline = time.monotonic() + 15
        last_error = None
        while time.monotonic() < deadline:
            try:
                if self._record(directory).get("ready") is True:
                    live = self._check_http(connection["url"])
                    if live["installation_id"] != backend["installation_id"] or live["cookie_secure"]:
                        self.adapter.stop(self._record(directory))
                        _fail("installation_changed", "A conexão não confirmou o destino esperado. O túnel foi encerrado.")
                    return self._connection(connection, running=True, backend=live)
            except RemoteError as error:
                if error.code != "connection_offline":
                    raise
                last_error = error
            time.sleep(0.1)
        self.adapter.stop(self._record(directory))
        if last_error:
            raise last_error
        _fail("connection_offline", "Não foi possível abrir o túnel. A Mia no servidor continua preservada; tente conectar novamente.")

    def remote_disconnect(self, payload: dict):
        directory = self._directory(payload.get("connection_id"))
        value = _json_file(directory / "connection.json")
        record = self._record(directory)
        self.adapter.stop(record)
        # Metadata is retained for an explicit reconnection; never stop backend.
        return self._connection(value, running=False)

    def https_connect(self, payload: dict):
        if not isinstance(payload, dict) or not isinstance(payload.get("url"), str):
            _fail("invalid_url", "Informe o endereço HTTPS da sua Mia.")
        url = remote_url(payload["url"])
        backend = self._check_http(url)
        identity = hashlib.sha256(("https:" + url).encode()).hexdigest()[:32]
        directory = self._directory(identity)
        path = directory / "connection.json"
        prior = _json_file(path)
        if prior.get("installation_id") and prior["installation_id"] != backend["installation_id"]:
            _fail("installation_changed", "Este endereço agora respondeu com outra Mia. Revise a nova instalação antes de conectar.")
        value = {"connection_id": identity, "mode": "https", "url": url, **backend}
        _write(path, value)
        return self._connection(value, running=True)

    def connections(self):
        if not self.base.exists():
            return []
        _private_path(self.base, directory=True, existing=True)
        result = []
        for path in sorted(self.base.iterdir()):
            if re.fullmatch(r"[0-9a-f]{32}", path.name) and len(result) < MAX_CONNECTIONS:
                try:
                    _private_path(path, directory=True, existing=True)
                    value = _json_file(path / "connection.json")
                    if value:
                        result.append(self._connection(value, running=self._record(path).get("ready") is True if value.get("mode") == "ssh" else False))
                except (RemoteError, OSError):
                    continue
        return result

    def handle(self, action, payload):
        if action not in ("remote_preflight", "remote_install", "remote_connect", "remote_disconnect", "https_connect"):
            _fail("unknown_action", "Esta ação não está disponível no aplicativo.")
        lock_path = self._base() / "operations.lock"
        _private_path(lock_path)
        with lock_path.open("a+") as lock:
            lock_path.chmod(0o600)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                _fail("operation_busy", "Outra operação de conexão está em andamento. Aguarde antes de continuar.")
            return getattr(self, action)(payload)


def _supervise(state: Path):
    """A private, persistent owner for the SSH child, outside bridge lifetime."""
    _private_path(state, existing=True)
    config = _json_file(state)
    endpoint = _payload(config)
    port = config.get("local_port")
    if type(port) is not int or not 1024 <= port <= 65535 or config.get("mode") != "ssh":
        _fail("invalid_state", "A conexão salva não está pronta para iniciar.")
    home = Path.home()
    expected_base = home / "Library/Application Support/Mia/remote"
    if state.parent.parent != expected_base or state.name != "connection.json" or not re.fullmatch(r"[0-9a-f]{32}", state.parent.name):
        _fail("invalid_state", "A conexão não pertence ao armazenamento do aplicativo.")
    known = Path(config.get("known_hosts", ""))
    if known.parent != expected_base or not re.fullmatch(r"[0-9a-f]{64}\.known_hosts", known.name):
        _fail("invalid_state", "A identidade do servidor não está registrada.")
    _private_path(known, existing=True)
    adapter = SystemSSH(home)
    lock_path = state.parent / "tunnel.lock"
    _private_path(lock_path)
    with lock_path.open("a+") as lock:
        lock_path.chmod(0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        # The mux socket is created only after SSH sets up its forwarding.
        # Checking it prevents accepting an unrelated listener that won a race
        # for the selected local port before SSH's bind failure is observed.
        with tempfile.TemporaryDirectory(prefix="mia-ssh-" + str(os.getuid()) + "-") as control_directory:
            os.chmod(control_directory, 0o700)
            control = Path(control_directory) / "ctl"
            if len(str(control).encode()) > 100:
                _fail("tunnel_unavailable", "O caminho do controle SSH excede o limite deste sistema.")
            child = subprocess.Popen(adapter.arguments(endpoint, known) + ["-M", "-S", str(control), "-o", "ControlPersist=no", "-N", "-L", f"127.0.0.1:{port}:127.0.0.1:{endpoint['remote_port']}", endpoint["user"] + "@" + endpoint["host"]], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, env=adapter._env(), close_fds=True)
            record = {"pid": os.getpid(), "birth": _birth(os.getpid()), "child_pid": child.pid, "child_birth": _birth(child.pid), "ready": False}
            _write(state.parent / "process.json", record)
            stopping = False
            def stop(signum, frame):
                nonlocal stopping
                stopping = True
                if record["child_birth"] and _birth(child.pid) == record["child_birth"]:
                    child.terminate()
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            try:
                deadline = time.monotonic() + 12
                while child.poll() is None and not stopping and time.monotonic() < deadline:
                    if control.exists() and not control.is_symlink() and control.stat().st_uid == os.getuid():
                        check = subprocess.run(adapter.arguments(endpoint, known) + ["-S", str(control), "-O", "check", endpoint["user"] + "@" + endpoint["host"]], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=adapter._env(), timeout=2, check=False)
                        if check.returncode == 0 and record["child_birth"] and _birth(child.pid) == record["child_birth"]:
                            record["ready"] = True
                            _write(state.parent / "process.json", record)
                            break
                    time.sleep(0.1)
                if not record["ready"]:
                    stop(signal.SIGTERM, None)
                while child.poll() is None and not stopping:
                    time.sleep(0.2)
                if child.poll() is None:
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        if record["child_birth"] and _birth(child.pid) == record["child_birth"]:
                            child.kill()
                child.wait()
            finally:
                if record["child_birth"] and _birth(child.pid) == record["child_birth"]:
                    child.terminate()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--tunnel-state":
        try:
            _supervise(Path(sys.argv[2]))
        except (RemoteError, OSError, ValueError, KeyError):
            sys.exit(1)
    else:
        sys.exit(2)
