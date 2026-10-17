#!/usr/bin/env python3
"""Private release operator CLI; participants never run these commands."""
from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mia.release_publication import (ARCHITECTURES, OpenSSLSigner, PublicationError, SparkleSigner, _receipt_metadata, _write_new,
    acceptance_template, attest_signed_dmg, canonical, channel_for, create_release_distribution_app, publication_plan, read_attestation, read_json, stage_release)
from mia.operations import OperationError


def _outside_checkout(path: Path) -> Path:
    path = Path(path)
    if any(part.is_symlink() for part in (path, *path.absolute().parents)):
        raise PublicationError("Material de publicação não aceita links simbólicos")
    path = path.resolve()
    if path.is_relative_to(ROOT):
        raise PublicationError("Estado, aceites e material gerado precisam ficar fora do repositório")
    return path


def _pair_arguments(parser, *, wheelhouses=False, attestations=False):
    for architecture in ARCHITECTURES:
        parser.add_argument("--" + architecture + "-dmg", type=Path)
        parser.add_argument("--" + architecture + ("-attestation" if attestations else "-receipt"), type=Path)
        if wheelhouses:
            parser.add_argument("--" + architecture + "-wheelhouse", type=Path)


def _selected(args, *, attestations=False, wheelhouses=False):
    selected = []
    for architecture in ARCHITECTURES:
        values = [getattr(args, architecture + "_dmg"), getattr(args, architecture + ("_attestation" if attestations else "_receipt"))]
        if wheelhouses:
            values.append(getattr(args, architecture + "_wheelhouse"))
        if any(value is not None for value in values):
            if any(value is None for value in values):
                raise PublicationError("Cada arquitetura oferecida precisa do conjunto completo de DMG, recibo/atestação e wheels")
            selected.append(architecture)
    if not selected:
        raise PublicationError("Selecione pelo menos uma arquitetura Mac explicitamente oferecida")
    return selected


def _trust_arguments(parser):
    parser.add_argument("--origin", required=True, help="Origem HTTPS estável já escolhida pelo operador")
    parser.add_argument("--channel", default="beta")
    parser.add_argument("--build-public-key", required=True, help="Chave pública Ed25519 de atestação de build, separada das chaves de atualização")


def _sparkle_arguments(parser):
    parser.add_argument("--sparkle-archive", type=Path, required=True, help="Sparkle-2.10.0.tar.xz oficial; SHA256 fixado na fonte")
    parser.add_argument("--sparkle-account", default="ed25519", help="Nome de conta Keychain existente; nenhuma chave privada no argumento")
    parser.add_argument("--sparkle-key-file", type=Path, help="Arquivo privado 0600 fora do checkout, no formato do sign_update")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    channels = actions.add_parser("channels", help="Grava somente URLs e chaves públicas por arquitetura")
    channels.add_argument("--origin", required=True)
    channels.add_argument("--channel", default="beta")
    channels.add_argument("--backend-public-key", required=True)
    channels.add_argument("--sparkle-public-key", required=True)
    channels.add_argument("--output", type=Path, required=True)
    template = actions.add_parser("acceptance-template", help="Aceites reais começam todos not_run; jamais são inferidos do build")
    _pair_arguments(template)
    template.add_argument("--output", type=Path, required=True)
    plan = actions.add_parser("plan", help="Revisa artefatos/canais/aceites e aponta gates pendentes, sem publicar")
    _pair_arguments(plan)
    _trust_arguments(plan)
    plan.add_argument("--acceptance", type=Path)
    attest = actions.add_parser("attest-mac", help="Mac: verifica bytes montados, tickets Apple e Gatekeeper, e assina a atestação")
    attest.add_argument("--dmg", type=Path, required=True)
    attest.add_argument("--receipt", type=Path, required=True)
    attest.add_argument("--build-public-key", required=True)
    attest.add_argument("--output", type=Path, required=True)
    _sparkle_arguments(attest)
    for action in ("stage", "refresh"):
        stage = actions.add_parser(action, help="Prepara publicação imutável autenticada" if action == "stage" else "Renova validade, conservando os mesmos artefatos e aceites")
        _pair_arguments(stage, wheelhouses=True, attestations=True)
        _trust_arguments(stage)
        _sparkle_arguments(stage)
        stage.add_argument("--state", type=Path, required=True)
        stage.add_argument("--source", type=Path, default=ROOT)
        stage.add_argument("--acceptance", type=Path, required=True)
        stage.add_argument("--approve-sha256", required=True)
        stage.add_argument("--notes-file", type=Path, required=True)
        stage.add_argument("--days", type=int, default=7)
        key = stage.add_mutually_exclusive_group()
        key.add_argument("--backend-key-file", type=Path, help="Ed25519 PEM privado, OpenSSL disponível; nenhum segredo no argumento")
        key.add_argument("--backend-keychain-account", default="mia-backend", help="Conta Keychain existente, assinada pela ferramenta Sparkle autenticada")
    serve = actions.add_parser("serve", help="Ensaio privado loopback da publicação, sem logs de acesso nem administração pública")
    serve.add_argument("--state", type=Path, required=True)
    serve.add_argument("--invitation-state", type=Path, required=True)
    serve.add_argument("--port", type=int, default=8130)
    args = parser.parse_args()
    try:
        if args.action == "channels":
            output = _outside_checkout(args.output)
            if output.exists() or output.is_symlink():
                raise PublicationError("Destino já existe e foi preservado")
            output.mkdir(parents=True, mode=0o700)
            for architecture in ARCHITECTURES:
                value = channel_for(args.origin, args.channel, architecture, args.backend_public_key, args.sparkle_public_key)
                _write_new(output / (architecture + ".json"), canonical(value) + b"\n")
            result = {"directory": str(output), "public_trust_configuration_only": True}
        elif args.action in ("acceptance-template", "plan"):
            receipts = [_receipt_metadata(read_json(getattr(args, arch + "_receipt")), getattr(args, arch + "_dmg"), require_apple=False) for arch in _selected(args)]
            if args.action == "acceptance-template":
                output = _outside_checkout(args.output)
                _write_new(output, canonical(acceptance_template(receipts)) + b"\n")
                result = {"output": str(output), "all_checks": "not_run", "operator_approved": False}
            else:
                ledger = read_json(args.acceptance) if args.acceptance else None
                result = publication_plan(receipts, ledger, origin=args.origin, channel=args.channel, build_public_key=args.build_public_key)
        elif args.action == "attest-mac":
            if args.sparkle_key_file:
                _outside_checkout(args.sparkle_key_file)
            with contextlib.closing(SparkleSigner(args.sparkle_archive, args.build_public_key, account=args.sparkle_account, key_file=args.sparkle_key_file)) as signer:
                result = attest_signed_dmg(args.dmg, args.receipt, _outside_checkout(args.output), signer)
        elif args.action in ("stage", "refresh"):
            state = _outside_checkout(args.state)
            _outside_checkout(args.acceptance)
            offered = _selected(args, attestations=True, wheelhouses=True)
            receipts = [read_attestation(getattr(args, arch + "_attestation"), getattr(args, arch + "_dmg"), args.build_public_key) for arch in offered]
            public_channel = receipts[0]["release_channel"]
            with contextlib.ExitStack() as stack:
                if args.sparkle_key_file:
                    _outside_checkout(args.sparkle_key_file)
                sparkle = stack.enter_context(contextlib.closing(SparkleSigner(args.sparkle_archive, public_channel["sparkle_public_key"], account=args.sparkle_account, key_file=args.sparkle_key_file)))
                if args.backend_key_file:
                    backend = OpenSSLSigner(_outside_checkout(args.backend_key_file))
                else:
                    backend = stack.enter_context(contextlib.closing(SparkleSigner(args.sparkle_archive, public_channel["backend_public_key"], account=args.backend_keychain_account)))
                result = stage_release(state, source=args.source, artifacts={arch: getattr(args, arch + "_dmg") for arch in offered},
                    attestations={arch: getattr(args, arch + "_attestation") for arch in offered}, wheelhouses={arch: getattr(args, arch + "_wheelhouse") for arch in offered},
                    acceptance_path=args.acceptance, origin=args.origin, channel=args.channel, build_public_key=args.build_public_key,
                    backend_signer=backend, sparkle_signer=sparkle, approve_sha256=args.approve_sha256, notes=args.notes_file.read_text(), lifetime_days=args.days, refresh=args.action == "refresh")
        else:
            if not 1024 <= args.port <= 65535:
                raise PublicationError("Porta loopback inválida")
            import uvicorn
            app = create_release_distribution_app(_outside_checkout(args.state), _outside_checkout(args.invitation_state))
            uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
            return
        print(json.dumps(result, ensure_ascii=False))
    except (PublicationError, OSError, ValueError, OperationError):
        parser.exit(2, "Operação não concluída: revise artefatos, aceites, plano e recursos de assinatura. Nenhum convite foi enviado.\n")


if __name__ == "__main__":
    main()
