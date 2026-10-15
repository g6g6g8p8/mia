"""Vercel Hobby distribution frontend; personal Mia installations are separate.

Invitation state is durable Upstash Redis. Large initial DMGs use one-object
private Blob leases, and never cross a Vercel Function's response-size limit.
No infrastructure credential or permanent public download URL reaches clients.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import time
import urllib.parse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
import httpx

from mia.demo_distribution import DistributionError
from mia.release_publication import ARCHITECTURES, PublicationError, _private_directory, _regular, _verified_publication, _write_new, canonical, digest, read_json
from mia.vercel_distribution import BlobPrivateDownloads, UpstashInvitationStore, VercelDistributionUnavailable

VERCEL_ENVIRONMENT_NAMES = ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "BLOB_READ_WRITE_TOKEN", "BLOB_STORE_ID")
MAX_CONFIG = 256 * 1024
MAX_METADATA = 16384


def _release_config(config: dict) -> dict:
    if not isinstance(config, dict) or config.get("protocol") != 1 or config.get("hosting") != "vercel" or config.get("download_policy") != "private-blob-one-object-60s-leases":
        raise PublicationError("Configuração Vercel da publicação inválida")
    from mia.updates import UpdateError, _https
    try:
        origin = _https(config["origin"]).rstrip("/")
    except (ValueError, KeyError, UpdateError):
        raise PublicationError("Publicação Vercel precisa de origem HTTPS revisada") from None
    if urllib.parse.urlsplit(origin).path:
        raise PublicationError("Origem Vercel não aceita caminho")
    releases = config.get("releases")
    if not isinstance(releases, list) or not 1 <= len(releases) <= 20:
        raise PublicationError("Publicação precisa de releases imutáveis limitados")
    seen = set()
    for release in releases:
        if not isinstance(release, dict) or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", str(release.get("release_id", ""))) or release["release_id"] in seen or not release.get("artifacts") or not set(release.get("artifacts", {})).issubset(ARCHITECTURES):
            raise PublicationError("Release Vercel inválido")
        seen.add(release["release_id"])
        for arch, artifact in release["artifacts"].items():
            if not isinstance(artifact, dict) or artifact.get("pathname") != release["release_id"] + "/Mia-" + arch + ".dmg" or not re.fullmatch(r"[a-f0-9]{64}", str(artifact.get("sha256", ""))) or isinstance(artifact.get("size"), bool) or not isinstance(artifact.get("size"), int) or not 1 <= artifact["size"] <= 2 * 1024**3:
                raise PublicationError("DMG privado não corresponde à arquitetura/path/hash revisados")
    if config.get("current_release_id") not in seen or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,59}", str(config.get("invitation_namespace", ""))):
        raise PublicationError("Versão atual ou namespace de convites inválido")
    current = next(release for release in releases if release["release_id"] == config["current_release_id"])
    if set(config.get("appcasts", {})) != set(current["artifacts"]):
        raise PublicationError("Appcast privado precisa corresponder às arquiteturas oferecidas")
    for architecture, entry in config["appcasts"].items():
        if not isinstance(entry, dict) or entry.get("filename") != architecture + ".xml" or not re.fullmatch(r"[a-f0-9]{64}", str(entry.get("sha256", ""))) or isinstance(entry.get("size"), bool) or not isinstance(entry.get("size"), int) or not 1 <= entry["size"] <= MAX_CONFIG:
            raise PublicationError("Appcast privado não corresponde ao inventário revisado")
    return {**config, "origin": origin}


def create_vercel_distribution_app(config: dict, *, environment: dict | None = None, feed_root: Path | None = None, store=None, downloads=None) -> FastAPI:
    config = _release_config(config)
    environment = os.environ if environment is None else environment
    store = store or UpstashInvitationStore(environment.get("UPSTASH_REDIS_REST_URL"), environment.get("UPSTASH_REDIS_REST_TOKEN"), namespace=config["invitation_namespace"])
    downloads = downloads or BlobPrivateDownloads(environment.get("BLOB_READ_WRITE_TOKEN"), environment.get("BLOB_STORE_ID"))
    releases = {release["release_id"]: release for release in config["releases"]}
    current = releases[config["current_release_id"]]
    feed_root = Path(feed_root) if feed_root is not None else Path(__file__).resolve().parents[1] / "update-feeds"
    feeds = {}
    for architecture, entry in config["appcasts"].items():
        path = _regular(feed_root / entry["filename"], maximum=MAX_CONFIG)
        if path.stat().st_size != entry["size"] or digest(path) != entry["sha256"]:
            raise PublicationError("Appcast privado mudou; publicação pausada")
        feeds[architecture] = path
    app = FastAPI(title="Mia · Demonstração", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        if request.url.query:
            return JSONResponse({"detail": "Parâmetros de URL não são aceitos"}, status_code=400)
        origin = request.headers.get("Origin")
        if origin is not None and origin != config["origin"] and request.method != "GET":
            return JSONResponse({"detail": "Origem não autorizada"}, status_code=403)
        request.state.csp_nonce = secrets.token_urlsafe(16)
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'none'; script-src 'nonce-" + request.state.csp_nonce + "'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"})
        return response

    @app.get("/health")
    def health():
        return {"ok": True, "service": "mia-demo-distribution", "hosting": "vercel", "release_id": current["release_id"]}

    def landing_html(request: Request, release: dict) -> HTMLResponse:
        # Blob handles the large download directly. A client-held request secret
        # is saved before POST, so cold starts and lost responses are repeatable.
        script = '''const releaseId=RELEASE_ID;
const invitation=location.hash.slice(1);if(location.hash)history.replaceState(null,'',location.pathname);
if(/^mia_invite_[A-Za-z0-9_-]{43}$/.test(invitation))document.getElementById('invite').value=invitation;
const state=document.getElementById('state'),button=document.getElementById('download'),choice=document.getElementById('architecture');
const storedKey='mia-demo-vercel-'+releaseId;let saved={};try{saved=JSON.parse(sessionStorage.getItem(storedKey)||'{}')}catch(_){}
if(saved.architecture)choice.value=saved.architecture;
const activation=document.getElementById('open-mia');if(saved.activation_ticket)activation.href='mia-demo://activate?ticket='+saved.activation_ticket;
button.onclick=async()=>{button.disabled=true;try{
if(!saved.download_token){if(!saved.request_id){const bytes=crypto.getRandomValues(new Uint8Array(32));saved.request_id=btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');saved.architecture=choice.value;sessionStorage.setItem(storedKey,JSON.stringify(saved));}
if(saved.architecture!==choice.value)throw new Error('O pedido anterior escolheu outro Mac. Retome essa opção ou peça um novo convite.');
const response=await fetch('/redeem',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:document.getElementById('invite').value.trim(),request_id:saved.request_id,architecture:saved.architecture,release_id:releaseId})});
if(!response.ok)throw new Error(response.status===503?'Distribuição indisponível. Tente novamente.':'Convite inválido, expirado, revogado ou já utilizado.');
saved={...saved,...await response.json()};sessionStorage.setItem(storedKey,JSON.stringify(saved));document.getElementById('invite').value='';if(saved.activation_ticket)activation.href='mia-demo://activate?ticket='+saved.activation_ticket;}
choice.disabled=true;const response=await fetch('/download/'+releaseId+'/'+saved.architecture,{headers:{Authorization:'Bearer '+saved.download_token}});
if(!response.ok)throw new Error(response.status===503?'Download indisponível. Tente novamente.':'Sessão inválida, expirada ou revogada. Peça um novo convite.');
const lease=await response.json(),link=document.createElement('a');link.href=lease.download_url;link.rel='noreferrer';link.download='Mia.dmg';link.click();
state.textContent='O download começa diretamente do armazenamento privado. Abra a Mia e escolha seu Mac ou servidor. Se interromper, tente novamente nesta janela.';
}catch(error){state.textContent=error.message}finally{button.disabled=false}};'''.replace("RELEASE_ID", json.dumps(release["release_id"]))
        choices = ''.join('<option value="' + arch + '">' + ('Chip Apple (M1 ou posterior)' if arch == 'arm64' else 'Processador Intel') + '</option>' for arch in ARCHITECTURES if arch in release["artifacts"])
        body = '<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mia · Seu convite</title><main><h1>Seu contexto, na sua Mia</h1><p>Abra a Mia e escolha seu Mac ou seu servidor. Seu Vault e suas conversas ficam na instalação escolhida.</p><label>Convite <input id="invite" autocomplete="off" type="password"></label><p><label>Seu Mac <select id="architecture">' + choices + '</select></label></p><p>Veja o chip em  → Sobre Este Mac. A Mia exige macOS 13 ou posterior.</p><button id="download">Baixar Mia</button><p id="state" role="status"></p><p>Depois de instalar, <a id="open-mia">abrir a Mia com meu convite</a>. Essa ativação libera as atualizações oficiais; sua biblioteca continua funcionando sem este portal.</p><p>O convite autoriza uma sessão de download por até 24 horas. Cada link privado dura até 60 segundos; revogar impede novos links. Uma transferência já iniciada pode terminar.</p></main><script nonce="' + html.escape(request.state.csp_nonce) + '">' + script + '</script></html>'
        return HTMLResponse(body)

    @app.get("/", response_class=HTMLResponse)
    @app.get("/invite", response_class=HTMLResponse)
    def landing(request: Request):
        return landing_html(request, current)

    @app.get("/invite/{release_id}", response_class=HTMLResponse)
    def historical_landing(release_id: str, request: Request):
        if release_id not in releases:
            raise HTTPException(404, "Versão de demonstração não encontrada")
        return landing_html(request, releases[release_id])

    @app.post("/redeem")
    async def redeem(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                raise HTTPException(413, "Pedido excedeu o limite")
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict) or set(payload) != {"token", "request_id", "architecture", "release_id"} or any(not isinstance(value, str) or len(value) > 120 for value in payload.values()):
                raise ValueError
            artifact = releases[payload["release_id"]]["artifacts"][payload["architecture"]]
        except (ValueError, UnicodeError, RecursionError, KeyError, TypeError):
            raise HTTPException(400, "Pedido de resgate inválido") from None
        try:
            receipt = store.redeem(payload["token"], artifact["sha256"], request_id=payload["request_id"], architecture=payload["architecture"])
            return {**receipt, "architecture": payload["architecture"], "release_id": payload["release_id"], "sha256": artifact["sha256"], "size": artifact["size"]}
        except VercelDistributionUnavailable:
            raise HTTPException(503, "Registro de convites indisponível; tente novamente") from None
        except DistributionError:
            raise HTTPException(410, "Convite inválido, expirado, revogado ou já utilizado") from None

    @app.get("/download/{release_id}/{architecture}")
    def download(release_id: str, architecture: str, request: Request):
        try:
            artifact = releases[release_id]["artifacts"][architecture]
        except KeyError:
            raise HTTPException(404, "Versão de demonstração não encontrada") from None
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer ") or len(authorization) > 120:
            raise HTTPException(401, "Sessão de download necessária")
        try:
            session = store.authorize(authorization[7:], artifact["sha256"])
            lease = downloads.download_url(artifact["pathname"], session_expires_at=session["expires_at"])
            return {"download_url": lease["url"], "expires_at": lease["expires_at"], "sha256": artifact["sha256"], "size": artifact["size"], "max_lease_seconds": 60}
        except VercelDistributionUnavailable:
            raise HTTPException(503, "Download indisponível; tente novamente") from None
        except DistributionError:
            raise HTTPException(401, "Sessão inválida, expirada ou revogada") from None

    @app.post("/beta/activate")
    async def activate(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                raise HTTPException(413, "Pedido excedeu o limite")
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict) or set(payload) != {"ticket", "client_nonce", "architecture"} or any(not isinstance(value, str) or len(value) > 100 for value in payload.values()) or payload["architecture"] not in current["artifacts"]:
                raise ValueError
        except (ValueError, UnicodeError, RecursionError, KeyError, TypeError):
            raise HTTPException(400, "Pedido de ativação inválido") from None
        try:
            return store.activate(payload["ticket"], payload["client_nonce"], payload["architecture"])
        except VercelDistributionUnavailable:
            raise HTTPException(503, "Ativação indisponível; tente novamente") from None
        except DistributionError:
            raise HTTPException(410, "Convite de ativação inválido, expirado, revogado ou já utilizado") from None

    def beta_session(request: Request, architecture: str):
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer ") or len(authorization) > 100:
            raise HTTPException(401, "Ativação beta necessária para atualizações oficiais")
        try:
            return store.authorize_beta(authorization[7:], architecture)
        except VercelDistributionUnavailable:
            raise HTTPException(503, "Autorização beta indisponível; tente novamente") from None
        except DistributionError:
            raise HTTPException(401, "Acesso beta inválido, expirado ou revogado") from None

    @app.get("/updates/{architecture}/appcast.xml")
    def appcast(architecture: str, request: Request):
        if architecture not in feeds:
            raise HTTPException(404, "Arquitetura não oferecida nesta demonstração")
        beta_session(request, architecture)
        try:
            path = _regular(feeds[architecture], maximum=MAX_CONFIG)
            content = path.read_bytes()
        except PublicationError:
            raise HTTPException(503, "Appcast privado mudou; publicação pausada") from None
        if hashlib.sha256(content).hexdigest() != config["appcasts"][architecture]["sha256"]:
            raise HTTPException(503, "Appcast privado mudou; publicação pausada")
        return Response(content, media_type="application/rss+xml")

    @app.get("/app-updates/{release_id}/{architecture}")
    def app_update(release_id: str, architecture: str, request: Request):
        try:
            artifact = releases[release_id]["artifacts"][architecture]
        except KeyError:
            raise HTTPException(404, "Atualização oficial não encontrada") from None
        session = beta_session(request, architecture)
        try:
            lease = downloads.download_url(artifact["pathname"], session_expires_at=session["expires_at"])
        except VercelDistributionUnavailable:
            raise HTTPException(503, "Download indisponível; tente novamente") from None
        return RedirectResponse(lease["url"], status_code=302)
    return app


def unconfigured_vercel_app() -> FastAPI:
    """A deployable preparation cannot falsely advertise a beta release."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    @app.get("/{path:path}")
    def pending(path: str):
        return JSONResponse({"ok": False, "ready_for_beta": False, "detail": "Distribuição ainda não liberada. Assinatura, aceites e recursos de publicação permanecem pendentes."}, status_code=503, headers={"Cache-Control": "no-store"})
    return app


class BlobArtifactUploader:
    """Operator-side streaming upload, no overwrite, followed by byte verification."""
    def __init__(self, *, token: str, store_id: str, access: str, client=None):
        from mia.vercel_distribution import _secret
        if not isinstance(store_id, str) or not re.fullmatch(r"[A-Za-z0-9]{8,64}", store_id) or access not in ("private", "public"):
            raise PublicationError("Store Blob precisa de ID explícito e acesso revisado")
        self.token, self.store_id, self.access = _secret(token), store_id, access
        self.client = client or httpx.Client(follow_redirects=False, timeout=httpx.Timeout(120, connect=15))

    def upload(self, path: Path, pathname: str, *, sha256: str) -> dict:
        path = _regular(path)
        if not re.fullmatch(r"[A-Za-z0-9._/-]{1,200}", pathname) or any(part in ("", ".", "..") for part in pathname.split("/")) or not re.fullmatch(r"[a-f0-9]{64}", sha256) or digest(path) != sha256:
            raise PublicationError("Upload exige caminho público limitado e hash exato revisado")
        headers = {"Authorization": "Bearer " + self.token, "x-api-version": "13", "x-vercel-blob-store-id": self.store_id, "x-vercel-blob-access": self.access, "x-add-random-suffix": "0", "x-allow-overwrite": "0", "x-content-type": "application/octet-stream", "Content-Length": str(path.stat().st_size)}
        url = "https://vercel.com/api/blob/?" + urllib.parse.urlencode({"pathname": pathname})
        expected_url = "https://" + self.store_id.lower() + "." + self.access + ".blob.vercel-storage.com/" + pathname
        try:
            read_headers = {"Accept-Encoding": "identity"}
            if self.access == "private":
                read_headers["Authorization"] = "Bearer " + self.token
            existing = self.client.head(expected_url, headers=read_headers)
            if existing.status_code == 404:
                with path.open("rb") as source:
                    response = self.client.put(url, headers=headers, content=iter(lambda: source.read(256 * 1024), b""))
                if response.status_code not in (200, 201) or len(response.content) > MAX_METADATA:
                    raise ValueError
                metadata = response.json()
                if metadata.get("url") != expected_url or metadata.get("pathname") != pathname:
                    raise ValueError
            elif existing.status_code != 200:
                raise ValueError
            # A retry may adopt only an already present object with exactly the
            # reviewed hash/size. It never overwrites a mismatching Blob object.
            total, observed = 0, hashlib.sha256()
            with self.client.stream("GET", expected_url, headers=read_headers) as downloaded:
                if downloaded.status_code != 200 or downloaded.headers.get("Content-Encoding", "identity") != "identity":
                    raise ValueError
                for chunk in downloaded.iter_bytes(256 * 1024):
                    total += len(chunk)
                    if total > path.stat().st_size:
                        raise ValueError
                    observed.update(chunk)
            if total != path.stat().st_size or observed.hexdigest() != sha256:
                raise ValueError
        except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError):
            raise PublicationError("Upload Blob não foi confirmado byte a byte; a publicação permanece pausada") from None
        return {"protocol": 1, "access": self.access, "store_id": self.store_id, "pathname": pathname, "url": expected_url, "sha256": sha256, "size": total, "verified_at": int(time.time()), "byte_verification": True}


def vercel_deployment_plan(*, domain: str, project_name: str, private_store_id: str | None = None, public_store_id: str | None = None, publication: dict | None = None) -> dict:
    from mia.updates import _https
    if not isinstance(domain, str) or not re.fullmatch(r"(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}", domain) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,80}", project_name):
        raise PublicationError("Domínio estável ou nome do projeto Vercel inválido")
    for store in (private_store_id, public_store_id):
        if store is not None and not re.fullmatch(r"[A-Za-z0-9]{8,64}", store):
            raise PublicationError("Identificador público Blob inválido")
    if private_store_id is not None and private_store_id == public_store_id:
        raise PublicationError("DMGs privados e updates públicos exigem stores de acessos distintos")
    plan = {"protocol": 1, "hosting": "vercel", "plan": "Hobby", "project_name": project_name, "domain": domain, "origin": _https("https://" + domain),
        "private_blob_store_id": private_store_id, "public_blob_store_id": public_store_id, "release_id": publication.get("release_id") if publication else None,
        "publication_sha256": hashlib.sha256(canonical(publication)).hexdigest() if publication else None,
        "environment_variable_names": list(VERCEL_ENVIRONMENT_NAMES), "durable_invitation_metadata": "Upstash Redis REST, one atomic Lua operation",
        "large_downloads": "private Blob read-only exact-object lease at most 60s; no function proxy",
        "official_app_updates": "private appcast + beta entitlement + private Blob lease", "backend_source_updates": "public Blob open-source ZIP + signed public backend feed",
        "external_gates": ["Apple signed/notarized accepted release", "stable production Vercel URL chosen before signing channels", "Hobby eligibility and current quotas confirmed in account", "private and public Blob stores provisioned", "free Upstash integration provisioned", "environment variables linked securely in production scope", "byte-verified Blob uploads", "reviewed deployment approved", "actual HTTPS invite/download/update acceptance"],
        "deployed": False, "invitations_sent": 0, "personal_installations_modified": False}
    return {**plan, "approve_sha256": hashlib.sha256(canonical(plan)).hexdigest()}


def write_vercel_kit(plan: dict, directory: Path, *, source: Path, publisher_state: Path | None = None, uploads: list[dict] | None = None) -> dict:
    """Prepare a concrete Vercel project; incomplete projects serve 503 only.

    Production packaging refuses manifests not backed by byte-verified upload
    receipts. It embeds public deployment metadata, never credentials or DMGs.
    """
    from scripts.package_macos import copy_public_source
    expected = hashlib.sha256(canonical({key: value for key, value in plan.items() if key != "approve_sha256"})).hexdigest()
    if plan.get("approve_sha256") != expected:
        raise PublicationError("Plano Vercel mudou depois da revisão")
    directory = Path(directory).absolute()
    if directory.exists() or directory.is_symlink() or any(part.is_symlink() for part in directory.parents):
        raise PublicationError("Kit Vercel exige pasta nova; conteúdo anterior preservado")
    config, rewrites = None, []
    public_files = {}
    if publisher_state is not None:
        state = _private_directory(publisher_state)
        manifest = read_json(state / "current.json", private=True)
        root, _ = _verified_publication(state, manifest)
        if plan["publication_sha256"] != hashlib.sha256(canonical(manifest)).hexdigest() or plan["origin"] != manifest["origin"]:
            raise PublicationError("Publicação não corresponde ao plano Vercel revisado")
        if not uploads or any(not isinstance(item, dict) or item.get("byte_verification") is not True for item in uploads):
            raise PublicationError("Kit publicado exige uploads Blob conferidos byte a byte")
        if len({(item.get("access"), item.get("pathname")) for item in uploads}) != len(uploads):
            raise PublicationError("Inventário de uploads contém objetos duplicados")
        artifacts = {}
        appcasts = {}
        offered = {artifact["architecture"] for artifact in manifest["artifacts"]}
        for architecture in sorted(offered):
            name = "Mia-" + architecture + ".dmg"
            pathname = manifest["release_id"] + "/" + name
            matches = [item for item in uploads if item.get("access") == "private" and item.get("pathname") == pathname and item.get("store_id") == plan["private_blob_store_id"]]
            if len(matches) != 1 or matches[0]["sha256"] != manifest["files"][name]["sha256"] or matches[0]["size"] != manifest["files"][name]["size"]:
                raise PublicationError("DMG privado não corresponde aos bytes aprovados no plano")
            artifacts[architecture] = {"pathname": pathname, "sha256": matches[0]["sha256"], "size": matches[0]["size"]}
        for route, name in manifest["routes"].items():
            if route.endswith("/appcast.xml"):
                architecture = route.split("/")[2]
                entry_name = "update-feeds/" + architecture + ".xml"
                public_files[entry_name] = (root / name).read_bytes()
                appcasts[architecture] = {"filename": architecture + ".xml", "sha256": manifest["files"][name]["sha256"], "size": manifest["files"][name]["size"]}
            elif route.startswith("/updates/"):
                public_files["public" + route] = (root / name).read_bytes()
            elif name.endswith(".zip"):
                pathname = manifest["release_id"] + "/" + name
                matches = [item for item in uploads if item.get("access") == "public" and item.get("pathname") == pathname and item.get("store_id") == plan["public_blob_store_id"]]
                if len(matches) != 1 or matches[0]["sha256"] != manifest["files"][name]["sha256"] or matches[0]["size"] != manifest["files"][name]["size"]:
                    raise PublicationError("Atualização pública não possui upload autenticado de bytes exatos")
                expected_url = "https://" + plan["public_blob_store_id"].lower() + ".public.blob.vercel-storage.com/" + pathname
                if matches[0]["url"] != expected_url:
                    raise PublicationError("Endereço de atualização difere do store Blob revisado")
                rewrites.append({"src": re.escape(route), "dest": expected_url})
        historical = []
        for release_path in sorted((state / "releases").iterdir()):
            previous = read_json(release_path / "publication.json", private=True)
            _verified_publication(state, previous)
            # Existing signed backend feeds can still be valid when a new
            # release becomes current. Keep their immutable source ZIP routes
            # reachable until the operator explicitly retires that release.
            for route, name in previous["routes"].items():
                if not name.endswith(".zip"):
                    continue
                pathname = previous["release_id"] + "/" + name
                matches = [item for item in uploads if item.get("access") == "public" and item.get("pathname") == pathname and item.get("store_id") == plan["public_blob_store_id"]]
                expected_url = "https://" + plan["public_blob_store_id"].lower() + ".public.blob.vercel-storage.com/" + pathname
                if len(matches) != 1 or matches[0].get("sha256") != previous["files"][name]["sha256"] or matches[0].get("size") != previous["files"][name]["size"] or matches[0].get("url") != expected_url:
                    raise PublicationError("Pacotes-fonte anteriores precisam conservar os uploads revisados")
                rewrite = {"src": re.escape(route), "dest": expected_url}
                if rewrite not in rewrites:
                    rewrites.append(rewrite)
            previous_artifacts = {}
            for artifact in previous["artifacts"]:
                architecture = artifact["architecture"]
                name = "Mia-" + architecture + ".dmg"
                pathname = previous["release_id"] + "/" + name
                matches = [item for item in uploads if item.get("access") == "private" and item.get("pathname") == pathname and item.get("store_id") == plan["private_blob_store_id"]]
                if len(matches) != 1 or matches[0]["sha256"] != previous["files"][name]["sha256"] or matches[0]["size"] != previous["files"][name]["size"]:
                    raise PublicationError("Downloads privados anteriores precisam conservar uploads/hash para sessões retomáveis")
                previous_artifacts[architecture] = {"pathname": pathname, "sha256": matches[0]["sha256"], "size": matches[0]["size"]}
            historical.append({"release_id": previous["release_id"], "version": previous["version"], "artifacts": previous_artifacts})
        config = _release_config({"protocol": 1, "hosting": "vercel", "origin": manifest["origin"], "download_policy": "private-blob-one-object-60s-leases", "invitation_namespace": "mia-demo-beta", "current_release_id": manifest["release_id"], "appcasts": appcasts, "releases": historical})
    directory.mkdir(parents=True, mode=0o700)
    copied = directory / "source-public"
    copy_public_source(source, copied)
    shutil.move(copied / "mia", directory / "mia")
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        if (copied / name).is_file():
            shutil.move(copied / name, directory / name)
    if (copied / "THIRD_PARTY_LICENSES").is_dir():
        shutil.move(copied / "THIRD_PARTY_LICENSES", directory / "THIRD_PARTY_LICENSES")
    requirements = (copied / "requirements.lock").read_bytes()
    shutil.rmtree(copied)
    _write_new(directory / "requirements.txt", requirements)
    _write_new(directory / ".python-version", b"3.12\n")
    _write_new(directory / ".vercelignore", b".env*\n*.pem\n*.key\n*.dmg\n*.zip\n.git\ndata\nbackups\nlogs\n.venv\n")
    api = directory / "api"
    api.mkdir(mode=0o700)
    entry = '''from pathlib import Path
import json
from mia.vercel_release import create_vercel_distribution_app, unconfigured_vercel_app
config_path = Path(__file__).resolve().parents[1] / "distribution-release.json"
app = create_vercel_distribution_app(json.loads(config_path.read_text()), feed_root=config_path.parent / "update-feeds") if config_path.exists() else unconfigured_vercel_app()
'''
    _write_new(api / "index.py", entry.encode())
    if config:
        _write_new(directory / "distribution-release.json", canonical(config) + b"\n")
    for name, content in public_files.items():
        target = directory / name
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        _write_new(target, content)
    # Explicitly route bundled configuration/private appcasts through the app
    # before filesystem handling. They must remain private even if deployment
    # output detection changes; none is an authenticated public file endpoint.
    private_route = {"src": r"/(?:update-feeds(?:/.*)?|distribution-release\.json|deployment-plan\.json|mia(?:/.*)?|\.env[^/]*)", "dest": "/api/index.py"}
    feed_cache = {"src": r"/updates/[^/]+/backend\.json", "headers": {"Cache-Control": "no-cache"}, "continue": True}
    vercel = {"version": 2, "functions": {"api/index.py": {"maxDuration": 30, "includeFiles": "{mia/**,distribution-release.json,update-feeds/**}"}},
              "routes": [feed_cache, *rewrites, private_route, {"handle": "filesystem"}, {"src": "/(.*)", "dest": "/api/index.py"}]}
    _write_new(directory / "vercel.json", canonical(vercel) + b"\n")
    _write_new(directory / "deployment-plan.json", canonical(plan) + b"\n")
    return {"directory": str(directory), "plan_sha256": expected, "ready_for_deployment": config is not None, "unconfigured_returns": None if config else 503,
            "deployed": False, "invitations_sent": 0, "large_artifacts_embedded": False, "secrets_embedded": False}
