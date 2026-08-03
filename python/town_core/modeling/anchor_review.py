"""Assemble immutable Codex producer responses into M4 social-anchor judgments."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from town_core.catalogs import load_catalog
from town_core.domain.base import ContractModel
from town_core.domain.config_models import UnitValue
from town_core.domain.decision_models import OutcomePrediction
from town_core.domain.enums import BehaviorId, EventType, RelationshipDirection
from town_core.domain.state_models import MoodDelta, NeedDelta, RelationshipDelta
from town_core.modeling.anchors import REPOSITORY_ROOT, _canonical
from town_core.modeling.contracts import (
    SHA256_PATTERN,
    SocialAnchorJudgment,
    SocialAnchorTask,
    SocialAnchorTypedAssertion,
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


def _ensure_external(path: Path) -> None:
    repository = REPOSITORY_ROOT.resolve()
    resolved = path.resolve()
    if resolved == repository or repository in resolved.parents:
        raise ValueError("M4 anchor producer artifacts must remain outside the repository")


class ProducerAssertionResponse(ContractModel):
    assertion_type: Literal[
        "ACCEPTANCE_RATIONALE",
        "DELTA_RATIONALE",
        "DIRECTION",
        "EVENT_RATIONALE",
        "PERSONALITY_MONOTONICITY",
    ]
    statement: Annotated[str, Field(min_length=1)]
    paired_task_id: Annotated[str | None, Field(pattern=r"^anchor_task_[a-f0-9]{24}$")] = None
    paired_task_sha256: Annotated[str | None, Field(pattern=SHA256_PATTERN)] = None
    expected_order: Literal["LOWER", "EQUAL", "HIGHER"] | None = None


class SocialAnchorProducerResponse(ContractModel):
    task_id: Annotated[str, Field(pattern=r"^anchor_task_[a-f0-9]{24}$")]
    task_sha256: str = Field(pattern=SHA256_PATTERN)
    need_delta_preview: NeedDelta
    actor_mood_delta: MoodDelta
    target_mood_delta: MoodDelta | None
    relationship_delta_target_to_actor: RelationshipDelta | None
    acceptance_probability: UnitValue | None
    event_probabilities: dict[EventType, UnitValue]
    rationale_tags: list[str] = Field(min_length=1)
    typed_assertions: list[ProducerAssertionResponse] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def flatten_proposed_soft_values(cls, value: Any) -> Any:
        if not isinstance(value, Mapping) or "proposed_soft_values" not in value:
            return value
        flattened = dict(value)
        proposed = flattened.pop("proposed_soft_values")
        if not isinstance(proposed, Mapping):
            raise TypeError("proposed_soft_values must be an object")
        proposed_values = dict(proposed)
        direction = proposed_values.pop("relationship_direction", "TARGET_TO_ACTOR")
        if direction != "TARGET_TO_ACTOR":
            raise ValueError("producer relationship direction must remain Target-to-Actor")
        if set(flattened) & set(proposed_values):
            raise ValueError("producer response cannot duplicate proposed soft fields")
        flattened.update(proposed_values)
        return flattened

    @model_validator(mode="after")
    def validate_response(self) -> SocialAnchorProducerResponse:
        if len(self.rationale_tags) != len(set(self.rationale_tags)):
            raise ValueError("producer response rationale tags must be unique")
        if not any(item.assertion_type == "DIRECTION" for item in self.typed_assertions):
            raise ValueError("producer response requires an explicit Target-to-Actor direction assertion")
        numeric_values = [
            *self.need_delta_preview.model_dump().values(),
            *self.actor_mood_delta.model_dump().values(),
            *(self.target_mood_delta.model_dump().values() if self.target_mood_delta else []),
            *(
                self.relationship_delta_target_to_actor.model_dump().values()
                if self.relationship_delta_target_to_actor
                else []
            ),
            *(self.event_probabilities.values()),
        ]
        if self.acceptance_probability is not None:
            numeric_values.append(self.acceptance_probability)
        if any(not math.isfinite(float(value)) for value in numeric_values):
            raise ValueError("producer response values must be finite")
        return self


def _load_tasks(path: Path, behavior_id: BehaviorId) -> tuple[list[SocialAnchorTask], dict[str, str]]:
    payload = path.read_text(encoding="utf-8")
    tasks: list[SocialAnchorTask] = []
    hashes: dict[str, str] = {}
    for line in payload.splitlines():
        task = SocialAnchorTask.model_validate_json(line)
        if task.behavior_id is not behavior_id:
            continue
        canonical = _canonical(task.model_dump(mode="json", by_alias=True, exclude_none=False))
        if line != canonical:
            raise ValueError(f"anchor task is not canonical JSON: {task.task_id}")
        tasks.append(task)
        hashes[task.task_id] = _sha256_bytes(line.encode("utf-8"))
    expected = 50 if behavior_id in {BehaviorId.APOLOGIZE, BehaviorId.CONFRONT} else 40
    if len(tasks) != expected or len(hashes) != expected:
        raise ValueError(f"producer batch for {behavior_id.value} must contain exactly {expected} unique tasks")
    return tasks, hashes


def _load_responses(path: Path) -> list[SocialAnchorProducerResponse]:
    payload = path.read_text(encoding="utf-8")
    if not payload.endswith("\n") or "\n\n" in payload:
        raise ValueError("producer response JSONL must be newline-terminated without blank records")
    responses: list[SocialAnchorProducerResponse] = []
    for line in payload.splitlines():
        raw = json.loads(line)
        response = SocialAnchorProducerResponse.model_validate(raw)
        canonical = _canonical(raw)
        if line != canonical:
            raise ValueError(f"producer response is not canonical JSON: {response.task_id}")
        responses.append(response)
    if len({item.task_id for item in responses}) != len(responses):
        raise ValueError("producer response task IDs must be unique")
    return responses


def _typed_assertions(
    response: SocialAnchorProducerResponse,
    *,
    task_sha256: str,
) -> list[SocialAnchorTypedAssertion]:
    assertions: list[SocialAnchorTypedAssertion] = []
    for index, draft in enumerate(response.typed_assertions):
        assertion_digest = _sha256_bytes(f"{task_sha256}:{index}:{_canonical(draft.model_dump())}".encode())[:16]
        assertions.append(
            SocialAnchorTypedAssertion.model_validate(
                {
                    "assertion_id": f"assertion_{assertion_digest}",
                    **draft.model_dump(exclude_none=False),
                }
            )
        )
    return assertions


def assemble_producer_judgments(
    *,
    config_path: Path,
    tasks_path: Path,
    responses_path: Path,
    output_root: Path,
    behavior_id: BehaviorId,
    producer_id: str,
    produced_at_utc: str,
) -> dict[str, object]:
    _ensure_external(output_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError("M4 anchor judgment output root must be absent or empty")
    tasks, task_hashes = _load_tasks(tasks_path, behavior_id)
    responses = _load_responses(responses_path)
    response_by_task = {item.task_id: item for item in responses}
    if set(response_by_task) != set(task_hashes):
        raise ValueError("producer responses must cover the exact immutable behavior batch")

    catalog = load_catalog(config_path)
    postprocessor = CatalogOutcomePostprocessor(catalog)
    judgments: list[SocialAnchorJudgment] = []
    changed_count = 0
    for task in tasks:
        response = response_by_task[task.task_id]
        task_sha256 = task_hashes[task.task_id]
        if response.task_sha256 != task_sha256:
            raise ValueError(f"producer response task hash mismatch: {task.task_id}")
        baseline = task.heuristic_baseline.prediction
        proposed = OutcomePrediction(
            prediction_id=baseline.prediction_id,
            candidate_id=baseline.candidate_id,
            need_delta_preview=response.need_delta_preview,
            actor_mood_delta=response.actor_mood_delta,
            target_mood_delta=response.target_mood_delta,
            relationship_direction=RelationshipDirection.TARGET_TO_ACTOR,
            relationship_delta_target_to_actor=response.relationship_delta_target_to_actor,
            acceptance_probability=response.acceptance_probability,
            event_probabilities=response.event_probabilities,
        )
        normalized, violations = postprocessor.process(task.feature, proposed)
        if violations:
            raise ValueError(f"producer response depends on forbidden mask/bounds repair: {task.task_id} {violations}")
        baseline_normalized, baseline_violations = postprocessor.process(task.feature, baseline)
        if baseline_violations:
            raise RuntimeError(f"heuristic baseline is not contract-safe: {task.task_id} {baseline_violations}")
        if normalized != baseline_normalized:
            changed_count += 1
        assertions = _typed_assertions(response, task_sha256=task_sha256)
        identity_payload = {
            "task_sha256": task_sha256,
            "producer_id": producer_id,
            "proposed_prediction": normalized.model_dump(mode="json"),
            "rationale_tags": response.rationale_tags,
            "typed_assertions": [item.model_dump(mode="json") for item in assertions],
        }
        judgment_digest = _sha256_bytes(_canonical(identity_payload).encode())[:24]
        judgments.append(
            SocialAnchorJudgment(
                judgment_id=f"anchor_judgment_{judgment_digest}",
                task_id=task.task_id,
                task_sha256=task_sha256,
                anchor_id=task.anchor_id,
                family_id=task.family_id,
                batch_id=task.batch_id,
                behavior_id=task.behavior_id,
                partition=task.partition,
                candidate_id=task.feature.candidate_id,
                producer_id=producer_id,
                produced_at_utc=produced_at_utc,
                proposed_prediction=normalized,
                rationale_tags=response.rationale_tags,
                typed_assertions=assertions,
            )
        )

    output_root.mkdir(parents=True, exist_ok=True)
    judgments_path = output_root / f"{behavior_id.value}-judgments.jsonl"
    report_path = output_root / f"{behavior_id.value}-producer-report.json"
    judgments_path.write_text(
        "".join(
            _canonical(item.model_dump(mode="json", by_alias=True, exclude_none=False)) + "\n" for item in judgments
        ),
        encoding="utf-8",
    )
    partition_counts = Counter(item.partition for item in judgments)
    report: dict[str, object] = {
        "schema": "stwm.model.social-anchor-producer-report/v1",
        "project_name": "Small Town World Model（STWM）",
        "behavior_id": behavior_id.value,
        "producer_id": producer_id,
        "produced_at_utc": produced_at_utc,
        "response_sha256": _sha256_file(responses_path),
        "judgments_relative_path": judgments_path.name,
        "judgments_sha256": _sha256_file(judgments_path),
        "judgment_count": len(judgments),
        "changed_from_heuristic_count": changed_count,
        "retained_heuristic_count": len(judgments) - changed_count,
        "partition_counts": {
            "TRAIN": partition_counts["TRAIN"],
            "VALIDATION": partition_counts["VALIDATION"],
            "ANCHOR_HOLDOUT": partition_counts["ANCHOR_HOLDOUT"],
        },
        "passed": True,
        "approval_claimed": False,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble one immutable M4 Codex anchor-judgment batch")
    parser.add_argument("--config", type=Path, default=Path("config/v0"))
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--behavior", type=BehaviorId, required=True, choices=list(BehaviorId))
    parser.add_argument("--producer-id", required=True)
    parser.add_argument("--produced-at-utc", required=True)
    arguments = parser.parse_args(argv)
    report = assemble_producer_judgments(
        config_path=arguments.config,
        tasks_path=arguments.tasks,
        responses_path=arguments.responses,
        output_root=arguments.output_root,
        behavior_id=arguments.behavior,
        producer_id=arguments.producer_id,
        produced_at_utc=arguments.produced_at_utc,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
