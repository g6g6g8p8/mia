#!/usr/bin/env python3
"""Prepare and verify Vercel distribution; no personal Mac/server modification."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.parse

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mia.release_publication import ARCHITECTURES, PublicationError, _regular, _verified_publication, _write_new, canonical, read_json
from mia.vercel_distribution import UpstashInvitationStore
from mia.vercel_release import BlobArtifactUploader, _release_config, vercel_deployment_plan, write_vercel_kit


def _outside(path: Path) -> Path:
    path = Path(path)
    if any(part.is_symlink() for part in (path, *path.absolute().parents)):
        raise PublicationError("Material de publicação não aceita links simbólicos")
    path = path.resolve()
    if path.is_relative_to(ROOT):
        raise PublicationError("Planos, artefatos, convites e kits precisam ficar fora do checkout")
    return path


def _store(config):
    return UpstashInvitationStore(os.environ.get("UPSTASH_REDIS_REST_URL"), os.environ.get("UPSTASH_REDIS_REST_TOKEN"), namespace=config["invitation_namespace"])


def _verified_health(config):
    try:
        response = httpx.get(config["origin"] + "/health", follow_redirects=False, timeout=15)
        if response.status_code != 200 or len(response.content) > 16384:
            raise ValueError
        result = response.json()
        if result.get("ok") is not True or result.get("hosting") != "vercel" or result.get("service") != "mia-demo-distribution" or result.get("release_id") != config["current_release_id"]:
            raise ValueError
        return {"https_verified": True, "release_id": result["release_id"]}
    except (httpx.HTTPError, ValueError, TypeError):
        raise PublicationError("HTTPS não confirmou a publicação esperada; nenhum convite será emitido") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    plan = actions.add_parser("plan", help="Escolhe origem estável e lista recursos/gates Vercel; não publica")
    plan.add_argument("--domain", required=True)
    plan.add_argument("--project-name", required=True)
    plan.add_argument("--private-store-id")
    plan.add_argument("--public-store-id")
    plan.add_argument("--state", type=Path, help="Publicação assinada e aceita já preparada; opcional no kit inicial")
    plan.add_argument("--output", type=Path, required=True)
    kit = actions.add_parser("kit", help="Projeto Vercel concreto; sem release aprovado retorna 503, nunca beta ready")
    kit.add_argument("--plan", type=Path, required=True)
    kit.add_argument("--state", type=Path)
    kit.add_argument("--uploads", type=Path, help="Inventário privado de uploads já verificados")
    kit.add_argument("--source", type=Path, default=ROOT)
    kit.add_argument("--output", type=Path, required=True)
    upload = actions.add_parser("upload", help="Upload Blob aprovado e verificação dos bytes; credenciais somente no ambiente")
    upload.add_argument("--plan", type=Path, required=True)
    upload.add_argument("--state", type=Path, required=True)
    upload.add_argument("--approve-sha256", required=True)
    upload.add_argument("--output", type=Path, required=True)
    for action in ("verify", "issue-invite", "list-invites", "revoke-invite"):
        sub = actions.add_parser(action)
        sub.add_argument("--kit", type=Path, required=True)
        if action == "issue-invite":
            sub.add_argument("--days", type=int, default=7)
            sub.add_argument("--output", type=Path, required=True, help="Convite/token em arquivo privado; nunca no stdout/chat")
        if action == "revoke-invite":
            sub.add_argument("--id", required=True)
    args = parser.parse_args()
    try:
        if args.action == "plan":
            publication = read_json(_outside(args.state) / "current.json", private=True) if args.state else None
            result = vercel_deployment_plan(domain=args.domain, project_name=args.project_name, private_store_id=args.private_store_id, public_store_id=args.public_store_id, publication=publication)
            _write_new(_outside(args.output), canonical(result) + b"\n")
        elif args.action == "kit":
            result = write_vercel_kit(read_json(args.plan), _outside(args.output), source=args.source, publisher_state=_outside(args.state) if args.state else None,
                uploads=read_json(args.uploads).get("uploads") if args.uploads else None)
        elif args.action == "upload":
            plan = read_json(args.plan)
            if args.approve_sha256 != plan.get("approve_sha256") or args.approve_sha256 != __import__("hashlib").sha256(canonical({key: value for key, value in plan.items() if key != "approve_sha256"})).hexdigest():
                raise PublicationError("Upload exige aprovação do plano exato")
            output = _outside(args.output)
            if output.exists() or output.is_symlink():
                raise PublicationError("Inventário de upload anterior foi preservado")
            state = _outside(args.state)
            publication = read_json(state / "current.json", private=True)
            _verified_publication(state, publication)
            if plan.get("publication_sha256") != __import__("hashlib").sha256(canonical(publication)).hexdigest():
                raise PublicationError("Publicação mudou depois da revisão do plano")
            private = BlobArtifactUploader(token=os.environ.get("BLOB_READ_WRITE_TOKEN"), store_id=plan["private_blob_store_id"], access="private")
            public = BlobArtifactUploader(token=os.environ.get("MIA_PUBLIC_BLOB_READ_WRITE_TOKEN"), store_id=plan["public_blob_store_id"], access="public")
            records = []
            for release_path in sorted((state / "releases").iterdir()):
                manifest = read_json(release_path / "publication.json", private=True)
                _verified_publication(state, manifest)
                for artifact in manifest["artifacts"]:
                    name = "Mia-" + artifact["architecture"] + ".dmg"
                    records.append(private.upload(release_path / name, manifest["release_id"] + "/" + name, sha256=manifest["files"][name]["sha256"]))
                for name, entry in manifest["files"].items():
                    if name.endswith(".zip"):
                        records.append(public.upload(release_path / name, manifest["release_id"] + "/" + name, sha256=entry["sha256"]))
            _write_new(output, canonical({"protocol": 1, "uploads": records}) + b"\n")
            result = {"uploads_verified": len(records), "output": str(output), "vercel_deployed": False, "invitations_sent": 0}
        else:
            config = _release_config(read_json(args.kit / "distribution-release.json"))
            if args.action == "verify":
                result = _verified_health(config)
                for architecture in next(release for release in config["releases"] if release["release_id"] == config["current_release_id"])["artifacts"]:
                    response = httpx.get(config["origin"] + "/updates/" + architecture + "/appcast.xml", follow_redirects=False, timeout=15)
                    if response.status_code != 401:
                        raise PublicationError("Appcast não protege as atualizações privadas; publicação não foi aprovada")
                result["private_appcasts_require_activation"] = True
                result["actual_beta_activation_and_download_verified"] = False
            elif args.action == "issue-invite":
                output = _outside(args.output)
                if output.exists() or output.is_symlink():
                    raise PublicationError("Destino do convite já existe; foi preservado")
                _verified_health(config)
                invitation = _store(config).issue(ttl=args.days * 86400)
                invitation["invite_url"] = config["origin"] + "/invite#" + invitation["token"]
                _write_new(output, canonical(invitation) + b"\n")
                result = {"id": invitation["id"], "output": str(output), "invitations_sent": 0}
            elif args.action == "list-invites":
                result = _store(config).list_invitations()
            else:
                _store(config).revoke(args.id)
                result = {"revoked": True, "id": args.id, "installed_libraries_modified": False}
        print(json.dumps(result, ensure_ascii=False))
    except (PublicationError, ValueError, OSError, KeyError, TypeError, httpx.HTTPError):
        parser.exit(2, "Distribuição não concluída: revise o plano, gates e recursos. Nenhum serviço pessoal foi alterado; credenciais não são exibidas.\n")


if __name__ == "__main__":
    main()
