"""External, deterministic, sharded M4 rule-teacher dataset producer."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from town_core.catalogs import load_catalog, load_m3_catalogs, m3_catalog_hash
from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import BehaviorId
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.domain.state_models import KnowledgeRecord, WorldEvent, WorldState
from town_core.modeling.contracts import DatasetManifest, DatasetShard, TrainingExample
from town_core.modeling.features import CandidateFeatureEncoder, feature_vocabulary
from town_core.modeling.providers import HeuristicOutcomeModel
from town_core.society.engine import SocietyEngine
from town_core.society.initialization import build_initial_society_checkpoint
from town_core.society.models import ConversationRecord

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ROWS_PER_SHARD = 10_000


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _atomic_json(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _repository_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _ensure_external(path: Path) -> None:
    repository = REPOSITORY_ROOT.resolve()
    resolved = path.resolve()
    if resolved == repository or repository in resolved.parents:
        raise ValueError("M4 generated dataset output must remain outside the repository")


class ParquetShardWriter:
    """Write canonical training examples in bounded, checksum-addressed Parquet shards."""

    def __init__(self, root: Path, *, rows_per_shard: int) -> None:
        if not 0 < rows_per_shard <= 25_000:
            raise ValueError("M4 rows_per_shard must be in 1..25000")
        self.root = root
        self.rows_per_shard = rows_per_shard
        self.shards_path = root / "shards"
        self.shards_path.mkdir(parents=True)
        self.descriptors: list[DatasetShard] = []

    def write(self, groups: Sequence[Sequence[TrainingExample]]) -> DatasetShard:
        rows = [row for group in groups for row in group]
        if not rows or len(rows) > self.rows_per_shard:
            raise ValueError("M4 shard must contain 1..rows_per_shard complete-group rows")
        try:
            pa = importlib.import_module("pyarrow")
            pq = importlib.import_module("pyarrow.parquet")
        except ImportError as exc:
            raise RuntimeError("M4 Parquet generation requires the optional pyarrow dependency") from exc
        shard_id = f"shard_{len(self.descriptors):05d}"
        destination = self.shards_path / f"{shard_id}.parquet"
        temporary = destination.with_name(f".{destination.name}.tmp")
        records = [
            {
                "row_id": row.feature.row_id,
                "decision_group_id": row.feature.decision_group_id,
                "scenario_group_id": row.feature.scenario_group_id,
                "split": row.feature.split,
                "behavior_id": row.feature.raw_candidate.behavior_id.value,
                "selected_by_teacher": row.label.selected_by_teacher,
                "example_json": _canonical(row.model_dump(mode="json", exclude_none=False, by_alias=True)),
            }
            for row in rows
        ]
        table = cast(Any, pa).Table.from_pylist(records)
        cast(Any, pq).write_table(
            table,
            temporary,
            compression="zstd",
            use_dictionary=True,
            write_statistics=True,
        )
        temporary.replace(destination)
        split_counts: Counter[str] = Counter(row.feature.split for row in rows)
        descriptor = DatasetShard(
            shard_id=shard_id,
            relative_path=destination.relative_to(self.root).as_posix(),
            sha256=_sha256(destination),
            bytes=destination.stat().st_size,
            row_count=len(rows),
            decision_group_count=len(groups),
            split_counts={
                "train": split_counts["train"],
                "validation": split_counts["validation"],
                "test": split_counts["test"],
            },
        )
        self.descriptors.append(descriptor)
        return descriptor


class DecisionDatasetCollector:
    def __init__(
        self,
        catalog: CatalogBundle,
        m3_catalogs: M3Catalogs,
        *,
        source_commit: str,
        seed: int,
        maximum_rows: int,
        writer: ParquetShardWriter,
    ) -> None:
        self.encoder = CandidateFeatureEncoder(catalog, m3_catalogs, source_commit=source_commit)
        self.heuristic = HeuristicOutcomeModel(catalog)
        self.seed = seed
        self.maximum_rows = maximum_rows
        self.writer = writer
        self.pending_groups: list[list[TrainingExample]] = []
        self.pending_rows = 0
        self.written_rows = 0
        self.decision_group_count = 0
        self.split_counts: Counter[str] = Counter()
        self.behavior_counts: Counter[BehaviorId] = Counter()
        self._limit_reached = False

    @property
    def observed_rows(self) -> int:
        return self.written_rows + self.pending_rows

    @property
    def limit_reached(self) -> bool:
        return self._limit_reached or self.observed_rows >= self.maximum_rows

    def record_decision(
        self,
        *,
        source_state: WorldState,
        decision: Mapping[str, object],
        events: Mapping[str, WorldEvent],
        knowledge_records: Mapping[str, KnowledgeRecord],
        conversations: Mapping[str, ConversationRecord],
        recent_behavior: BehaviorId | None,
    ) -> None:
        if self.limit_reached:
            return
        group = self.encoder.encode_decision(
            seed=self.seed,
            state=source_state,
            decision=decision,
            events=events,
            knowledge_records=knowledge_records,
            conversations=conversations,
            recent_behavior=recent_behavior,
        )
        if not group:
            raise ValueError("M4 decision observer received an empty candidate group")
        if self.observed_rows and self.observed_rows + len(group) > self.maximum_rows:
            self._limit_reached = True
            return
        reproduced = self.heuristic.predict_batch([item.feature for item in group])
        for item, predicted in zip(group, reproduced, strict=True):
            teacher = item.label.prediction
            if predicted.model_copy(update={"prediction_id": teacher.prediction_id}) != teacher:
                raise RuntimeError(f"M4 heuristic feature adapter diverged for {item.feature.row_id}")
        self.pending_groups.append(group)
        self.pending_rows += len(group)
        self.decision_group_count += 1
        for item in group:
            self.split_counts[item.feature.split] += 1
            self.behavior_counts[item.feature.raw_candidate.behavior_id] += 1
        if self.observed_rows >= self.maximum_rows:
            self._limit_reached = True

    def flush_ready(self, *, final: bool = False) -> list[DatasetShard]:
        written: list[DatasetShard] = []
        while self.pending_groups:
            selected: list[list[TrainingExample]] = []
            selected_rows = 0
            for group in self.pending_groups:
                if selected and selected_rows + len(group) > self.writer.rows_per_shard:
                    break
                if len(group) > self.writer.rows_per_shard:
                    raise ValueError("one M4 decision group exceeds the frozen shard row limit")
                selected.append(group)
                selected_rows += len(group)
            consumes_all = len(selected) == len(self.pending_groups)
            if consumes_all and not final and selected_rows < self.writer.rows_per_shard:
                break
            descriptor = self.writer.write(selected)
            written.append(descriptor)
            del self.pending_groups[: len(selected)]
            self.pending_rows -= selected_rows
            self.written_rows += selected_rows
        return written


def _manifest(
    *,
    dataset_id: str,
    status: Literal["IN_PROGRESS", "COMPLETED", "FAILED"],
    source_commit: str,
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    collector: DecisionDatasetCollector,
    started_at_utc: str,
    failure: str | None = None,
) -> DatasetManifest:
    return DatasetManifest(
        dataset_id=dataset_id,
        status=status,
        source_commit=source_commit,
        config_hash=collector_state_config_hash(catalog),
        m3_catalog_hash=m3_catalog_hash(m3_catalogs),
        seeds=[collector.seed],
        max_rows_per_shard=collector.writer.rows_per_shard,
        decision_group_count=collector.decision_group_count,
        row_count=collector.observed_rows,
        split_counts={
            "train": collector.split_counts["train"],
            "validation": collector.split_counts["validation"],
            "test": collector.split_counts["test"],
        },
        behavior_counts={behavior: collector.behavior_counts[behavior] for behavior in BehaviorId},
        shards=collector.writer.descriptors,
        vocabulary=feature_vocabulary(catalog),
        started_at_utc=started_at_utc,
        completed_at_utc=_utc_now() if status != "IN_PROGRESS" else None,
        failure=failure,
    )


def collector_state_config_hash(catalog: CatalogBundle) -> str:
    return hashlib.sha256(_canonical(catalog.model_dump(mode="json", exclude_none=False)).encode("utf-8")).hexdigest()


def generate_dataset(
    *,
    config_path: Path,
    output_root: Path,
    dataset_id: str,
    seed: int,
    maximum_rows: int,
    maximum_minutes: int,
    rows_per_shard: int = DEFAULT_ROWS_PER_SHARD,
    source_commit: str | None = None,
) -> DatasetManifest:
    if maximum_rows <= 0 or maximum_minutes <= 0:
        raise ValueError("M4 maximum_rows and maximum_minutes must be positive")
    _ensure_external(output_root)
    destination = output_root / dataset_id
    if destination.exists():
        raise FileExistsError(f"M4 dataset destination already exists: {destination}")
    destination.mkdir(parents=True)
    started = _utc_now()
    commit = source_commit or _repository_head()
    catalog = load_catalog(config_path)
    m3_catalogs = load_m3_catalogs(config_path, catalog=catalog)
    writer = ParquetShardWriter(destination, rows_per_shard=rows_per_shard)
    collector = DecisionDatasetCollector(
        catalog,
        m3_catalogs,
        source_commit=commit,
        seed=seed,
        maximum_rows=maximum_rows,
        writer=writer,
    )
    initial = build_initial_society_checkpoint(catalog, m3_catalogs, seed=seed)
    engine = SocietyEngine(catalog, m3_catalogs, initial, decision_observer=collector)
    manifest_path = destination / "dataset-manifest.json"
    _atomic_json(
        manifest_path,
        _manifest(
            dataset_id=dataset_id,
            status="IN_PROGRESS",
            source_commit=commit,
            catalog=catalog,
            m3_catalogs=m3_catalogs,
            collector=collector,
            started_at_utc=started,
        ).model_dump(mode="json", exclude_none=False, by_alias=True),
    )
    try:
        target_limit = initial.world.game_minute + maximum_minutes
        while engine.state.game_minute < target_limit and not collector.limit_reached:
            engine.advance_to(engine.state.game_minute + 1)
            if collector.flush_ready():
                _atomic_json(
                    manifest_path,
                    _manifest(
                        dataset_id=dataset_id,
                        status="IN_PROGRESS",
                        source_commit=commit,
                        catalog=catalog,
                        m3_catalogs=m3_catalogs,
                        collector=collector,
                        started_at_utc=started,
                    ).model_dump(mode="json", exclude_none=False, by_alias=True),
                )
        collector.flush_ready(final=True)
        completed = _manifest(
            dataset_id=dataset_id,
            status="COMPLETED",
            source_commit=commit,
            catalog=catalog,
            m3_catalogs=m3_catalogs,
            collector=collector,
            started_at_utc=started,
        )
        _atomic_json(manifest_path, completed.model_dump(mode="json", exclude_none=False, by_alias=True))
        return completed
    except Exception as exc:
        failed = _manifest(
            dataset_id=dataset_id,
            status="FAILED",
            source_commit=commit,
            catalog=catalog,
            m3_catalogs=m3_catalogs,
            collector=collector,
            started_at_utc=started,
            failure=f"{type(exc).__name__}: {exc}",
        )
        _atomic_json(manifest_path, failed.model_dump(mode="json", exclude_none=False, by_alias=True))
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an external M4 heuristic-teacher Parquet dataset")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--maximum-rows", type=int, default=10_000)
    parser.add_argument("--maximum-minutes", type=int, default=10_080)
    parser.add_argument("--rows-per-shard", type=int, default=DEFAULT_ROWS_PER_SHARD)
    parser.add_argument("--source-commit")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    manifest = generate_dataset(
        config_path=arguments.config,
        output_root=arguments.output_root,
        dataset_id=arguments.dataset_id,
        seed=arguments.seed,
        maximum_rows=arguments.maximum_rows,
        maximum_minutes=arguments.maximum_minutes,
        rows_per_shard=arguments.rows_per_shard,
        source_commit=arguments.source_commit,
    )
    print(json.dumps(manifest.model_dump(mode="json", exclude_none=False, by_alias=True), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
