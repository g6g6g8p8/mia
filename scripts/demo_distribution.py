#!/usr/bin/env python3
"""Private operator CLI. No network-facing invitation administration endpoint."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mia.demo_distribution import InvitationStore, create_distribution_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Distribuição privada Mia Demo")
    parser.add_argument("--state", type=Path, required=True, help="Diretório privado fora do checkout (0700)")
    actions = parser.add_subparsers(dest="action", required=True)
    issue = actions.add_parser("issue", help="Emite um convite; guarde o resultado em local privado")
    issue.add_argument("--days", type=int, default=7)
    issue.add_argument("--public-url", help="Origem HTTPS já publicada; convite no fragmento, fora dos logs HTTP")
    revoke = actions.add_parser("revoke")
    revoke.add_argument("invitation_id")
    actions.add_parser("list")
    serve = actions.add_parser("serve", help="Loopback; publicação HTTPS deve ser configurada separadamente")
    serve.add_argument("--artifact", type=Path, required=True)
    serve.add_argument("--sha256", required=True)
    serve.add_argument("--port", type=int, default=8130)
    args = parser.parse_args()
    if args.state.absolute().is_relative_to(Path(__file__).resolve().parents[1]):
        parser.error("Convites e tokens precisam ficar fora do repositório")
    if args.action == "serve":
        if not 1024 <= args.port <= 65535:
            parser.error("Porta precisa ficar entre 1024 e 65535")
        import uvicorn
        app = create_distribution_app(args.state, args.artifact, sha256=args.sha256)
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
        return
    store = InvitationStore(args.state)
    if args.action == "issue":
        if args.public_url:
            parsed = urllib.parse.urlsplit(args.public_url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/") or any(ord(c) < 33 for c in args.public_url):
                parser.error("Endereço público precisa ser uma origem HTTPS sem credenciais ou parâmetros")
        invitation = store.issue(ttl=args.days * 86400)
        if args.public_url:
            invitation["invite_url"] = args.public_url.rstrip("/") + "/invite#" + invitation["token"]
        print(json.dumps(invitation, ensure_ascii=False))
    elif args.action == "revoke":
        store.revoke(args.invitation_id)
        print(json.dumps({"revoked": True}))
    else:
        print(json.dumps(store.list_invitations(), ensure_ascii=False))


if __name__ == "__main__":
    main()
