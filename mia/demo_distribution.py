"""Invitation-gated official binaries, isolated from personal Mia installations.

The public service never creates invitations and has no access to a Mia library.
Only token hashes are persisted. Redeeming creates a short-lived download session,
so an interrupted HTTP download can resume without redeeming an invitation twice.
"""
from __future__ import annotations

import contextlib
import base64
import hashlib
import html
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
from typing import Iterator

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

MAX_ARTIFACT = 2 * 1024**3
MAX_INVITATION_TTL = 30 * 86400
DOWNLOAD_TTL = 24 * 3600


class DistributionError(ValueError):
    pass


class _ClosingStream(StreamingResponse):
    def __init__(self, content, *, close, **kwargs):
        super().__init__(content, **kwargs)
        self.close_file = close

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Starlette's background callbacks run only after a successful
            # response call. Header-send failures must also release the file.
            self.close_file()


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _private_directory(directory: Path) -> Path:
    directory = Path(directory).absolute()
    for ancestor in (directory, *directory.parents):
        if ancestor.is_symlink():
            raise DistributionError("Diretório privado não aceita links simbólicos")
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = directory.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise DistributionError("Diretório de distribuição precisa pertencer ao usuário e ter permissão 0700")
    return directory


class InvitationStore:
    def __init__(self, directory: Path):
        self.directory = _private_directory(directory)
        self.path = self.directory / "invitations.sqlite3"
        if self.path.is_symlink():
            raise DistributionError("Banco de convites não aceita link simbólico")
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.close(fd)
        if self.path.stat().st_uid != os.getuid() or self.path.stat().st_mode & 0o077:
            raise DistributionError("Banco de convites precisa ser privado")
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS invitations (
                    id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL,
                    created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
                    redeemed_at INTEGER, revoked_at INTEGER, redemption_request_hash TEXT
                );
                CREATE TABLE IF NOT EXISTS download_sessions (
                    token_hash TEXT PRIMARY KEY, invitation_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
                    artifact_sha256 TEXT NOT NULL,
                    FOREIGN KEY(invitation_id) REFERENCES invitations(id)
                );
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(invitations)")}
            if "redemption_request_hash" not in columns:
                db.execute("ALTER TABLE invitations ADD COLUMN redemption_request_hash TEXT")

    @contextlib.contextmanager
    def connect(self):
        # Closing is separate from SQLite's transaction context manager.
        with contextlib.closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.row_factory = sqlite3.Row
            with db:
                yield db

    def issue(self, *, ttl: int = 7 * 86400, now: int | None = None) -> dict:
        if isinstance(ttl, bool) or not 60 <= ttl <= MAX_INVITATION_TTL:
            raise DistributionError("Prazo do convite deve ficar entre um minuto e trinta dias")
        now = int(time.time()) if now is None else now
        token, identity = "mia_invite_" + secrets.token_urlsafe(32), secrets.token_hex(16)
        with self.connect() as db:
            db.execute("INSERT INTO invitations(id,token_hash,created_at,expires_at) VALUES(?,?,?,?)",
                       (identity, _digest(token), now, now + ttl))
        return {"id": identity, "token": token, "expires_at": now + ttl}

    def revoke(self, invitation_id: str, *, now: int | None = None) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", invitation_id):
            raise DistributionError("Identificador de convite inválido")
        with self.connect() as db:
            db.execute("UPDATE invitations SET revoked_at=? WHERE id=?", (int(time.time()) if now is None else now, invitation_id))

    def redeem(self, token: str, artifact_sha256: str, *, request_id: str | None = None, now: int | None = None) -> dict:
        if not re.fullmatch(r"mia_invite_[A-Za-z0-9_-]{43}", token):
            raise DistributionError("Convite inválido, expirado ou já utilizado")
        if not re.fullmatch(r"[a-f0-9]{64}", artifact_sha256):
            raise DistributionError("Artefato não identificado")
        if request_id is not None and not re.fullmatch(r"[A-Za-z0-9_-]{43}", request_id):
            raise DistributionError("Identificador de resgate inválido")
        now = int(time.time()) if now is None else now
        # A client-held 256-bit request secret makes an acknowledged/lost POST
        # replay idempotent while a different redeemer cannot create a session.
        # No plaintext invitation, request secret or session enters the database.
        session_secret = base64.urlsafe_b64encode(hashlib.sha256(b"Mia download v1\0" + token.encode() + b"\0" + request_id.encode()).digest()).rstrip(b"=").decode() if request_id else secrets.token_urlsafe(32)
        session = "mia_download_" + session_secret
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            invite = db.execute("SELECT * FROM invitations WHERE token_hash=?", (_digest(token),)).fetchone()
            if not invite or invite["revoked_at"] is not None:
                raise DistributionError("Convite inválido, expirado ou já utilizado")
            if invite["redeemed_at"] is not None:
                if request_id is None or invite["redemption_request_hash"] != _digest(request_id):
                    raise DistributionError("Convite inválido, expirado ou já utilizado")
                previous = db.execute("SELECT * FROM download_sessions WHERE token_hash=? AND invitation_id=?", (_digest(session), invite["id"])).fetchone()
                if not previous or previous["expires_at"] <= now or previous["artifact_sha256"] != artifact_sha256:
                    raise DistributionError("Sessão de download inválida ou expirada")
                return {"download_token": session, "expires_at": previous["expires_at"]}
            if invite["expires_at"] <= now:
                raise DistributionError("Convite inválido, expirado ou já utilizado")
            db.execute("UPDATE invitations SET redeemed_at=?,redemption_request_hash=? WHERE id=?", (now, _digest(request_id) if request_id else None, invite["id"]))
            db.execute("INSERT INTO download_sessions VALUES(?,?,?,?,?)",
                       (_digest(session), invite["id"], now, now + DOWNLOAD_TTL, artifact_sha256))
        return {"download_token": session, "expires_at": now + DOWNLOAD_TTL}

    def authorize(self, token: str, artifact_sha256: str, *, now: int | None = None) -> None:
        if not re.fullmatch(r"mia_download_[A-Za-z0-9_-]{43}", token):
            raise DistributionError("Sessão de download inválida ou expirada")
        now = int(time.time()) if now is None else now
        with self.connect() as db:
            session = db.execute("""SELECT s.expires_at,s.artifact_sha256,i.revoked_at
                FROM download_sessions s JOIN invitations i ON i.id=s.invitation_id
                WHERE s.token_hash=?""", (_digest(token),)).fetchone()
            if not session or session["expires_at"] <= now or session["revoked_at"] is not None or session["artifact_sha256"] != artifact_sha256:
                raise DistributionError("Sessão de download inválida ou expirada")

    def list_invitations(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT id,created_at,expires_at,redeemed_at,revoked_at FROM invitations ORDER BY created_at DESC LIMIT 1000")]


def _range(value: str | None, size: int) -> tuple[int, int, bool]:
    if value is None:
        return 0, size - 1, False
    matched = re.fullmatch(r"bytes=(\d{1,12})-(\d{0,12})", value)
    if not matched:
        raise HTTPException(416, "Intervalo de download inválido", headers={"Content-Range": f"bytes */{size}"})
    start = int(matched[1])
    end = min(int(matched[2]) if matched[2] else size - 1, size - 1)
    if start >= size or end < start:
        raise HTTPException(416, "Intervalo de download inválido", headers={"Content-Range": f"bytes */{size}"})
    return start, end, True


def create_distribution_app(directory: Path, artifact: Path, *, sha256: str) -> FastAPI:
    store = InvitationStore(directory)
    artifact = Path(artifact).absolute()
    if artifact.is_symlink() or any(p.is_symlink() for p in artifact.parents):
        raise DistributionError("Artefato não aceita links simbólicos")
    if not re.fullmatch(r"[a-f0-9]{64}", sha256) or not artifact.is_file():
        raise DistributionError("Artefato/hash inválido")
    info = artifact.stat()
    if not 1 <= info.st_size <= MAX_ARTIFACT or info.st_mode & 0o022:
        raise DistributionError("Artefato supera o limite de distribuição")
    with artifact.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != sha256:
            raise DistributionError("Artefato difere do hash revisado")
    identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    # Fixed safe download name; filesystem names never become response headers.
    filename = "Mia-Demo.dmg" if artifact.suffix.lower() == ".dmg" else "Mia-Demo.zip"
    app = FastAPI(title="Distribuição Mia Demo", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.invitation_store = store

    @app.middleware("http")
    async def private_response(request: Request, call_next):
        # Never accept secrets in a URL; default access logs contain URL paths.
        if request.url.query:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Parâmetros de URL não são aceitos"}, status_code=400)
        request.state.csp_nonce = secrets.token_urlsafe(16)
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'none'; script-src 'nonce-" + request.state.csp_nonce + "'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"})
        return response

    @app.get("/", response_class=HTMLResponse)
    @app.get("/invite", response_class=HTMLResponse)
    def landing(request: Request):
        return """<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Mia Demo</title>
        <main><h1>Seu convite para a Mia</h1><p>Seu contexto fica na sua instalação. Este serviço libera apenas o download.</p>
        <label>Convite <input id="code" autocomplete="off" type="password"></label>
        <button id="download">Baixar Mia</button><p id="state" role="status"></p></main><script nonce="SCRIPT_NONCE">
        const invitation=location.hash.slice(1);
        if (/^mia_invite_[A-Za-z0-9_-]{43}$/.test(invitation)) document.getElementById('code').value=invitation;
        if (location.hash) history.replaceState(null,'',location.pathname);
        let session = null, requestId = null;
        try { const previous=JSON.parse(sessionStorage.getItem('mia-demo-download')||'null');
          if (previous && previous.expires_at*1000>Date.now()) session=previous.download_token;
          requestId=sessionStorage.getItem('mia-demo-request'); } catch (_) {}
        document.getElementById('download').onclick = async () => {
          const state = document.getElementById('state');
          const button = document.getElementById('download'); button.disabled = true;
          try {
            if (!session) {
              if (!requestId) { const random=crypto.getRandomValues(new Uint8Array(32));
                requestId=btoa(String.fromCharCode(...random)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');
                sessionStorage.setItem('mia-demo-request',requestId); }
              const redeemed = await fetch('/redeem', {method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({token:document.getElementById('code').value.trim(),request_id:requestId})});
              if (!redeemed.ok) throw new Error('Convite inválido, expirado ou já utilizado.');
              const receipt=await redeemed.json(); session=receipt.download_token;
              sessionStorage.setItem('mia-demo-download',JSON.stringify(receipt)); document.getElementById('code').value='';
            }
            state.textContent='Baixando. Se a conexão falhar, tente novamente nesta janela.';
            const response = await fetch('/download', {headers:{Authorization:'Bearer '+session}});
            if (response.status===401) { session=null; requestId=null; sessionStorage.removeItem('mia-demo-download'); sessionStorage.removeItem('mia-demo-request'); }
            if (!response.ok) throw new Error('Download indisponível. Tente novamente ou peça um novo convite.');
            const link=document.createElement('a'), url=URL.createObjectURL(await response.blob());
            link.href=url; link.download='FILENAME'; link.click(); setTimeout(()=>URL.revokeObjectURL(url),60000);
            state.textContent='Download concluído. Abra a Mia e escolha onde guardar seu contexto.';
          } catch (error) { state.textContent=error.message; } finally { button.disabled=false; }
        };</script></html>""".replace("FILENAME", html.escape(filename)).replace("SCRIPT_NONCE", html.escape(request.state.csp_nonce))

    @app.post("/redeem")
    async def redeem(request: Request):
        # Bound the actual body before parsing and never echo a token in a
        # validation error (the framework's default errors include inputs).
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                raise HTTPException(413, "Pedido de resgate excedeu o limite")
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict) or "token" not in payload or set(payload) - {"token", "request_id"} or not isinstance(payload["token"], str) or len(payload["token"]) > 100:
                raise ValueError
            if "request_id" in payload and (not isinstance(payload["request_id"], str) or len(payload["request_id"]) > 100):
                raise ValueError
        except (ValueError, UnicodeError, RecursionError):
            raise HTTPException(400, "Pedido de resgate inválido") from None
        try:
            return {**store.redeem(payload["token"], sha256, request_id=payload.get("request_id")), "download_path": "/download", "filename": filename, "size": info.st_size, "sha256": sha256}
        except DistributionError:
            raise HTTPException(410, "Convite inválido, expirado ou já utilizado") from None

    @app.get("/download")
    def download(authorization: str = Header(default=""), range: str | None = Header(default=None)):
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Sessão de download necessária")
        try:
            store.authorize(authorization[7:], sha256)
        except DistributionError:
            raise HTTPException(401, "Sessão de download inválida ou expirada") from None
        start, end, partial = _range(range, info.st_size)
        fd = os.open(artifact, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        current = os.fstat(fd)
        if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != identity:
            os.close(fd)
            raise HTTPException(503, "Artefato mudou; distribuição pausada")

        closed = False
        def close() -> None:
            nonlocal closed
            if not closed:
                closed = True
                os.close(fd)
        def chunks() -> Iterator[bytes]:
            try:
                os.lseek(fd, start, os.SEEK_SET)
                remaining = end - start + 1
                while remaining:
                    chunk = os.read(fd, min(256 * 1024, remaining))
                    if not chunk:
                        raise DistributionError("Artefato incompleto")
                    remaining -= len(chunk)
                    yield chunk
            finally:
                close()

        headers = {"Accept-Ranges": "bytes", "Content-Length": str(end - start + 1),
                   "Content-Disposition": f'attachment; filename="{filename}"', "ETag": '"' + sha256 + '"'}
        if partial:
            headers["Content-Range"] = f"bytes {start}-{end}/{info.st_size}"
        return _ClosingStream(chunks(), status_code=206 if partial else 200,
                              media_type="application/octet-stream", headers=headers, close=close)

    return app
