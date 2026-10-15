"""Durable invitation metadata and short leases for private Vercel Blob DMGs.

No DMG crosses the serverless function: after invitation/session authorization,
Blob issues a read-only, one-object URL valid for at most sixty seconds. The
Upstash REST credential and Blob read-write credential remain server-side.

The wire protocol follows official vercel/storage @vercel/blob 2.8.2 (API 13):
``issueSignedToken`` and ``presignUrl``. This is an implementation of that
protocol using Python's standard library, without bundling the JavaScript SDK.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from mia.demo_distribution import DistributionError, DOWNLOAD_TTL, MAX_INVITATION_TTL

MAX_RECORDS = 1000
MAX_REDIS_RESPONSE = 512 * 1024
MAX_BLOB_RESPONSE = 16 * 1024
DOWNLOAD_LEASE = 60
BETA_ACCESS_TTL = 90 * 86400
ARCHITECTURES = ("arm64", "x86_64")
BLOB_API_URL = "https://vercel.com/api/blob/signed-token"
BLOB_API_VERSION = "13"


class VercelDistributionUnavailable(DistributionError):
    """Infrastructure failure; callers should return a fixed 503 response."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _post_json(url: str, token: str, payload, *, maximum: int, headers: dict | None = None):
    # No query-string credentials, redirects, debug response bodies, or retries
    # that silently replay a mutation. Redemptions are explicitly idempotent.
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode()
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json",
        "Accept": "application/json", **(headers or {}),
    })
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=8) as response:
            if response.getcode() != 200 or response.headers.get_content_type() != "application/json":
                raise ValueError
            data = response.read(maximum + 1)
        if len(data) > maximum:
            raise ValueError
        return json.loads(data)
    except (OSError, ValueError, UnicodeError, RecursionError, urllib.error.URLError):
        raise VercelDistributionUnavailable("Serviço de distribuição indisponível; tente novamente") from None


def _secret(value: str) -> str:
    if not isinstance(value, str) or not 20 <= len(value) <= 2048 or not re.fullmatch(r"[!-~]+", value):
        raise DistributionError("Credencial de distribuição ausente ou inválida")
    return value


def _now(value: int | None) -> int:
    value = int(time.time()) if value is None else value
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**40:
        raise DistributionError("Horário de distribuição inválido")
    return value


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _capability(domain: bytes, secret: str, nonce: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(domain + b"\0" + secret.encode() + b"\0" + nonce.encode()).digest()).rstrip(b"=").decode()


def _architecture(value: str) -> str:
    if not isinstance(value, str) or value not in ARCHITECTURES:
        raise DistributionError("Arquitetura de demonstração inválida")
    return value


_ISSUE = r"""
if redis.call('ZCARD', KEYS[4]) >= tonumber(ARGV[5]) then return '{"ok":false,"code":"capacity"}' end
if redis.call('HEXISTS', KEYS[1], ARGV[1]) == 1 or redis.call('HEXISTS', KEYS[2], ARGV[2]) == 1 then
  return '{"ok":false,"code":"collision"}'
end
local record = {id=ARGV[1],token_hash=ARGV[2],created_at=tonumber(ARGV[3]),expires_at=tonumber(ARGV[4])}
redis.call('HSET', KEYS[1], ARGV[1], cjson.encode(record))
redis.call('HSET', KEYS[2], ARGV[2], ARGV[1])
redis.call('ZADD', KEYS[4], ARGV[3], ARGV[1])
return '{"ok":true}'
"""

_REVOKE = r"""
local raw=redis.call('HGET',KEYS[1],ARGV[1])
if raw then local item=cjson.decode(raw); item.revoked_at=tonumber(ARGV[2]); redis.call('HSET',KEYS[1],ARGV[1],cjson.encode(item)) end
return '{"ok":true}'
"""

_REDEEM = r"""
local identity=redis.call('HGET',KEYS[2],ARGV[1])
if not identity then return '{"ok":false,"code":"invite"}' end
local raw=redis.call('HGET',KEYS[1],identity)
if not raw then return '{"ok":false,"code":"invite"}' end
local invite=cjson.decode(raw)
local now=tonumber(ARGV[5])
if invite.revoked_at then return '{"ok":false,"code":"invite"}' end
if invite.redeemed_at then
  if invite.redemption_request_hash ~= ARGV[3] then return '{"ok":false,"code":"invite"}' end
  local old=redis.call('HGET',KEYS[3],ARGV[4])
  if not old then return '{"ok":false,"code":"session"}' end
  local session=cjson.decode(old)
  if session.invitation_id ~= identity or session.expires_at <= now or session.artifact_sha256 ~= ARGV[2] or session.architecture ~= ARGV[7] then
    return '{"ok":false,"code":"session"}'
  end
  local old_ticket=redis.call('HGET',KEYS[5],ARGV[8])
  if not old_ticket then return '{"ok":false,"code":"ticket"}' end
  local ticket=cjson.decode(old_ticket)
  if ticket.invitation_id ~= identity or ticket.architecture ~= ARGV[7] then return '{"ok":false,"code":"ticket"}' end
  return cjson.encode({ok=true,expires_at=session.expires_at})
end
if invite.expires_at <= now then return '{"ok":false,"code":"invite"}' end
local expiry=now+tonumber(ARGV[6])
invite.redeemed_at=now; invite.redemption_request_hash=ARGV[3]
redis.call('HSET',KEYS[1],identity,cjson.encode(invite))
redis.call('HSET',KEYS[3],ARGV[4],cjson.encode({invitation_id=identity,created_at=now,expires_at=expiry,artifact_sha256=ARGV[2],architecture=ARGV[7]}))
redis.call('HSET',KEYS[5],ARGV[8],cjson.encode({invitation_id=identity,created_at=now,expires_at=expiry,architecture=ARGV[7]}))
return cjson.encode({ok=true,expires_at=expiry})
"""

_AUTHORIZE = r"""
local raw=redis.call('HGET',KEYS[3],ARGV[1])
if not raw then return '{"ok":false,"code":"session"}' end
local session=cjson.decode(raw)
local invite_raw=redis.call('HGET',KEYS[1],session.invitation_id)
if not invite_raw then return '{"ok":false,"code":"session"}' end
local invite=cjson.decode(invite_raw)
if invite.revoked_at or session.expires_at <= tonumber(ARGV[3]) or session.artifact_sha256 ~= ARGV[2] then
  return '{"ok":false,"code":"session"}'
end
return cjson.encode({ok=true,expires_at=session.expires_at,invitation_id=session.invitation_id})
"""

_ACTIVATE = r"""
local raw=redis.call('HGET',KEYS[5],ARGV[1])
if not raw then return '{"ok":false,"code":"ticket"}' end
local ticket=cjson.decode(raw)
if ticket.architecture ~= ARGV[4] then return '{"ok":false,"code":"ticket"}' end
local invite_raw=redis.call('HGET',KEYS[1],ticket.invitation_id)
if not invite_raw then return '{"ok":false,"code":"ticket"}' end
local invite=cjson.decode(invite_raw)
if invite.revoked_at then return '{"ok":false,"code":"ticket"}' end
local now=tonumber(ARGV[5])
if ticket.activated_at then
  if ticket.client_nonce_hash ~= ARGV[2] or ticket.access_hash ~= ARGV[3] then return '{"ok":false,"code":"ticket"}' end
  local old=redis.call('HGET',KEYS[6],ARGV[3])
  if not old then return '{"ok":false,"code":"access"}' end
  local access=cjson.decode(old)
  if access.invitation_id ~= ticket.invitation_id or access.architecture ~= ARGV[4] or access.expires_at <= now then
    return '{"ok":false,"code":"access"}'
  end
  return cjson.encode({ok=true,expires_at=access.expires_at})
end
if ticket.expires_at <= now then return '{"ok":false,"code":"ticket"}' end
local expiry=now+tonumber(ARGV[6])
ticket.activated_at=now; ticket.client_nonce_hash=ARGV[2]; ticket.access_hash=ARGV[3]
redis.call('HSET',KEYS[5],ARGV[1],cjson.encode(ticket))
redis.call('HSET',KEYS[6],ARGV[3],cjson.encode({invitation_id=ticket.invitation_id,created_at=now,expires_at=expiry,architecture=ARGV[4]}))
return cjson.encode({ok=true,expires_at=expiry})
"""

_AUTHORIZE_BETA = r"""
local raw=redis.call('HGET',KEYS[6],ARGV[1])
if not raw then return '{"ok":false,"code":"access"}' end
local access=cjson.decode(raw)
if access.architecture ~= ARGV[2] or access.expires_at <= tonumber(ARGV[3]) then return '{"ok":false,"code":"access"}' end
local invite_raw=redis.call('HGET',KEYS[1],access.invitation_id)
if not invite_raw then return '{"ok":false,"code":"access"}' end
local invite=cjson.decode(invite_raw)
if invite.revoked_at then return '{"ok":false,"code":"access"}' end
return cjson.encode({ok=true,expires_at=access.expires_at,invitation_id=access.invitation_id})
"""

_LIST = r"""
local identities=redis.call('ZREVRANGE',KEYS[4],0,999)
if #identities == 0 then return '{"ok":true,"invitations":[]}' end
local records={}
for _,identity in ipairs(identities) do
  local raw=redis.call('HGET',KEYS[1],identity)
  if raw then
    local item=cjson.decode(raw)
    table.insert(records,{id=item.id,created_at=item.created_at,expires_at=item.expires_at,redeemed_at=item.redeemed_at or cjson.null,revoked_at=item.revoked_at or cjson.null})
  end
end
return cjson.encode({ok=true,invitations=records})
"""


class UpstashInvitationStore:
    """One atomic Lua operation per mutation, durable across function instances.

    Hashes share a Redis cluster hash slot. No invitation, request nonce, download
    token, activation ticket, update access token, or provider credential is
    persisted as plaintext. One activation per invitation binds a private client
    nonce and architecture; access authorizes official updates for ninety days,
    independently of the installed user's Mia library and core features. The small beta
    namespace is capped at 1,000 historical invitations; capacity requires an
    explicit operator retention decision rather than deleting audit metadata.
    """
    def __init__(self, url: str, token: str, namespace: str = "mia-demo-beta"):
        if not isinstance(url, str):
            raise DistributionError("Endereço Upstash inválido")
        try:
            parsed = urllib.parse.urlsplit(url)
            port = parsed.port
        except ValueError:
            raise DistributionError("Endereço Upstash inválido") from None
        if (parsed.scheme != "https" or not re.fullmatch(r"[a-z0-9-]+\.upstash\.io", parsed.hostname or "")
                or parsed.username is not None or parsed.password is not None or port is not None
                or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise DistributionError("Endereço Upstash exige a origem HTTPS oficial, sem parâmetros")
        if not isinstance(namespace, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,59}", namespace):
            raise DistributionError("Namespace de distribuição inválido")
        self.url, self._token = url.rstrip("/"), _secret(token)
        self.keys = ["{" + namespace + "}:" + name for name in ("invites", "tokens", "sessions", "index", "tickets", "beta-access")]

    def _eval(self, script: str, arguments: list[str | int]) -> dict:
        value = _post_json(self.url, self._token, ["EVAL", script, len(self.keys), *self.keys, *arguments], maximum=MAX_REDIS_RESPONSE)
        try:
            if not isinstance(value, dict) or "error" in value or not isinstance(value.get("result"), str):
                raise ValueError
            result = json.loads(value["result"])
            if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
                raise ValueError
        except (ValueError, RecursionError):
            raise VercelDistributionUnavailable("Registro de convites indisponível; tente novamente") from None
        if not result["ok"]:
            if result.get("code") == "capacity":
                raise DistributionError("Limite de convites atingido; o administrador precisa revisar a retenção")
            raise DistributionError("Convite ou sessão inválido, expirado, revogado ou já utilizado")
        return result

    def issue(self, *, ttl: int = 7 * 86400, now: int | None = None) -> dict:
        if isinstance(ttl, bool) or not isinstance(ttl, int) or not 60 <= ttl <= MAX_INVITATION_TTL:
            raise DistributionError("Prazo do convite deve ficar entre um minuto e trinta dias")
        now = _now(now)
        token, identity = "mia_invite_" + secrets.token_urlsafe(32), secrets.token_hex(16)
        self._eval(_ISSUE, [identity, _digest(token), now, now + ttl, MAX_RECORDS])
        return {"id": identity, "token": token, "expires_at": now + ttl}

    def revoke(self, invitation_id: str, *, now: int | None = None) -> None:
        if not isinstance(invitation_id, str) or not re.fullmatch(r"[a-f0-9]{32}", invitation_id):
            raise DistributionError("Identificador de convite inválido")
        self._eval(_REVOKE, [invitation_id, _now(now)])

    def redeem(self, token: str, artifact_sha256: str, *, request_id: str | None = None, architecture: str = "arm64", now: int | None = None) -> dict:
        if not isinstance(token, str) or not re.fullmatch(r"mia_invite_[A-Za-z0-9_-]{43}", token):
            raise DistributionError("Convite inválido, expirado ou já utilizado")
        if not isinstance(artifact_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", artifact_sha256):
            raise DistributionError("Artefato não identificado")
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", request_id):
            raise DistributionError("Resgate exige o identificador privado de repetição")
        architecture = _architecture(architecture)
        now = _now(now)
        secret = _capability(b"Mia download v1", token, request_id)
        session = "mia_download_" + secret
        ticket = _capability(b"Mia beta activation v1", token, request_id)
        result = self._eval(_REDEEM, [_digest(token), artifact_sha256, _digest(request_id), _digest(session), now, DOWNLOAD_TTL, architecture, _digest(ticket)])
        expiry = result.get("expires_at")
        if isinstance(expiry, bool) or not isinstance(expiry, int) or not now < expiry <= now + DOWNLOAD_TTL:
            raise VercelDistributionUnavailable("Registro de convites respondeu com prazo inválido")
        return {"download_token": session, "expires_at": expiry, "activation_ticket": ticket}

    def authorize(self, token: str, artifact_sha256: str, *, now: int | None = None) -> dict:
        if not isinstance(token, str) or not re.fullmatch(r"mia_download_[A-Za-z0-9_-]{43}", token):
            raise DistributionError("Sessão de download inválida ou expirada")
        if not isinstance(artifact_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", artifact_sha256):
            raise DistributionError("Artefato não identificado")
        now = _now(now)
        result = self._eval(_AUTHORIZE, [_digest(token), artifact_sha256, now])
        expiry, identity = result.get("expires_at"), result.get("invitation_id")
        if (isinstance(expiry, bool) or not isinstance(expiry, int) or not now < expiry <= now + DOWNLOAD_TTL
                or not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{32}", identity)):
            raise VercelDistributionUnavailable("Registro de convites respondeu com sessão inválida")
        return {"expires_at": expiry, "invitation_id": identity}

    def activate(self, ticket: str, client_nonce: str, architecture: str, *, now: int | None = None) -> dict:
        if (not isinstance(ticket, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", ticket)
                or not isinstance(client_nonce, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", client_nonce)):
            raise DistributionError("Ativação exige convite e identificador privado válidos")
        architecture, now = _architecture(architecture), _now(now)
        access = _capability(b"Mia beta access v1", ticket, client_nonce)
        result = self._eval(_ACTIVATE, [_digest(ticket), _digest(client_nonce), _digest(access), architecture, now, BETA_ACCESS_TTL])
        expiry = result.get("expires_at")
        if isinstance(expiry, bool) or not isinstance(expiry, int) or not now < expiry <= now + BETA_ACCESS_TTL:
            raise VercelDistributionUnavailable("Registro de convites respondeu com ativação inválida")
        return {"access_token": access, "expires_at": expiry}

    def authorize_beta(self, access_token: str, architecture: str, *, now: int | None = None) -> dict:
        if not isinstance(access_token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", access_token):
            raise DistributionError("Acesso às atualizações beta inválido ou expirado")
        architecture, now = _architecture(architecture), _now(now)
        result = self._eval(_AUTHORIZE_BETA, [_digest(access_token), architecture, now])
        expiry, identity = result.get("expires_at"), result.get("invitation_id")
        if (isinstance(expiry, bool) or not isinstance(expiry, int) or not now < expiry <= now + BETA_ACCESS_TTL
                or not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{32}", identity)):
            raise VercelDistributionUnavailable("Registro de convites respondeu com acesso beta inválido")
        return {"expires_at": expiry, "invitation_id": identity}

    def list_invitations(self) -> list[dict]:
        result = self._eval(_LIST, [])
        records = result.get("invitations")
        if not isinstance(records, list) or len(records) > MAX_RECORDS:
            raise VercelDistributionUnavailable("Registro de convites respondeu com lista inválida")
        clean = []
        for row in records:
            if not isinstance(row, dict) or set(row) != {"id", "created_at", "expires_at", "redeemed_at", "revoked_at"}:
                raise VercelDistributionUnavailable("Registro de convites respondeu com lista inválida")
            if not isinstance(row["id"], str) or not re.fullmatch(r"[a-f0-9]{32}", row["id"]):
                raise VercelDistributionUnavailable("Registro de convites respondeu com lista inválida")
            if any(isinstance(row[key], bool) or not isinstance(row[key], int) for key in ("created_at", "expires_at")):
                raise VercelDistributionUnavailable("Registro de convites respondeu com lista inválida")
            if any(row[key] is not None and (isinstance(row[key], bool) or not isinstance(row[key], int)) for key in ("redeemed_at", "revoked_at")):
                raise VercelDistributionUnavailable("Registro de convites respondeu com lista inválida")
            clean.append(row)
        return clean


class BlobPrivateDownloads:
    """Exact-path read-only leases; no function proxy and no permanent public URL.

    Revocation stops issuing new leases immediately. A previously issued URL is
    usable for its remaining lease (at most sixty seconds); a download already
    accepted by Blob can finish. This is a capability lifetime, not remote
    revocation of copies that a participant already downloaded.
    """
    def __init__(self, token: str, store_id: str):
        if not isinstance(store_id, str) or not re.fullmatch(r"(?:store_)?[A-Za-z0-9]{3,64}", store_id):
            raise DistributionError("Identificador do armazenamento Blob inválido")
        self._token, self.store_id = _secret(token), store_id.removeprefix("store_")

    def download_url(self, pathname: str, *, session_expires_at: int, now: int | None = None) -> dict:
        if (not isinstance(pathname, str) or len(pathname) > 512
                or not re.fullmatch(r"(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+\.dmg", pathname)
                or any(part in (".", "..") for part in pathname.split("/"))):
            raise DistributionError("Caminho do artefato Blob inválido")
        now = _now(now)
        if (isinstance(session_expires_at, bool) or not isinstance(session_expires_at, int)
                or session_expires_at <= now or session_expires_at > now + BETA_ACCESS_TTL):
            raise DistributionError("Sessão de download inválida ou expirada")
        expiry = min(now + DOWNLOAD_LEASE, session_expires_at)
        wire = _post_json(BLOB_API_URL, self._token,
            {"pathname": pathname, "operations": ["get"], "validUntil": expiry * 1000},
            maximum=MAX_BLOB_RESPONSE, headers={"x-api-version": BLOB_API_VERSION, "x-vercel-blob-store-id": self.store_id})
        try:
            if not isinstance(wire, dict) or set(wire) != {"delegationToken", "clientSigningToken", "validUntil"}:
                raise ValueError
            delegation, signing, until = wire["delegationToken"], wire["clientSigningToken"], wire["validUntil"]
            if not isinstance(delegation, str) or not re.fullmatch(r"[A-Za-z0-9_-]{20,12000}\.[A-Za-z0-9_-]{20,100}", delegation):
                raise ValueError
            if not isinstance(signing, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", signing):
                raise ValueError
            if isinstance(until, bool) or not isinstance(until, int) or not now * 1000 < until <= expiry * 1000:
                raise ValueError
            segment = delegation.split(".", 1)[0]
            payload = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
            if (not isinstance(payload, dict) or payload.get("storeId") not in (self.store_id, "store_" + self.store_id)
                    or payload.get("pathname") != pathname or payload.get("operations") != ["get"]
                    or payload.get("validUntil") != until or isinstance(payload.get("validUntil"), bool)):
                raise ValueError
        except (ValueError, UnicodeError, RecursionError):
            raise VercelDistributionUnavailable("Blob não confirmou a leitura privada e limitada do artefato") from None
        canonical = "operation=get\npathname=" + pathname
        signature = base64.urlsafe_b64encode(hmac.new(signing.encode(), canonical.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
        url = "https://" + self.store_id + ".private.blob.vercel-storage.com/" + pathname
        query = urllib.parse.urlencode({"vercel-blob-delegation": delegation, "vercel-blob-signature": signature})
        return {"url": url + "?" + query, "expires_at": until // 1000}
