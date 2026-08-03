# AITOWN-MODEL handoff

## State

M4 was activated by the producer on 2026-08-04 from public
`main@02b9e53b8ec11b06235be704dec7d5fcd7495945`.

The logical `AITOWN-MODEL` responsibility is active under `AITOWN-ORCH`. A
separate long-running Codex task was intentionally not created at entry because
the producer reported only about 10% weekly Codex quota remaining. This does not
change path or contract ownership; it creates a clean handoff for a dedicated
task after quota reset if useful.

## Frozen inputs

- M3 accepted implementation:
  `cc7f581da0548cb5aebd3d215db3e7bd93575d11`;
- M3 release record: `docs/orchestration/M3_ACCEPTANCE_RECORD.md`;
- M4 baseline: `docs/orchestration/M4_EXECUTION_BASELINE.md`;
- model boundary: ADR-0005, ADR-0012, and ADR-0013;
- active feature/label versions: `v0.1` / `v0.1`;
- active online protocol remains `0.3.0`;
- DeepSeek and all language work remain M5.

## Cloud target

- SSH alias: `stwm-autodl`;
- repository: `/root/autodl-tmp/STWM`;
- active work: `/root/autodl-tmp/stwm-m4-work`;
- durable root: `/root/autodl-fs/STWM/m4`;
- RTX 4090 24GB, 16 CPU, 120GB RAM;
- Python 3.12.3, PyTorch 2.5.1+cu124, CUDA 12.4;
- 30GB system, 50GB local data, 200GB mounted file storage.

Do not place credentials in the repository or handoff. Source AutoDL's official
`/etc/network_turbo` only for outbound dependency/GitHub access.

## Implemented data foundation

The first M4 source increment now provides:

1. internal M4 Pydantic contracts and committed JSON Schemas;
2. `OutcomeModel` batch Protocol, `RecordedOutcomeModel`, and an exact M3
   heuristic row adapter;
3. catalog mask/bounds/finite postprocessing;
4. deterministic feature extraction and group-owned split keys;
5. a default-off read-only `SocietyDecisionObserver` seam whose enabled and
   disabled authority checkpoints are regression-equal;
6. an external bounded Parquet producer using locked `pyarrow==19.0.1`;
7. focused contracts/provider/authority-neutrality tests.

The smoke is now complete at source `abb9d92`: 9,996 rows, 1,435 complete
decision groups, all 22 behaviors, strict train/validation/test grouping, and
matching manifest/shard hashes. The durable copy is
`/root/autodl-fs/STWM/m4/datasets/m4_teacher_smoke_seed12345_abb9d92`.

The raw matrix is complete at source `73ca45f`: all five frozen seeds, a
100,000-row cap per seed, 499,978 total rows, 71,636 decision groups, 23 shards,
and 22/22 behavior coverage. Seed-isolated `--max-workers 5` execution completed
in about 29 minutes; only the parent wrote producer state and aggregation.

The durable dataset is
`/root/autodl-fs/STWM/m4/datasets/m4_teacher_release_raw_v1_73ca45f`.
Its manifest SHA-256 is
`e256ecf426d4d0b2ab4bfb63060873e88233c1aaeb14498cc536ef7f3161eccb`.
The strict dataset validator passed at production, active-copy recheck,
durable-copy recheck, and formal quality-analysis entry.

The quality tool at source `881a023` emitted
`/root/autodl-fs/STWM/m4/reports/m4_teacher_release_raw_v1_73ca45f-quality.json`
with SHA-256
`298f7dc159cace7c6a607324e90107ea10c117ebdf33a3c49a8d29855c0c5231`.
All formal raw-data gates pass. The report warns that teacher-selected auxiliary
ranking labels are highly imbalanced; candidate-level outcome coverage remains
complete. Use grouped weighting/balancing, per-behavior metrics, and anchor
holdouts rather than aggregate selection accuracy.

The next data increment is exactly 300 independently reviewed social anchors
under ADR-0013: 40 each for `greet`, `chat`, `joke`, `compliment`, and
`invite_join`, plus 50 each for `apologize` and `confront`. Their frozen split is
210 TRAIN, 30 VALIDATION, and 60 ANCHOR_HOLDOUT. Tasks, Codex judgments, review
issues, approval manifests, and coverage policies are separate hash-chained
artifacts; raw labels and Parquet rows remain immutable. Raw rows alone do not
authorize release training.

## Pause/resume

At each safe point update the durable
`/root/autodl-fs/STWM/m4/control/m4-progress.json` descriptor and this handoff.
Generated data/model artifacts are external and referenced by relative path,
SHA-256, byte size, schema, source commit, and parent artifact hashes.

Current source stage: `M4_RAW_DATA_VALIDATED`; next stage:
`M4_REVIEWED_SOCIAL_ANCHORS`.

ADR-0013 is the anchor-stage authority. Implement its additive Python-private
schemas and deterministic task selector before any producer judgment batch.
Holdout judgments cannot be exposed to training, early stopping, calibration,
or hyperparameter selection.

The first approval manifest must select the frozen 300 entries. Producer task
and judgment artifacts stay immutable; reviewer issues and approvals reference
their canonical SHA-256 values. Revisions create new judgment artifacts rather
than overwriting drafts. Only approved TRAIN/VALIDATION judgments may overlay
named bounded soft targets; ANCHOR_HOLDOUT remains evaluation-only.
