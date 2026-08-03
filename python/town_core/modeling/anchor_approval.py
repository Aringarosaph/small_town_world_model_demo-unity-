"""Assemble independent reviewer findings into hash-chained M4 draft approvals."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from town_core.catalogs import load_catalog
from town_core.domain.base import ContractModel
from town_core.domain.enums import BehaviorId
from town_core.modeling.anchor_review import _load_tasks, anchor_output_provenance_paths
from town_core.modeling.anchors import REPOSITORY_ROOT, _canonical, default_coverage_policy
from town_core.modeling.contracts import (
    SHA256_PATTERN,
    ArtifactDescriptor,
    SocialAnchorApprovalEntry,
    SocialAnchorApprovalManifest,
    SocialAnchorCoveragePolicy,
    SocialAnchorJudgment,
    SocialAnchorReviewIssue,
)
from town_core.modeling.postprocess import CatalogOutcomePostprocessor


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _descriptor(path: Path, *, manifest_directory: Path) -> ArtifactDescriptor:
    relative_path = Path(os.path.relpath(path.resolve(), start=manifest_directory.resolve())).as_posix()
    return ArtifactDescriptor(relative_path=relative_path, sha256=_sha256_file(path), bytes=path.stat().st_size)


def _ensure_external(path: Path) -> None:
    repository = REPOSITORY_ROOT.resolve()
    resolved = path.resolve()
    if resolved == repository or repository in resolved.parents:
        raise ValueError("M4 anchor review artifacts must remain outside the repository")


class ReviewerIssueResponse(ContractModel):
    severity: Literal["ADVISORY", "BLOCKING", "DISPUTED"]
    issue_code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]+$")]
    message: Annotated[str, Field(min_length=1)]
    related_anchor_ids: list[Annotated[str, Field(pattern=r"^anchor_[a-f0-9]{24}$")]] = Field(default_factory=list)


class SocialAnchorReviewerResponse(ContractModel):
    task_id: Annotated[str, Field(pattern=r"^anchor_task_[a-f0-9]{24}$")]
    task_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    judgment_id: Annotated[str, Field(pattern=r"^anchor_judgment_[a-f0-9]{24}$")]
    judgment_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    decision: Literal["APPROVED", "REJECTED", "DISPUTED"]
    issues: list[ReviewerIssueResponse]
    acknowledged_advisory_issue_codes: list[Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]+$")]]

    @model_validator(mode="after")
    def validate_decision(self) -> SocialAnchorReviewerResponse:
        issue_codes = [item.issue_code for item in self.issues]
        if len(issue_codes) != len(set(issue_codes)):
            raise ValueError("reviewer issue codes must be unique within one judgment")
        blocking = [item for item in self.issues if item.severity == "BLOCKING"]
        disputed = [item for item in self.issues if item.severity == "DISPUTED"]
        advisory_codes = {item.issue_code for item in self.issues if item.severity == "ADVISORY"}
        if set(self.acknowledged_advisory_issue_codes) != advisory_codes:
            raise ValueError("reviewer must explicitly acknowledge every advisory issue code")
        if self.decision == "APPROVED" and (blocking or disputed):
            raise ValueError("approved reviewer response cannot retain blocking or disputed issues")
        if self.decision == "REJECTED" and not blocking:
            raise ValueError("rejected reviewer response requires a blocking issue")
        if self.decision == "DISPUTED" and not disputed:
            raise ValueError("disputed reviewer response requires a disputed issue")
        return self


def _load_judgments(path: Path, behavior_id: BehaviorId) -> tuple[list[SocialAnchorJudgment], dict[str, str]]:
    payload = path.read_text(encoding="utf-8")
    judgments: list[SocialAnchorJudgment] = []
    hashes: dict[str, str] = {}
    for line in payload.splitlines():
        judgment = SocialAnchorJudgment.model_validate_json(line)
        if judgment.behavior_id is not behavior_id:
            raise ValueError("review batch judgment behavior differs from the requested batch")
        canonical = _canonical(judgment.model_dump(mode="json", by_alias=True, exclude_none=False))
        if line != canonical:
            raise ValueError(f"anchor judgment is not canonical JSON: {judgment.judgment_id}")
        judgments.append(judgment)
        hashes[judgment.judgment_id] = _sha256_bytes(line.encode("utf-8"))
    expected = 50 if behavior_id in {BehaviorId.APOLOGIZE, BehaviorId.CONFRONT} else 40
    if len(judgments) != expected or len(hashes) != expected:
        raise ValueError(f"review batch for {behavior_id.value} must contain exactly {expected} unique judgments")
    return judgments, hashes


def _load_reviewer_responses(path: Path) -> list[SocialAnchorReviewerResponse]:
    payload = path.read_text(encoding="utf-8")
    if not payload.endswith("\n") or "\n\n" in payload:
        raise ValueError("reviewer response JSONL must be newline-terminated without blank records")
    responses: list[SocialAnchorReviewerResponse] = []
    for line in payload.splitlines():
        raw: Any = json.loads(line)
        if not isinstance(raw, Mapping):
            raise TypeError("reviewer response must be an object")
        if line != _canonical(raw):
            raise ValueError("reviewer response must use canonical JSON")
        responses.append(SocialAnchorReviewerResponse.model_validate(raw))
    if len({item.judgment_id for item in responses}) != len(responses):
        raise ValueError("reviewer response judgment IDs must be unique")
    return responses


def assemble_review_batch(
    *,
    config_path: Path,
    coverage_policy_path: Path,
    tasks_path: Path,
    judgments_path: Path,
    responses_path: Path,
    output_root: Path,
    behavior_id: BehaviorId,
    reviewer_id: str,
    reviewed_at_utc: str,
    previous_approval_manifest_sha256: str | None = None,
) -> dict[str, object]:
    _ensure_external(output_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError("M4 anchor review output root must be absent or empty")
    artifact_root = output_root.parent.resolve()
    for path in (coverage_policy_path, tasks_path, judgments_path, responses_path):
        resolved = path.resolve()
        if resolved != artifact_root and artifact_root not in resolved.parents:
            raise ValueError("review inputs and output must share one external artifact root")
    policy = SocialAnchorCoveragePolicy.model_validate_json(coverage_policy_path.read_text(encoding="utf-8"))
    if policy != default_coverage_policy():
        raise ValueError("review batch coverage policy differs from ADR-0013")
    tasks, task_hashes = _load_tasks(tasks_path, behavior_id)
    judgments, judgment_hashes = _load_judgments(judgments_path, behavior_id)
    responses = _load_reviewer_responses(responses_path)
    tasks_by_id = {item.task_id: item for item in tasks}
    responses_by_id = {item.judgment_id: item for item in responses}
    if set(responses_by_id) != set(judgment_hashes):
        raise ValueError("reviewer responses must cover the exact immutable judgment batch")
    producer_ids = {item.producer_id for item in judgments}
    if len(producer_ids) != 1:
        raise ValueError("one review batch must reference exactly one producer identity")
    producer_id = next(iter(producer_ids))
    if producer_id == reviewer_id:
        raise ValueError("anchor producer and reviewer identities must differ")

    catalog = load_catalog(config_path)
    postprocessor = CatalogOutcomePostprocessor(catalog)
    behavior = next(item for item in catalog.behaviors.behaviors if item.behavior_id is behavior_id)
    reviewed_output_paths, heuristic_passthrough_output_paths = anchor_output_provenance_paths(behavior)
    issues: list[SocialAnchorReviewIssue] = []
    entries: list[SocialAnchorApprovalEntry] = []
    source_dataset_hashes: set[str] = set()
    for judgment in judgments:
        task = tasks_by_id.get(judgment.task_id)
        if task is None:
            raise ValueError(f"anchor judgment references a task outside the batch: {judgment.judgment_id}")
        response = responses_by_id[judgment.judgment_id]
        task_sha256 = task_hashes[task.task_id]
        judgment_sha256 = judgment_hashes[judgment.judgment_id]
        if response.task_id != task.task_id or response.task_sha256 != task_sha256:
            raise ValueError(f"reviewer task identity/hash mismatch: {judgment.judgment_id}")
        if response.judgment_sha256 != judgment_sha256:
            raise ValueError(f"reviewer judgment hash mismatch: {judgment.judgment_id}")
        if (
            judgment.task_sha256 != task_sha256
            or judgment.anchor_id != task.anchor_id
            or judgment.family_id != task.family_id
            or judgment.batch_id != task.batch_id
            or judgment.partition != task.partition
            or judgment.candidate_id != task.feature.candidate_id
            or judgment.reviewed_output_paths != reviewed_output_paths
            or judgment.heuristic_passthrough_output_paths != heuristic_passthrough_output_paths
        ):
            raise ValueError(f"judgment provenance differs from immutable task: {judgment.judgment_id}")
        normalized, violations = postprocessor.process(task.feature, judgment.proposed_prediction)
        if violations or normalized != judgment.proposed_prediction:
            raise ValueError(f"reviewed judgment is not directly catalog-safe: {judgment.judgment_id}")
        baseline_normalized, baseline_violations = postprocessor.process(
            task.feature, task.heuristic_baseline.prediction
        )
        if baseline_violations:
            raise RuntimeError(f"heuristic baseline is not contract-safe: {task.task_id} {baseline_violations}")
        if (
            judgment.proposed_prediction.need_delta_preview != baseline_normalized.need_delta_preview
            or judgment.proposed_prediction.event_probabilities != baseline_normalized.event_probabilities
        ):
            raise ValueError(f"judgment changed an ADR-0012 heuristic passthrough head: {judgment.judgment_id}")
        source_dataset_hashes.add(task.source_dataset_manifest_sha256)
        entry_issues: list[SocialAnchorReviewIssue] = []
        for issue_response in response.issues:
            issue_payload = {
                "task_sha256": task_sha256,
                "judgment_sha256": judgment_sha256,
                "reviewer_id": reviewer_id,
                **issue_response.model_dump(mode="json"),
            }
            issue_id = f"anchor_issue_{_sha256_bytes(_canonical(issue_payload).encode())[:24]}"
            issue = SocialAnchorReviewIssue(
                issue_id=issue_id,
                task_id=task.task_id,
                task_sha256=task_sha256,
                judgment_id=judgment.judgment_id,
                judgment_sha256=judgment_sha256,
                reviewer_id=reviewer_id,
                reviewed_at_utc=reviewed_at_utc,
                severity=issue_response.severity,
                issue_code=issue_response.issue_code,
                message=issue_response.message,
                related_anchor_ids=issue_response.related_anchor_ids,
            )
            issues.append(issue)
            entry_issues.append(issue)
        advisory = [item.issue_id for item in entry_issues if item.severity == "ADVISORY"]
        acknowledged_codes = set(response.acknowledged_advisory_issue_codes)
        acknowledged = [
            item.issue_id
            for item in entry_issues
            if item.severity == "ADVISORY" and item.issue_code in acknowledged_codes
        ]
        entries.append(
            SocialAnchorApprovalEntry(
                anchor_id=task.anchor_id,
                task_id=task.task_id,
                task_sha256=task_sha256,
                judgment_id=judgment.judgment_id,
                judgment_sha256=judgment_sha256,
                behavior_id=judgment.behavior_id,
                partition=judgment.partition,
                decision=response.decision,
                issue_ids=[item.issue_id for item in entry_issues],
                blocking_issue_ids=[item.issue_id for item in entry_issues if item.severity == "BLOCKING"],
                disputed_issue_ids=[item.issue_id for item in entry_issues if item.severity == "DISPUTED"],
                advisory_issue_ids=advisory,
                acknowledged_advisory_issue_ids=acknowledged,
            )
        )
    if len(source_dataset_hashes) != 1:
        raise ValueError("one review batch must reference exactly one source dataset manifest")

    output_root.mkdir(parents=True, exist_ok=True)
    issues_path = output_root / f"{behavior_id.value}-review-issues.jsonl"
    approval_path = output_root / f"{behavior_id.value}-draft-approval.json"
    report_path = output_root / f"{behavior_id.value}-review-report.json"
    issues_path.write_text(
        "".join(_canonical(item.model_dump(mode="json", by_alias=True, exclude_none=False)) + "\n" for item in issues),
        encoding="utf-8",
    )
    approval_identity = {
        "behavior_id": behavior_id.value,
        "reviewer_id": reviewer_id,
        "judgments_sha256": _sha256_file(judgments_path),
        "responses_sha256": _sha256_file(responses_path),
        "previous_approval_manifest_sha256": previous_approval_manifest_sha256,
    }
    approval = SocialAnchorApprovalManifest(
        approval_id=f"anchor_approval_{_sha256_bytes(_canonical(approval_identity).encode())[:24]}",
        status="DRAFT",
        created_at_utc=reviewed_at_utc,
        producer_id=producer_id,
        reviewer_id=reviewer_id,
        source_dataset_manifest_sha256=next(iter(source_dataset_hashes)),
        previous_approval_manifest_sha256=previous_approval_manifest_sha256,
        coverage_policy=_descriptor(coverage_policy_path, manifest_directory=output_root),
        tasks=_descriptor(tasks_path, manifest_directory=output_root),
        judgments=_descriptor(judgments_path, manifest_directory=output_root),
        issues=_descriptor(issues_path, manifest_directory=output_root),
        entries=entries,
    )
    approval_path.write_text(
        json.dumps(approval.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    decision_counts = Counter(item.decision for item in entries)
    severity_counts = Counter(item.severity for item in issues)
    report: dict[str, object] = {
        "schema": "stwm.model.social-anchor-review-report/v1",
        "project_name": "Small Town World Model（STWM）",
        "behavior_id": behavior_id.value,
        "producer_id": producer_id,
        "reviewer_id": reviewer_id,
        "reviewed_at_utc": reviewed_at_utc,
        "response_sha256": _sha256_file(responses_path),
        "issue_count": len(issues),
        "issue_counts": {
            "ADVISORY": severity_counts["ADVISORY"],
            "BLOCKING": severity_counts["BLOCKING"],
            "DISPUTED": severity_counts["DISPUTED"],
        },
        "decision_counts": {
            "APPROVED": decision_counts["APPROVED"],
            "REJECTED": decision_counts["REJECTED"],
            "DISPUTED": decision_counts["DISPUTED"],
        },
        "issues_sha256": _sha256_file(issues_path),
        "draft_approval_sha256": _sha256_file(approval_path),
        "approval_status": "DRAFT",
        "training_eligible": False,
        "passed": True,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble one independent M4 anchor review batch")
    parser.add_argument("--config", type=Path, default=Path("config/v0"))
    parser.add_argument("--coverage-policy", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--judgments", type=Path, required=True)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--behavior", type=BehaviorId, required=True, choices=list(BehaviorId))
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewed-at-utc", required=True)
    parser.add_argument("--previous-approval-manifest-sha256", default=None)
    arguments = parser.parse_args(argv)
    report = assemble_review_batch(
        config_path=arguments.config,
        coverage_policy_path=arguments.coverage_policy,
        tasks_path=arguments.tasks,
        judgments_path=arguments.judgments,
        responses_path=arguments.responses,
        output_root=arguments.output_root,
        behavior_id=arguments.behavior,
        reviewer_id=arguments.reviewer_id,
        reviewed_at_utc=arguments.reviewed_at_utc,
        previous_approval_manifest_sha256=arguments.previous_approval_manifest_sha256,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
