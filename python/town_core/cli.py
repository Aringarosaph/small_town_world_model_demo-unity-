"""Minimal command-line entry points owned by the M0 contracts package."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from town_core.catalogs import CatalogValidationError, load_catalog


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m town_core.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-config", help="validate a complete V0 catalog")
    validate.add_argument("--config", required=True, help="path to config/v0")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "validate-config":
        try:
            catalog = load_catalog(args.config)
        except CatalogValidationError as exc:
            print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False))
            return 1
        summary = {
            "valid": True,
            "config_version": catalog.world.config_version,
            "schema_version": catalog.world.schema_version,
            "protocol_version": catalog.world.protocol_version,
            "counts": dict(catalog.world.fixed_counts),
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
