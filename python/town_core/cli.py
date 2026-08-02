"""Command-line entry points for Small Town World Model（STWM）."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from town_core.catalogs import CatalogValidationError, load_catalog, load_m3_catalogs, m3_catalog_hash
from town_core.replay import replay_run
from town_core.simulation.run import run_headless


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m town_core.cli", description="Small Town World Model（STWM）")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-config", help="validate a complete V0 catalog")
    validate.add_argument("--config", required=True, help="path to config/v0")
    headless = subparsers.add_parser("run-headless", help="run the deterministic one-NPC M1 slice")
    headless.add_argument("--config", required=True, help="path to config/v0")
    headless.add_argument("--agent", default="npc_01", help="the sole enabled M1 agent")
    headless.add_argument("--days", type=int, default=3, help="number of complete game days")
    headless.add_argument("--seed", type=int, default=12345, help="non-negative deterministic world seed")
    headless.add_argument("--out", type=Path, help="exact new run directory (default: runs/<generated-id>)")
    headless.add_argument("--output-root", type=Path, default=Path("runs"), help="generated run parent directory")
    headless.add_argument(
        "--chunk-minutes", type=int, default=1, help="driver chunk size; authority ticks remain 1 minute"
    )
    replay = subparsers.add_parser("replay", help="apply committed authority transactions and verify final hash")
    replay.add_argument("--run", required=True, type=Path, help="source run directory")
    replay.add_argument("--output-root", type=Path, help="new replay-run parent directory")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "validate-config":
        try:
            catalog = load_catalog(args.config)
            m3_catalogs = load_m3_catalogs(args.config, catalog=catalog)
        except CatalogValidationError as exc:
            print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False))
            return 1
        summary = {
            "valid": True,
            "config_version": catalog.world.config_version,
            "schema_version": catalog.world.schema_version,
            "protocol_version": catalog.world.protocol_version,
            "counts": dict(catalog.world.fixed_counts),
            "m3_catalog_hash": m3_catalog_hash(m3_catalogs),
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "run-headless":
        try:
            catalog = load_catalog(args.config)
            summary = run_headless(
                catalog,
                active_agent_id=args.agent,
                days=args.days,
                seed=args.seed,
                output_root=args.output_root,
                run_path=args.out,
                chunk_minutes=args.chunk_minutes,
            )
        except (CatalogValidationError, OSError, ValueError) as exc:
            print(
                json.dumps(
                    {"completed": False, "error_type": type(exc).__name__, "error": str(exc)},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 1
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "replay":
        try:
            summary = replay_run(args.run, output_root=args.output_root)
        except (OSError, TypeError, ValueError, KeyError, RuntimeError) as exc:
            print(
                json.dumps(
                    {"completed": False, "error_type": type(exc).__name__, "error": str(exc)},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 1
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0 if summary["match"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
