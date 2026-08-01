"""Prepare the actionable M0 freeze manifest for Orchestrator review.

This command collects hashes but never marks a governance checklist item as
approved. The Orchestrator must review the integrated CONTRACTS artifacts and
turn each false item into true before the strict gate can pass.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from tools.diagnostics.check_m0 import (
    FREEZE_CHECKLIST_KEYS,
    FREEZE_MANIFEST_PATH,
    eligible_freeze_paths,
    find_repository_root,
    sha256_file,
)


def _head_commit(root: Path) -> str:
    completed = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git rev-parse HEAD failed")
    return completed.stdout.strip()


def build_candidate(root: Path, source_commit: str) -> dict[str, object]:
    """Build an unsigned manifest candidate from the integrated repository."""
    paths = sorted(eligible_freeze_paths(root))
    if not paths:
        raise RuntimeError("no config/protocol/domain Schema files found; integrate CONTRACTS first")
    return {
        "schema": "aitown.qa.m0-freeze/v1",
        "source_commit": source_commit,
        "approved_by": "",
        "approved_at_utc": None,
        "checklist": {key: False for key in FREEZE_CHECKLIST_KEYS},
        "files": [{"path": path, "sha256": sha256_file(root / path)} for path in paths],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root override")
    parser.add_argument(
        "--source-commit",
        help="reviewed integration commit (default: current HEAD)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=f"output path (default: {FREEZE_MANIFEST_PATH})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing candidate; requires a fresh manual review",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve() if args.root else find_repository_root()
    output = args.output or (root / FREEZE_MANIFEST_PATH)
    if not output.is_absolute():
        output = root / output
    if output.exists() and not args.force:
        raise SystemExit(f"refusing to overwrite {output}; pass --force to replace it")

    source_commit = args.source_commit or _head_commit(root)
    candidate = build_candidate(root, source_commit)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(candidate, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    generated_at = datetime.now(UTC).isoformat()
    print(f"wrote {output} at {generated_at}")
    print("next: manually review every checklist item, approved_by, and approved_at_utc")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
