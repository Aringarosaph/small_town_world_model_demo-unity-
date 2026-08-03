"""Deterministically generate the private M4 JSON Schema artifacts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from town_core.modeling.contracts import (
    CandidateFeatureRow,
    DatasetManifest,
    EvaluationReport,
    OutcomeLabel,
    OutcomePackage,
    SocialAnchor,
    SocialAnchorApprovalManifest,
    SocialAnchorCoveragePolicy,
    SocialAnchorJudgment,
    SocialAnchorReviewIssue,
    SocialAnchorTask,
    SocialAnchorTrainingInputManifest,
    TrainingExample,
)

SCHEMA_ADAPTERS: Mapping[str, TypeAdapter[Any]] = {
    "candidate-feature-row": TypeAdapter(CandidateFeatureRow),
    "outcome-label": TypeAdapter(OutcomeLabel),
    "training-example": TypeAdapter(TrainingExample),
    "social-anchor": TypeAdapter(SocialAnchor),
    "social-anchor-approval-manifest": TypeAdapter(SocialAnchorApprovalManifest),
    "social-anchor-coverage-policy": TypeAdapter(SocialAnchorCoveragePolicy),
    "social-anchor-judgment": TypeAdapter(SocialAnchorJudgment),
    "social-anchor-review-issue": TypeAdapter(SocialAnchorReviewIssue),
    "social-anchor-task": TypeAdapter(SocialAnchorTask),
    "social-anchor-training-input-manifest": TypeAdapter(SocialAnchorTrainingInputManifest),
    "dataset-manifest": TypeAdapter(DatasetManifest),
    "outcome-package": TypeAdapter(OutcomePackage),
    "evaluation-report": TypeAdapter(EvaluationReport),
}

VERSION_DOCUMENT = {
    "project_name": "Small Town World Model（STWM）",
    "feature_version": "v0.1",
    "label_version": "v0.1",
    "schemas": {
        "candidate-feature-row": "stwm.model.candidate-feature-row/v1",
        "dataset-manifest": "stwm.model.dataset-manifest/v1",
        "evaluation-report": "stwm.model.evaluation-report/v1",
        "outcome-label": "stwm.model.outcome-label/v1",
        "outcome-package": "stwm.model.outcome-package/v1",
        "social-anchor": "stwm.model.social-anchor/v1",
        "social-anchor-approval-manifest": "stwm.model.social-anchor-approval-manifest/v1",
        "social-anchor-coverage-policy": "stwm.model.social-anchor-coverage-policy/v1",
        "social-anchor-judgment": "stwm.model.social-anchor-judgment/v1",
        "social-anchor-review-issue": "stwm.model.social-anchor-review-issue/v1",
        "social-anchor-task": "stwm.model.social-anchor-task/v1",
        "social-anchor-training-input-manifest": "stwm.model.social-anchor-training-input-manifest/v1",
        "training-example": "stwm.model.training-example/v1",
    },
}


def build_schemas() -> dict[str, dict[str, Any]]:
    return {name: adapter.json_schema(mode="validation") for name, adapter in sorted(SCHEMA_ADAPTERS.items())}


def write_artifacts(root: Path) -> None:
    schemas_path = root / "jsonschema"
    schemas_path.mkdir(parents=True, exist_ok=True)
    for name, schema in build_schemas().items():
        (schemas_path / f"{name}.schema.json").write_text(
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (root / "version.json").write_text(
        json.dumps(VERSION_DOCUMENT, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate committed M4 model schemas")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--root", type=Path, default=Path("model"))
    arguments = parser.parse_args(argv)
    if arguments.write:
        write_artifacts(arguments.root)
    else:
        print(json.dumps(build_schemas(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
