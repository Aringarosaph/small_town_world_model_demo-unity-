# M4 execution baseline

Status: active and frozen by AITOWN-ORCH on 2026-08-04.

Base: accepted public `main@02b9e53b8ec11b06235be704dec7d5fcd7495945`.

Accepted M3 implementation boundary:
`cc7f581da0548cb5aebd3d215db3e7bd93575d11`.

## Product outcome

M4 trains and integrates a small conditional outcome model that distills
bounded social reactions from the complete M3 rule society, reviewed anchors,
and constrained augmentation. It is not an autonomous discoverer of social
laws and it never owns authority.

The release must provide:

- a versioned feature/label/anchor/dataset contract;
- 300-1,000 reviewed social anchors;
- 50,000-100,000 grouped decision-state samples and 300,000-1,000,000 candidate
  rows;
- a readable 1M-3M parameter PyTorch model with per-head evaluation;
- `HeuristicOutcomeModel`, `TorchOutcomeModel`, and `RecordedOutcomeModel` behind
  one batch interface;
- catalog masks, bounds, deterministic sampling, package compatibility checks,
  structured fallback, and zero hard-authority mutation;
- local CPU batch inference, model switching, replayable neural rollout, and a
  30-day safety comparison against the M3 baseline.

## Entry evidence and environments

The producer explicitly activated M4 on 2026-08-04. M3 is accepted, frozen, and
remains the regression baseline.

The cloud entry audit passed:

- AutoDL, Ubuntu `22.04`, Python `3.12.3`;
- NVIDIA RTX 4090 24GB, driver `580.76.05`;
- PyTorch `2.5.1+cu124`, CUDA runtime `12.4`, BF16 available;
- actual container limits: 16 CPU cores and 120GB RAM;
- 30GB system disk, 50GB local data disk, and mounted 200GB redundant file
  storage;
- CUDA matrix smoke passed and the GPU was idle/healthy at entry;
- repository clone `/root/autodl-tmp/STWM` matched public
  `main@02b9e53b8ec11b06235be704dec7d5fcd7495945`;
- direct GitHub HTTPS needs AutoDL's official `network_turbo`; access passes
  after it is sourced.

Storage ownership is frozen as follows:

- `/root/autodl-tmp/STWM`: working clone and active local-I/O jobs;
- `/root/autodl-tmp/stwm-m4-work`: generated shards and ephemeral caches;
- `/root/autodl-fs/STWM/m4`: durable manifests, reviewed data, checkpoints,
  packages, reports, and resumable job state;
- Git: source, contracts, tests, small reviewed anchors, handoffs, and hashes;
- never Git: generated rows, runs, caches, model weights, or secrets.

The MacBook Air remains responsible for source integration, CPU inference
acceptance, M0-M3 regressions, Unity, and final orchestration.

## Compatibility and authority boundary

ADR-0012 owns the M4 model boundary.

- Protocol `0.3.0`, public world schema `v0.1`, M3 checkpoint v1, 10 NPCs,
  22 behaviors, 4 households, 8 locations, 15 object types, and 90 directed
  relationship edges remain unchanged.
- Existing M1, M2, and M3 gates must pass without model artifacts installed.
- The neural model receives only legal candidates after hard filtering.
- It cannot modify money, food, schedules, objects, reservations, ownership,
  action phases, event types, visibility, knowledge permissions, or arbitrary
  state fields.
- Need deltas and event probabilities remain auxiliary/preview heads in M4.
- Accepted-path actor/target mood, Target-to-Actor relationship deltas, and
  social acceptance may be consumed only after catalog postprocessing.
- A rejected social action uses the frozen rule rejection effect.
- The heuristic path must reproduce accepted M3 behavior and remains a one-step
  fallback at all times.
- M5 DeepSeek, PLAYER_TOLD, player language, M6 golden-chain publication, and
  all post-V0 Claim/Belief, Commitment, GNN, RSSM, RL, institution, or free
  behavior-generation work remain excluded.

## Feature and label contract

Active identities:

- feature schema `stwm.model.candidate-feature-row/v1`;
- catalog feature version `v0.1`;
- label schema `stwm.model.outcome-label/v1`;
- label version `v0.1`;
- at most four event-context tokens;
- at most twelve candidates per agent and 120 rows per inference batch.

Each row contains trace identifiers, raw structured values, normalized numeric
features, categorical indices, masks, hard preview, soft targets, provenance,
and grouping/split keys. Trace identifiers such as `actor_id` and
`candidate_id` are never embeddings.

The feature surface follows the implementation specification:

- actor needs, mood, personality, household resource ratios, schedule/action
  timing, local population summaries, and stable actor categories;
- behavior/destination/capability embeddings, travel/duration/cost/conflict,
  repetition, cross-location, and JointAction flags;
- masked target needs/mood, directed relationship, relationship labels,
  interaction timing, family/coworker/conversation/knowledge flags;
- up to four typed event tokens encoded with masked mean and max pooling.

Catalog-derived vocabularies and numeric normalization live in the model
package. Unknown or incompatible production categories cause whole-batch
heuristic fallback; they are not silently assigned new indices.

## Data and anchor plan

Release data minimums are 50,000 grouped decision states and 300,000 candidate
rows. The target is approximately 360,000-500,000 rows unless coverage requires
more; one million is a hard V0 ceiling, not a target to fill for its own sake.

Data generation uses the accepted M3 seeds:

- 7-day: `12345`, `24680`, `97531`, `314159`, `271828`;
- 30-day: `12345`, `24680`, `97531`.

After the 10,000-row smoke measured approximately 1,435 decisions and 9,996
candidate rows per seven game days, the raw training matrix is frozen as five
serial 60-day runs using `12345`, `24680`, `97531`, `314159`, and `271828`.
Each seed is capped at 100,000 rows, so the combined raw dataset remains below
the one-million-row ceiling while targeting 50,000+ decision groups and
300,000-500,000 rows. This training-data matrix does not change the release
rollout gate, which remains five 7-day and three 30-day neural comparisons.

One dataset episode/group spans seven consecutive game days. Its rows and
augmented descendants stay in one split; stable group hashing assigns 80/10/10
buckets. This prevents individual days or candidates from leaking across
splits while providing enough independent groups for all three partitions.

Every due-agent decision records all legal candidates with heuristic
counterfactual labels. Output is sharded Parquet with atomic manifests and
checksums. A shard contains at most 25,000 rows so generation can resume without
rewriting accepted shards.

The social anchor gate requires at least 300 approved anchors over the seven
acceptance behaviors and the frozen pairwise coverage dimensions. Production
and review run in batches of 25-50 anchors. Each batch records a producer file,
independent review issues, an approval manifest, coverage deltas, and hashes.
Rejected or disputed anchors are never training inputs.

Constrained augmentation may perturb continuous neighborhoods and semantic
equivalents, but descendants inherit the source group/split and may not cross
behavior masks or bounds.

Split policy is deterministic and group-owned:

- 80% train, 10% validation, 10% test by stable scenario-group hash;
- whole episodes, anchor families, and augmented descendants stay together;
- boundary, unseen-combination, anchor holdout, and long-rollout suites are
  separate named evaluation sets;
- release metrics are computed once on the frozen test manifests.

## Model and training plan

The first release architecture is the specification's readable MLP/DeepSets
baseline:

- categorical embeddings and continuous normalizer;
- two-layer actor, candidate, and target encoders;
- event token MLP with masked mean/max pooling;
- width 256, four residual LayerNorm/GELU blocks;
- need, actor/target mood, Target-to-Actor relationship, acceptance, and grouped
  event heads;
- 1M-3M trainable parameters.

Training uses PyTorch, AdamW, FP32 or BF16, Huber plus BCE/CE losses, per-head
metrics, early stopping, and a best-validation checkpoint. Release training
uses fixed seeds `12345`, `24680`, and `97531`; a single smoke seed is not release
evidence.

Before a release run, a 10,000-row smoke fit must validate the complete load,
forward, loss, checkpoint, resume, export, and evaluation path. Release jobs:

- checkpoint every epoch and after graceful interruption;
- write metrics and RNG/optimizer/scheduler state atomically;
- resume only when dataset, config, code, and parent-checkpoint hashes match;
- have a two-hour wall-time cap per invocation and a finite early-stop bound;
- produce a terminal success/failure manifest without requiring an attached
  Codex session.

## Runtime integration

The Society engine receives an `OutcomeModel`; it does not import a global model
singleton. Due candidates are feature-encoded and predicted in batches of at
most 120. Predictions pass the catalog postprocessor before utility scoring.

The default remains heuristic until every M4 release gate passes. After
acceptance, `neural` may be selected only with an exact compatible package.
`heuristic`, explicit package selection, and automatic fallback remain runtime
options. Fallback records provider, requested model, reason, state version, and
batch identity without exposing paths or secrets.

Neural acceptance sampling is reproducible from world seed, state version,
action ID, and model version. The chosen prediction and provider version remain
in decision/action evidence so authoritative replay never reruns inference.

## Acceptance gates

All gates are blocking unless explicitly marked diagnostic:

1. **Contracts:** exact schema/version validation, grouped split integrity,
   package hashes, and no generated artifacts in Git.
2. **Coverage:** at least 300 approved anchors, 50,000 decision states, 300,000
   candidate rows, all 22 behaviors, all five need/four personality/two mood/four
   relationship axes, all target/event masks, and all seven acceptance behaviors.
3. **Safety:** pre-postprocess violations are counted; postprocess illegal-field,
   non-finite, out-of-bound, absent-target, unknown-event, and hard-authority
   commit rates are exactly zero.
4. **Continuous heads:** need MAE at most `0.02`; mood and relationship MAE at
   most `0.03`; high-tension/boundary MAE at most `0.04` on their named suites.
5. **Acceptance:** Brier score at most `0.08`, ECE at most `0.05`, and ROC-AUC at
   least `0.80` when the suite contains both classes; metrics are also reported
   per behavior.
6. **Anchor holdout:** neural composite error is no worse than the frozen
   heuristic baseline and no directional high-risk anchor assertion regresses.
7. **Decision quality:** teacher Top-1 agreement at least `0.90`, Top-3 coverage
   at least `0.98`, and normalized relative regret at most `0.03`.
8. **Model shape:** parameter count is within 1M-3M and every head/mask has an
   executable ablation or targeted test.
9. **CPU:** on the producer MacBook Air, batch-120 p95 is below 50ms and the
   report also records batch 1/12/60/120 and the ideal 20ms target.
10. **Runtime:** model switch, corrupt/missing/mismatched package, exception,
    non-finite output, and explicit heuristic fallback all pass with no partial
    mutation.
11. **Rollout:** fixed 7-day comparisons and all three fixed 30-day neural runs
    pass M3 invariants, replay, economy, reservation, liveness, event-growth,
    relationship, and performance gates; golden-chain diagnostics are not
    promoted to the M6 release.
12. **Regression:** M0-M3 strict Python gates and the accepted Unity protocol/
    presentation surface pass without requiring weights.

Threshold changes after seeing test results require an additive ADR; they may
not be relaxed silently to accept a run.

## Codex-quota and interruption policy

The producer reported approximately 10% weekly Codex quota remaining at M4
activation, with a possible reset later on 2026-08-04. AITOWN-ORCH reads the
account rate-limit snapshot only at safe boundaries:

- `usedPercent <= 10`: at least 90% remains; normal implementation may proceed;
- `usedPercent < 98`: more than about 2% remains; bounded implementation and
  dataset work may continue, but long training remains separately authorized;
- `usedPercent >= 98`: create/update the pause handoff, sync durable artifacts,
  commit a coherent source state, and stop new implementation work.

This threshold was explicitly revised by the producer on 2026-08-04 after the
activation baseline. Safe atomic boundaries and the ban on unapproved manual
reset credits remain unchanged.

Manual reset credits are never consumed without explicit producer approval.

Every vertical increment must end with:

1. tests for the completed scope;
2. a scoped Git commit with no generated artifacts;
3. `/root/autodl-fs/STWM/m4/control/m4-progress.json` updated atomically with
   source commit, stage, commands, artifact hashes, job state, and next action;
4. resumable external artifacts copied from local work storage to file storage;
5. a handoff that distinguishes completed, running, pending, and blocked work.

An unattended cloud job may outlive a Codex turn only when it has bounded wall
time, automatic checkpoints, terminal manifests, and no need for interactive
approval. Otherwise the GPU instance is shut down at the pause point.

## Vertical increments and safe pause points

1. **M4 activation:** this baseline, ADR-0012, environment audit, ownership, and
   pause protocol.
2. **Contracts:** feature/label/anchor/package models, postprocessor, recorded
   provider, schemas, and tests.
3. **Data:** deterministic feature extraction, grouped splits, resumable Parquet
   producer, and a small end-to-end dataset smoke.
4. **Anchors:** reviewed batches and coverage/conflict diagnostics.
5. **Model:** architecture, loss, checkpoint/resume, export, and smoke training.
6. **Integration:** injected providers, neural sampling, fallback, debug
   provenance, and M3 compatibility.
7. **Release:** full data, multi-seed training, calibration, CPU benchmark,
   fixed rollout, strict QA evidence, documentation, and acceptance.

Stop and return to AITOWN-ORCH before changing frozen IDs, public protocol,
authority ownership, M3 heuristic behavior, output direction, or any exclusion
above.
