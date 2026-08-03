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

The reviewed-data increment is exactly 300 independently reviewed social anchors
under ADR-0013: 40 each for `greet`, `chat`, `joke`, `compliment`, and
`invite_join`, plus 50 each for `apologize` and `confront`. Their frozen split is
210 TRAIN, 30 VALIDATION, and 60 ANCHOR_HOLDOUT. Tasks, Codex judgments, review
issues, approval manifests, and coverage policies are separate hash-chained
artifacts; raw labels and Parquet rows remain immutable. The completed FINAL
approval and fit-only manifest now authorize bounded training work, but they do
not constitute an accepted model package.

## Pause/resume

At each safe point update the durable
`/root/autodl-fs/STWM/m4/control/m4-progress.json` descriptor and this handoff.
Generated data/model artifacts are external and referenced by relative path,
SHA-256, byte size, schema, source commit, and parent artifact hashes.

Current durable stage: `M4_REVIEWED_SOCIAL_ANCHORS_APPROVED`; next stage:
`M4_QUOTA_SAFE_TORCH_SMOKE_TRAINING`.

ADR-0013 is the anchor-stage authority. Implement its additive Python-private
schemas and deterministic task selector before any producer judgment batch.
Holdout judgments cannot be exposed to training, early stopping, calibration,
or hyperparameter selection.

The first approval manifest must select the frozen 300 entries. Producer task
and judgment artifacts stay immutable; reviewer issues and approvals reference
their canonical SHA-256 values. Revisions create new judgment artifacts rather
than overwriting drafts. Only approved TRAIN/VALIDATION judgments may overlay
named bounded soft targets; ANCHOR_HOLDOUT remains evaluation-only.

## M4 anchor-task integration result

- Selector source: `75ba0306c8a419fe1043a50edc5d582bb9f799a6`;
  validator source: `31211a7e4fbdf3b09606519b65300d4d2644dd78`.
- Durable packet:
  `/root/autodl-fs/STWM/m4/anchors/m4_social_anchor_tasks_v1_75ba030`.
- Exact matrix: 300 tasks = 210 TRAIN + 30 VALIDATION + 60 ANCHOR_HOLDOUT;
  seven behavior-local batches meet the ADR-0013 quotas.
- `anchor-tasks.jsonl` SHA-256:
  `d463506978f2b4671bfdabad07e70756d948ff672167059760e0b4120c10dc54`;
  coverage policy SHA-256:
  `f185fd73a121d3c22037a3c7c96dab3e5087af67cc5a22b292c4477610345429`.
- Independent regeneration report:
  `/root/autodl-fs/STWM/m4/reports/m4_social_anchor_tasks_v1_75ba030-validation.json`,
  SHA-256
  `8c4dc2fbc060020076a360249ff9fa0d8d970d0cecdfb1b04c33f14ce3b6428f`.
- Every task and coverage row regenerated identically from the accepted raw
  dataset. Actor-target maximum repeat is 3; exact signature maximum repeat is
  2. The packet is explicitly `TASKS_ONLY_VALIDATED_NOT_JUDGED`.
- The seven immutable Codex judgment batches and exact final approval matrix
  are complete below. Do not expose holdout judgments to fitting, calibration,
  early stopping, or hyperparameter selection.

## M4 anchor-judgment provenance refinement

The first `greet` pilot correctly exposed an auxiliary-teacher limitation:
catalog event probabilities do not encode whether a conversation or first
greeting already exists. The pilot draft is therefore superseded and is not a
training input. This finding does not expand the learned authority boundary or
relax an approval gate.

Each new `SocialAnchorJudgment` now records two disjoint provenance sets. Codex
review covers only catalog-enabled acceptance, actor/target mood, and
Target-to-Actor relationship paths that M4 may consume. All five need-delta
paths and `event_probabilities` remain byte-equivalent heuristic passthrough
heads under ADR-0012. Both the producer and independent-review assemblers reject
path drift or any attempted passthrough value change. Reviewer issue artifacts
may continue to record auxiliary event limitations without attributing those
fields to Codex judgment.

`anchor_review.py` assembles immutable producer judgments;
`anchor_approval.py` independently verifies hashes, catalog masks/bounds,
declared path provenance, and reviewer findings into a DRAFT approval manifest.

The superseding `greet` batch at source
`ae05aedc8dd08858f8d800553c910930bf177956` passed independent production and
review reassembly. All 40 judgments are approved: 28 TRAIN, 4 VALIDATION, and 8
ANCHOR_HOLDOUT; there are no rejected or disputed entries. Thirty acknowledged
advisories document the auxiliary heuristic event-context limitation. AITOWN-ORCH
audited four entries, including the largest reviewed-head deviation and one
holdout, with no direction or semantic disagreement.

Durable batch:
`/root/autodl-fs/STWM/m4/anchors/greet-reviewed-batch-ae05aed`.
Its manifest SHA-256 is
`de33b1c2cc5900444ccaa934f923056a35d35639292b0ed020b90b31de06a128`;
judgment SHA-256 is
`71dc227664505e9bf3d6d6e2855bcceb5605029bdcad2546dbd8e93cd81eebd2`;
independent review response SHA-256 is
`dadad81f30de73fb3a1195f7e9be72ac4eaa294793d5282a0095093ac736a651`.
The other six behavior-local batches also passed the same independent chain:

- `chat`: 40/40 approved; manifest SHA-256
  `55378fff806923990c254e6dcdc19b306df522b81c4f86bfae8cf4844ffc6462`;
- `joke`: 40/40 approved; manifest SHA-256
  `2e6067c736d1420b5e69b9a4fd08295b372f42d80a265348b2a15eb26e92d746`;
- `compliment`: 40/40 approved; manifest SHA-256
  `631984ebbec4376355a827f1d5803a798e8b2d1591cb3acd7b443aef4f5c50ed`;
- `invite_join`: 40/40 approved; manifest SHA-256
  `82c34d0f4c7b74b49a14eac36d3c40f8318904a4441c54a13a0a2e9795e3069a`;
- `apologize`: 50/50 approved; manifest SHA-256
  `6b234a8f1d28436d8a8cda61fb6161487f401bc94f5f7e4c33b542a91875e007`;
- `confront`: 50/50 approved; manifest SHA-256
  `8be1ccb27bd602ac8de02488b3c1f6084bb11cbab5e01e5da6109955f8480b01`.

AITOWN-ORCH reproduced all producer/reviewer assemblies byte for byte and
sampled 32 entries across the seven batches. The final `confront` audit covers
the complete seven-entry high-risk union: all no-event, lower-clipped,
severe-tension, and dual-high-stress cases. Events remain context evidence,
not proof of guilt, blame, sincerity, or factual responsibility.

Every behavior-local approval remains immutable DRAFT evidence. Source
`6112f96c5026a67d4e238c04a3e0abdd1df80817` adds the strict aggregate
finalizer and the private
`stwm.model.social-anchor-training-input-manifest/v1` contract. It validates
all packaged producer/reviewer reports, source hashes, decisions, issue
acknowledgements, catalog-safe judgments, and the exact partition matrix.

The formal durable aggregate is
`/root/autodl-fs/STWM/m4/anchors/m4_reviewed_social_anchors_final_6112f96`:

- FINAL approval: 300/300 = 210 TRAIN + 30 VALIDATION + 60 ANCHOR_HOLDOUT;
- final approval SHA-256:
  `3b9ea65572707105b259d0a9e81a75d076d0d0602ba7ebbddccc7761b15f5900`;
- fitting file: exactly 240 judgments = 210 TRAIN + 30 VALIDATION and zero
  ANCHOR_HOLDOUT; SHA-256
  `46a53fd603542413f5d11b19464c65767b65d73bb424b10c8e676b726f1ea7e5`;
- training-input manifest SHA-256:
  `1c9d0655a0c553db2a786077bd1ae7604580b1b8426f6c5e3976637127b2c398`.

Long training has not started. The next increment is only the locked
TorchOutcomeModel/data-loader implementation plus bounded shape/finite-value
smoke. Recheck quota before any long run; prepare a durable pause at about 2%
remaining and never consume either manual reset credit without producer
approval. The latest official snapshot remains 95% used / about 5% remaining.
