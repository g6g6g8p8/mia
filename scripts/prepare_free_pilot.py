#!/usr/bin/env python3
"""Prepare review material for the free pilot; never deploy or issue invites."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mia.pilot_publication import acceptance_template, pilot_plan, validate_receipt, verify_mac_artifact
from mia.release_publication import PublicationError, _write_new, canonical, read_json
from scripts.publish_demo_release import _outside_checkout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("acceptance-template", "verify-mac", "plan"))
    parser.add_argument("--dmg", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--acceptance", type=Path)
    parser.add_argument("--mac-verification", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = _outside_checkout(args.output)
        artifact = _outside_checkout(args.dmg)
        receipt = validate_receipt(read_json(_outside_checkout(args.receipt)), artifact)
        if args.action == "acceptance-template":
            result = acceptance_template(receipt)
        elif args.action == "verify-mac":
            result = verify_mac_artifact(receipt, artifact)
        else:
            result = pilot_plan(receipt, artifact,
                read_json(_outside_checkout(args.acceptance)) if args.acceptance else None,
                read_json(_outside_checkout(args.mac_verification)) if args.mac_verification else None)
        _write_new(output, canonical(result) + b"\n")
        print("Material de revisão gravado. Nenhuma publicação ou convite realizado.")
    except (PublicationError, OSError, ValueError):
        parser.exit(2, "Preparação recusada; confira os arquivos, permissões e a política do piloto. Nada foi publicado.\n")


if __name__ == "__main__":
    main()
