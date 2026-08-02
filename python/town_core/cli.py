"""Command-line entry points for Small Town World Model（STWM）."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from town_core.catalogs import CatalogValidationError, load_catalog, load_m3_catalogs, m3_catalog_hash
from town_core.replay import replay_run
from town_core.simulation.run import run_headless
from town_core.society.checkpoint import load_checkpoint
from town_core.society.replay import replay_society_run
from town_core.society.run import run_society


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
    society = subparsers.add_parser("run-society", help="run the deterministic ten-NPC M3 society")
    society.add_argument("--config", required=True, help="path to config/v0")
    society.add_argument("--days", type=int, default=1, help="scenario end in complete game days")
    society.add_argument("--seed", type=int, default=12345, help="non-negative deterministic world seed")
    society.add_argument("--out", type=Path, help="exact new M3 run directory")
    society.add_argument("--output-root", type=Path, default=Path("runs"), help="generated run parent")
    society.add_argument("--chunk-minutes", type=int, default=1, help="driver chunk; authority ticks stay 1 minute")
    society.add_argument("--resume-checkpoint", type=Path, help="SIM-owned six-hour M3 checkpoint")
    society_replay = subparsers.add_parser(
        "replay-society", help="replay M3 authority patches without policy recomputation"
    )
    society_replay.add_argument("--run", required=True, type=Path, help="source M3 run directory")
    society_replay.add_argument("--output-root", type=Path, help="new replay-run parent directory")
    society_replay.add_argument("--from-checkpoint", type=Path, help="resume replay from a six-hour checkpoint")
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
    if args.command == "run-society":
        try:
            catalog = load_catalog(args.config)
            m3_catalogs = load_m3_catalogs(args.config, catalog=catalog)
            checkpoint = load_checkpoint(args.resume_checkpoint) if args.resume_checkpoint else None
            summary = run_society(
                catalog,
                m3_catalogs,
                days=args.days,
                seed=args.seed,
                output_root=args.output_root,
                run_path=args.out,
                chunk_minutes=args.chunk_minutes,
                resume_checkpoint=checkpoint,
            )
        except (CatalogValidationError, OSError, TypeError, ValueError, KeyError, RuntimeError) as exc:
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
    if args.command == "replay-society":
        try:
            summary = replay_society_run(
                args.run,
                output_root=args.output_root,
                from_checkpoint=args.from_checkpoint,
            )
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
