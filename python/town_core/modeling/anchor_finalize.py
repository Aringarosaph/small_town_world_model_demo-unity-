"""Finalize seven reviewed M4 anchor batches without exposing holdout labels to fitting."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from town_core.domain.enums import BehaviorId
from town_core.modeling.anchor_approval import _load_judgments, _load_reviewer_responses
from town_core.modeling.anchor_review import _load_tasks
from town_core.modeling.anchors import REPOSITORY_ROOT, _canonical, default_coverage_policy
from town_core.modeling.contracts import (
    REVIEWED_SOCIAL_BEHAVIORS,
    ArtifactDescriptor,
    DatasetManifest,
    HeuristicPassthroughOutputPath,
    SocialAnchorApprovalEntry,
    SocialAnchorApprovalManifest,
    SocialAnchorReviewedBatchSource,
    SocialAnchorReviewIssue,
    SocialAnchorTrainingInputManifest,
)

BEHAVIOR_ORDER = (
    BehaviorId.GREET,
    BehaviorId.CHAT,
    BehaviorId.JOKE,
    BehaviorId.COMPLIMENT,
    BehaviorId.INVITE_JOIN,
    BehaviorId.APOLOGIZE,
    BehaviorId.CONFRONT,
)
PASSTHROUGH_PATHS: list[HeuristicPassthroughOutputPath] = [
    "need_delta_preview.hunger",
    "need_delta_preview.energy",
    "need_delta_preview.hygiene",
    "need_delta_preview.fun",
    "need_delta_preview.social",
    "event_probabilities",
]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _descriptor(path: Path, *, manifest_directory: Path) -> ArtifactDescriptor:
    return ArtifactDescriptor(
        relative_path=Path(os.path.relpath(path.resolve(), start=manifest_directory.resolve())).as_posix(),
        sha256=_sha256_file(path),
        bytes=path.stat().st_size,
    )


def _ensure_external(path: Path) -> None:
    repository = REPOSITORY_ROOT.resolve()
    resolved = path.resolve()
    if resolved == repository or repository in resolved.parents:
        raise ValueError("M4 final anchor artifacts must remain outside the repository")


def _load_object(path: Path) -> dict[str, Any]:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise TypeError(f"artifact must be a JSON object: {path}")
    return dict(value)


def _resolve_packaged_artifact(batch_root: Path, value: Any) -> Path:
    descriptor = ArtifactDescriptor.model_validate(value)
    path = (batch_root / descriptor.relative_path).resolve()
    root = batch_root.resolve()
    if path != root and root not in path.parents:
        raise ValueError("reviewed batch artifact escapes its package root")
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size != descriptor.bytes or _sha256_file(path) != descriptor.sha256:
        raise ValueError(f"reviewed batch artifact descriptor mismatch: {path}")
    return path


def _load_canonical_issues(path: Path) -> tuple[list[SocialAnchorReviewIssue], dict[str, str]]:
    issues: list[SocialAnchorReviewIssue] = []
    hashes: dict[str, str] = {}
    payload = path.read_text(encoding="utf-8")
    if payload and (not payload.endswith("\n") or "\n\n" in payload):
        raise ValueError("review issue JSONL must be canonical and newline terminated")
    for line in payload.splitlines():
        issue = SocialAnchorReviewIssue.model_validate_json(line)
        if line != _canonical(issue.model_dump(mode="json", by_alias=True, exclude_none=False)):
            raise ValueError(f"review issue is not canonical: {issue.issue_id}")
        issues.append(issue)
        hashes[issue.issue_id] = hashlib.sha256(line.encode()).hexdigest()
    if len(issues) != len(hashes):
        raise ValueError("review issue IDs must be unique")
    return issues, hashes


def _verify_entry_issues(entry: SocialAnchorApprovalEntry, issue_by_id: Mapping[str, SocialAnchorReviewIssue]) -> None:
    selected = [issue_by_id[item] for item in entry.issue_ids]
    if any(item.task_id != entry.task_id or item.judgment_id != entry.judgment_id for item in selected):
        raise ValueError(f"review issue provenance differs from approval entry: {entry.anchor_id}")
    expected_blocking = {item.issue_id for item in selected if item.severity == "BLOCKING"}
    expected_disputed = {item.issue_id for item in selected if item.severity == "DISPUTED"}
    expected_advisory = {item.issue_id for item in selected if item.severity == "ADVISORY"}
    if (
        set(entry.blocking_issue_ids) != expected_blocking
        or set(entry.disputed_issue_ids) != expected_disputed
        or set(entry.advisory_issue_ids) != expected_advisory
    ):
        raise ValueError(f"review issue severity classification drifted: {entry.anchor_id}")


def finalize_reviewed_anchors(
    *,
    source_commit: str,
    created_at_utc: str,
    raw_dataset_manifest_path: Path,
    coverage_policy_path: Path,
    tasks_path: Path,
    batch_roots: Sequence[Path],
    output_root: Path,
) -> dict[str, object]:
    _ensure_external(output_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError("M4 final anchor output root must be absent or empty")
    for path in (raw_dataset_manifest_path, coverage_policy_path, tasks_path, *batch_roots):
        _ensure_external(path)

    raw_dataset = DatasetManifest.model_validate_json(raw_dataset_manifest_path.read_text(encoding="utf-8"))
    if raw_dataset.status != "COMPLETED":
        raise ValueError("final anchor approval requires a completed raw dataset manifest")
    if default_coverage_policy().model_dump(mode="json", by_alias=True) != json.loads(
        coverage_policy_path.read_text(encoding="utf-8")
    ):
        raise ValueError("final anchor coverage policy differs from ADR-0013")
    all_tasks: dict[str, Any] = {}
    task_hashes: dict[str, str] = {}
    task_order: dict[str, int] = {}
    for behavior in BEHAVIOR_ORDER:
        behavior_tasks, behavior_hashes = _load_tasks(tasks_path, behavior)
        for task in behavior_tasks:
            all_tasks[task.task_id] = task
            task_hashes[task.task_id] = behavior_hashes[task.task_id]
    for index, line in enumerate(tasks_path.read_text(encoding="utf-8").splitlines()):
        task_id = str(json.loads(line)["task_id"])
        task_order[task_id] = index
    if len(all_tasks) != 300:
        raise ValueError("final anchor task packet must contain exactly 300 unique tasks")

    batch_by_behavior: dict[BehaviorId, tuple[Path, dict[str, Any]]] = {}
    batch_sources: list[SocialAnchorReviewedBatchSource] = []
    all_entries: list[SocialAnchorApprovalEntry] = []
    all_judgments: list[Any] = []
    all_issues: list[SocialAnchorReviewIssue] = []
    producer_ids: set[str] = set()
    reviewer_ids: set[str] = set()
    for batch_root in batch_roots:
        manifest_path = batch_root / "batch-manifest.json"
        batch = _load_object(manifest_path)
        if batch.get("schema") != "stwm.model.social-anchor-reviewed-batch/v1":
            raise ValueError("unexpected reviewed batch schema")
        if batch.get("status") != "REVIEWED_BATCH_DRAFT_FOR_FINAL_300" or batch.get("training_eligible") is not False:
            raise ValueError("behavior-local batch must remain a non-training DRAFT")
        behavior = BehaviorId(str(batch.get("behavior_id")))
        if behavior not in REVIEWED_SOCIAL_BEHAVIORS or behavior in batch_by_behavior:
            raise ValueError("final anchor inputs require one unique batch per reviewed behavior")
        batch_by_behavior[behavior] = (batch_root, batch)
        counts = batch.get("counts")
        if not isinstance(counts, Mapping) or counts.get("APPROVED") != counts.get("total"):
            raise ValueError(f"reviewed batch is not fully approved: {behavior.value}")
        if counts.get("REJECTED") != 0 or counts.get("DISPUTED") != 0:
            raise ValueError(f"reviewed batch retains rejected or disputed entries: {behavior.value}")
        inputs = batch.get("inputs")
        if not isinstance(inputs, Mapping):
            raise TypeError("reviewed batch inputs must be an object")
        expected_shared = {
            "tasks": (_sha256_file(tasks_path), tasks_path.stat().st_size),
            "coverage_policy": (_sha256_file(coverage_policy_path), coverage_policy_path.stat().st_size),
        }
        for name, (expected_hash, expected_bytes) in expected_shared.items():
            descriptor = ArtifactDescriptor.model_validate(inputs.get(name))
            if (descriptor.sha256, descriptor.bytes) != (expected_hash, expected_bytes):
                raise ValueError(f"reviewed batch {name} differs from the immutable shared input")
        artifacts = batch.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise TypeError("reviewed batch artifacts must be an object")
        resolved = {name: _resolve_packaged_artifact(batch_root, value) for name, value in artifacts.items()}
        required = {
            "producer_responses",
            "producer_report",
            "judgments",
            "reviewer_responses",
            "review_issues",
            "draft_approval",
            "review_report",
        }
        if set(resolved) != required:
            raise ValueError("reviewed batch artifact set is not exact")
        approval = SocialAnchorApprovalManifest.model_validate_json(
            resolved["draft_approval"].read_text(encoding="utf-8")
        )
        if approval.status != "DRAFT" or len(approval.entries) != counts.get("total"):
            raise ValueError("reviewed batch draft approval count/status mismatch")
        if approval.source_dataset_manifest_sha256 != _sha256_file(raw_dataset_manifest_path):
            raise ValueError("reviewed batch source dataset differs from the supplied raw dataset manifest")
        if (
            approval.coverage_policy.sha256 != expected_shared["coverage_policy"][0]
            or approval.tasks.sha256 != expected_shared["tasks"][0]
            or approval.judgments.sha256 != _sha256_file(resolved["judgments"])
            or approval.issues.sha256 != _sha256_file(resolved["review_issues"])
        ):
            raise ValueError("draft approval descriptor differs from its reviewed batch package")
        producer_ids.add(approval.producer_id)
        reviewer_ids.add(approval.reviewer_id)
        judgments, judgment_hashes = _load_judgments(resolved["judgments"], behavior)
        reviewer_responses = _load_reviewer_responses(resolved["reviewer_responses"])
        issues, _ = _load_canonical_issues(resolved["review_issues"])
        issue_by_id = {item.issue_id: item for item in issues}
        judgment_by_id = {item.judgment_id: item for item in judgments}
        response_by_id = {item.judgment_id: item for item in reviewer_responses}
        producer_report = _load_object(resolved["producer_report"])
        review_report = _load_object(resolved["review_report"])
        if (
            producer_report.get("passed") is not True
            or producer_report.get("approval_claimed") is not False
            or producer_report.get("behavior_id") != behavior.value
            or producer_report.get("response_sha256") != _sha256_file(resolved["producer_responses"])
            or producer_report.get("judgments_sha256") != _sha256_file(resolved["judgments"])
        ):
            raise ValueError("producer report does not prove the packaged judgment batch")
        if (
            review_report.get("passed") is not True
            or review_report.get("training_eligible") is not False
            or review_report.get("approval_status") != "DRAFT"
            or review_report.get("behavior_id") != behavior.value
            or review_report.get("response_sha256") != _sha256_file(resolved["reviewer_responses"])
            or review_report.get("issues_sha256") != _sha256_file(resolved["review_issues"])
            or review_report.get("draft_approval_sha256") != _sha256_file(resolved["draft_approval"])
        ):
            raise ValueError("review report does not prove the packaged draft approval")
        if set(response_by_id) != set(judgment_by_id):
            raise ValueError("reviewer responses do not cover the exact packaged judgment set")
        for entry in approval.entries:
            if entry.behavior_id is not behavior or entry.decision != "APPROVED":
                raise ValueError("final anchor input contains a non-approved or cross-behavior entry")
            judgment = judgment_by_id.get(entry.judgment_id)
            if judgment is None or judgment_hashes[entry.judgment_id] != entry.judgment_sha256:
                raise ValueError("approval entry judgment identity/hash mismatch")
            approval_task = all_tasks.get(entry.task_id)
            if (
                approval_task is None
                or approval_task.anchor_id != entry.anchor_id
                or approval_task.partition != entry.partition
                or task_hashes[entry.task_id] != entry.task_sha256
            ):
                raise ValueError("approval entry differs from the immutable task packet")
            if not set(entry.issue_ids) <= set(issue_by_id):
                raise ValueError("approval entry references an issue outside its batch")
            _verify_entry_issues(entry, issue_by_id)
            response = response_by_id[entry.judgment_id]
            if (
                response.task_id != entry.task_id
                or response.task_sha256 != entry.task_sha256
                or response.judgment_sha256 != entry.judgment_sha256
                or response.decision != entry.decision
                or len(response.issues) != len(entry.issue_ids)
            ):
                raise ValueError("reviewer response differs from its approval entry")
            response_issues = {item.issue_code: item for item in response.issues}
            for issue_id in entry.issue_ids:
                issue = issue_by_id[issue_id]
                source = response_issues.get(issue.issue_code)
                if source is None or (
                    issue.severity,
                    issue.message,
                    issue.related_anchor_ids,
                    issue.reviewer_id,
                ) != (source.severity, source.message, source.related_anchor_ids, approval.reviewer_id):
                    raise ValueError("review issue differs from the immutable reviewer response")
        all_entries.extend(approval.entries)
        all_judgments.extend(judgments)
        all_issues.extend(issues)
        batch_sources.append(
            SocialAnchorReviewedBatchSource(
                behavior_id=behavior,
                batch_manifest=_descriptor(manifest_path, manifest_directory=output_root),
                draft_approval=_descriptor(resolved["draft_approval"], manifest_directory=output_root),
            )
        )

    if set(batch_by_behavior) != set(BEHAVIOR_ORDER) or len(producer_ids) != 1 or len(reviewer_ids) != 1:
        raise ValueError("final anchor sources must cover seven behaviors with one producer/reviewer pair")
    if (len(all_entries), len(all_judgments)) != (300, 300):
        raise ValueError("final anchor aggregate must contain exactly 300 entries and judgments")
    if len({item.task_id for item in all_entries}) != 300 or len({item.judgment_id for item in all_entries}) != 300:
        raise ValueError("final anchor aggregate contains duplicate task or judgment identities")
    if len({item.issue_id for item in all_issues}) != len(all_issues):
        raise ValueError("final anchor aggregate contains duplicate issue identities")

    all_entries.sort(key=lambda item: task_order[item.task_id])
    all_judgments.sort(key=lambda item: task_order[item.task_id])
    all_issues.sort(key=lambda item: (task_order[item.task_id], item.issue_id))
    batch_sources.sort(key=lambda item: BEHAVIOR_ORDER.index(item.behavior_id))
    partition_counts = Counter(item.partition for item in all_entries)
    if partition_counts != {"TRAIN": 210, "VALIDATION": 30, "ANCHOR_HOLDOUT": 60}:
        raise ValueError("final anchor aggregate partition counts differ from ADR-0013")

    output_root.mkdir(parents=True, exist_ok=True)
    judgments_path = output_root / "approved-judgments.jsonl"
    issues_path = output_root / "review-issues.jsonl"
    fit_path = output_root / "fit-judgments.jsonl"
    approval_path = output_root / "final-anchor-approval.json"
    training_path = output_root / "training-input-manifest.json"
    judgments_path.write_text(
        "".join(
            _canonical(item.model_dump(mode="json", by_alias=True, exclude_none=False)) + "\n" for item in all_judgments
        ),
        encoding="utf-8",
    )
    issues_path.write_text(
        "".join(
            _canonical(item.model_dump(mode="json", by_alias=True, exclude_none=False)) + "\n" for item in all_issues
        ),
        encoding="utf-8",
    )
    fit_judgments = [item for item in all_judgments if item.partition != "ANCHOR_HOLDOUT"]
    fit_path.write_text(
        "".join(
            _canonical(item.model_dump(mode="json", by_alias=True, exclude_none=False)) + "\n" for item in fit_judgments
        ),
        encoding="utf-8",
    )
    identity = {
        "source_commit": source_commit,
        "created_at_utc": created_at_utc,
        "dataset": _sha256_file(raw_dataset_manifest_path),
        "tasks": _sha256_file(tasks_path),
        "judgments": _sha256_file(judgments_path),
        "issues": _sha256_file(issues_path),
        "source_batches": [item.batch_manifest.sha256 for item in batch_sources],
    }
    approval_id = f"anchor_approval_{hashlib.sha256(_canonical(identity).encode()).hexdigest()[:24]}"
    final_approval = SocialAnchorApprovalManifest(
        approval_id=approval_id,
        status="FINAL",
        created_at_utc=created_at_utc,
        producer_id=next(iter(producer_ids)),
        reviewer_id=next(iter(reviewer_ids)),
        source_dataset_manifest_sha256=_sha256_file(raw_dataset_manifest_path),
        coverage_policy=_descriptor(coverage_policy_path, manifest_directory=output_root),
        tasks=_descriptor(tasks_path, manifest_directory=output_root),
        judgments=_descriptor(judgments_path, manifest_directory=output_root),
        issues=_descriptor(issues_path, manifest_directory=output_root),
        entries=all_entries,
    )
    approval_path.write_text(
        json.dumps(final_approval.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    training_manifest = SocialAnchorTrainingInputManifest(
        source_commit=source_commit,
        created_at_utc=created_at_utc,
        source_dataset_manifest_sha256=_sha256_file(raw_dataset_manifest_path),
        raw_dataset_manifest=_descriptor(raw_dataset_manifest_path, manifest_directory=output_root),
        coverage_policy=_descriptor(coverage_policy_path, manifest_directory=output_root),
        tasks=_descriptor(tasks_path, manifest_directory=output_root),
        final_anchor_approval=_descriptor(approval_path, manifest_directory=output_root),
        fit_judgments=_descriptor(fit_path, manifest_directory=output_root),
        source_batches=batch_sources,
        heuristic_passthrough_output_paths=PASSTHROUGH_PATHS,
    )
    training_path.write_text(
        json.dumps(
            training_manifest.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "schema": "stwm.model.social-anchor-finalization-report/v1",
        "approval_id": approval_id,
        "approved_count": len(all_entries),
        "fit_count": len(fit_judgments),
        "excluded_anchor_holdout_count": partition_counts["ANCHOR_HOLDOUT"],
        "final_anchor_approval_sha256": _sha256_file(approval_path),
        "training_input_manifest_sha256": _sha256_file(training_path),
        "fit_judgments_sha256": _sha256_file(fit_path),
        "training_eligible": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize seven independently reviewed M4 social-anchor batches")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--created-at-utc", required=True)
    parser.add_argument("--raw-dataset-manifest", type=Path, required=True)
    parser.add_argument("--coverage-policy", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--batch-root", type=Path, action="append", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args(argv)
    report = finalize_reviewed_anchors(
        source_commit=arguments.source_commit,
        created_at_utc=arguments.created_at_utc,
        raw_dataset_manifest_path=arguments.raw_dataset_manifest,
        coverage_policy_path=arguments.coverage_policy,
        tasks_path=arguments.tasks,
        batch_roots=arguments.batch_root,
        output_root=arguments.output_root,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
