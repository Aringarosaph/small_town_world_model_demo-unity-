# Integration matrix

| Interface | Owner | Consumers | M0 artifact | Change gate |
|---|---|---|---|---|
| Domain IDs and enums | CONTRACTS | SIM, UNITY, MODEL, DIALOGUE, QA | Python DTOs and JSON Schema | Schema version + ADR |
| World configuration | CONTRACTS | SIM, MODEL, QA | `config/v0/` | Config hash + validation |
| Behavior/object catalogs | CONTRACTS | SIM, UNITY, MODEL, QA | YAML catalogs | Catalog version + coverage test |
| Message envelope | CONTRACTS | SIM, UNITY, QA | M3 `0.3.0`; M2 `0.2.0`; `0.1.0` legacy decode | Protocol semver + compatibility test |
| Authority transactions | SIM | UNITY, MODEL, QA | M1 | ADR + invariant tests |
| Semantic asset registry | CONTRACTS / UNITY | SIM, QA | M2 scoped profile; M3 shared full-town manifest | Catalog re-freeze + dual Python/Unity validation |
| Movement/presentation reports | CONTRACTS | SIM, UNITY, QA | M2 directional `0.2.0`; M3 structured `0.3.0` | ADR + direction/version/idempotency tests |
| OutcomeModel DTO | CONTRACTS | SIM, MODEL, QA | M0 protocol only | Feature/model version + regression |
| M4 feature/label/anchor contracts | MODEL / ORCH | SIM, QA | ADR-0012 raw contracts + ADR-0013 reviewed-anchor ledger | Schema identity + feature/label version + grouped-split/hash-chain/review tests |
| M4 model package and providers | MODEL | SIM, QA | ADR-0012 package/provider boundary | Package hashes + CPU inference + fallback + rollout |
| Knowledge/SpeechPlan | CONTRACTS | SIM, DIALOGUE, UNITY, QA | M0 schema | Schema + permission tests |
| Decision trace and run layout | QA | All | M0 docs/checks | Observability review |
| M3 authority checkpoint | SIM | QA, replay | ADR-0011 sidecar v1 | Checkpoint schema + resume/replay hashes |
| Full-town semantic instances | CONTRACTS | SIM, UNITY, QA | M3 shared manifest | Catalog re-freeze + dual registry gate |
| Background NPC templates | CONTRACTS | SIM, UNITY, QA | M3 deterministic UTF-8 catalog | Coverage + deterministic selection + catalog re-freeze |

## Merge order for M0

1. Orchestrator repository and ADR baseline.
2. Contracts configuration and validation.
3. QA/CI checks adapted to the integrated contract.
4. Full validation and M0 release commit.

## M0 integration record

- Orchestrator baseline: `d12450a`
- Environment lock baseline: `32cd848`
- QA handoff integrated: `23acf49`
- Contracts handoff integrated and frozen source: `9bc2051`
- Appendix D sign-off: `tools/diagnostics/m0_config_freeze.json`

The next writable product boundary is M1's authority runtime. All rows marked
with an M0 artifact are frozen inputs to that work.

## Merge order for M1

1. Orchestrator naming, scope, CLI, evidence, and acceptance baseline.
2. Simulation runtime, tests, run writer, Headless CLI, and replay CLI.
3. QA adapters and independent determinism/replay/invariant gates.
4. Full repository validation and an audited three-day run.
5. Public `main` push followed by both GitHub Actions gates.

## M1 integration record

- Public naming and execution baseline: `a8c23b8`
- Simulation runtime handoff: source `2afad99`, integrated as `7b59c0c`
- Independent QA handoff: source `99da488`, integrated as `4b19cdd`
- Work attendance semantics: ADR-0008
- Final strict gate: `tools/diagnostics/check_m1.py --require-sim`
- Orchestrator acceptance commit: `3d43c15`
- GitHub Actions acceptance run: `30722721963` (all three jobs passed)

## M2 protocol integration record

- M2 functional-greybox and scoped-registry baseline: ADR-0009 / `0a4caa1`
- Movement cancellation and protocol `0.2.0`: ADR-0010 / `392f941`
- Additive formatted source consumed by the re-freeze: `247711a`
- Active M2 acceptance version: exactly `0.2.0`
- Legacy compatibility: `0.1.0` bootstrap/decode tests only; no cancellation gate
- Heartbeat: WebSocket ping/pong; no JSON message
- Reconnect: full hello/registry/snapshot/ready sequence; no resync JSON message
- Authority direction: Unity reports `movement_cancelled`; only Python emits the
  committed `action_cancelled`
- Evidence naming: M2 sessions record `catalog_protocol_version` separately from
  `negotiated_protocol_version`
- Freeze gate: protocol/domain changes require the ADR-0010 M2 re-freeze manifest;
  the original M0 `0.1.0` source evidence remains recorded

## M2 implementation integration record

- Orchestrator execution baseline: `0a4caa1`
- Protocol feature/format/re-freeze integrated as: `8a66e91`, `660efd8`, `1dcfd04`
- Python WebSocket/cancellation/evidence integrated as: `a2a4814`, `8cfea57`, `7e11d24`
- QA baseline and stale-semantics gate integrated as: `02c034c`, `19f769e`
- Unity greybox foundation and final acceptance tooling integrated as:
  `6d2fec1`, `6b5b7d0`
- Local strict result: Unity EditMode 26/26, PlayMode 4/4, Python 123 tests,
  integration 7 tests, M2 diagnostics 19 pass / 26 allowed warnings / 0 pending / 0 fail
- Remote Python acceptance: GitHub Actions run `30749456317` passed all QA,
  M0, M1, and M2 jobs on `codex/aitown-orch-m2`
- Producer accepted the reproducible local Unity evidence gate; a remote
  licensed macOS ARM64 Unity lane is optional future infrastructure

## Merge order for M3

1. Orchestrator execution baseline, ADR-0011, thresholds, and ownership.
2. CONTRACTS protocol `0.3.0`, shared semantic/template catalogs, compatibility
   artifacts, and re-freeze.
3. SIM society runtime in vertical increments, checkpoint/replay, bridge, and
   authority evidence.
4. QA independent readiness, behavior/economy/knowledge/JointAction/pathology,
   and soak gates.
5. UNITY full-town builder, strict local registry, multiplayer presentation,
   Debug UI, and zero-skipped evidence.
6. Orchestrator integrated regressions, fixed-seed soak, release evidence,
   producer acceptance, and public `main` publication.

## M3 activation record

- Accepted base: public `main@7b2618de09bd87eb49716ac40f1d0ba697f00351`
- Integration branch: `codex/aitown-orch-m3`
- Execution baseline: `docs/orchestration/M3_EXECUTION_BASELINE.md`
- Contract decision: ADR-0011
- M3 active protocol: exactly `0.3.0`
- Accepted M2 compatibility protocol: exactly `0.2.0`

## M3 CONTRACTS integration record

- Active wire contract: `ProtocolMessageV030` and direction-specific V030 unions.
- Public snapshot state: unchanged `WorldState` schema `v0.1`; reconnect adds a
  presentation projection outside the public state.
- Compatibility: explicit V020 aliases/artifacts plus unchanged historical M2
  artifact names; V010 remains legacy decode.
- Shared M3 catalogs: `stwm.catalog.m3-semantic-instances/v1` and
  `stwm.catalog.m3-background-dialogue/v1`.
- Checkpoint owner: SIM. CONTRACTS does not publish a competing authority
  checkpoint or private-ledger model.
- Re-freeze authority: ADR-0011; content commit and final manifest commit are
  reported in cherry-pick order after validation.

## M3 acceptance integration record

- Accepted implementation commit:
  `cc7f581da0548cb5aebd3d215db3e7bd93575d11`.
- Protocol/catalog foundation: `bf3a136`, `e27051a`; active M3 protocol is
  exactly `0.3.0`, with M2 acceptance preserved at exactly `0.2.0`.
- Society/runtime foundation: `e920187`, followed by the accepted checkpoint,
  replay, evidence, liveness, performance, event-ledger, behavior-occurrence,
  and invited-JointAction fixes through `cc7f581`.
- Independent QA/assembler foundation: `fc26dce`, `46b0bc1`, `2e22a98`,
  `df48c7d`; the final strict gate is 19 pass / 0 pending / 0 fail.
- Unity full-town foundation and evidence: `98380ff`, `7a1df95`, `48822bf`,
  `81d20d9`, `3abdbf9`, `e953d3a`; final Unity evidence was regenerated at the
  accepted source commit with EditMode 72/72 and live PlayMode 6/6, zero skips.
- Release matrix: canonical repeat/chunks `1/7/60`, five fixed seven-day seeds,
  and three fixed thirty-day seeds; all final state, ledger, authority-log,
  checkpoint-resume, and replay hashes match.
- Full release evidence and immutable hashes are recorded in
  `docs/orchestration/M3_ACCEPTANCE_RECORD.md`; raw generated runs remain outside
  Git.

## Merge order for M4

1. Orchestrator activation baseline, ADR-0012, cloud audit, metrics, storage,
   and quota-safe pause policy.
2. MODEL internal feature/label/anchor/package contracts, postprocessor,
   provider interface, heuristic/recorded providers, schemas, and tests.
3. MODEL grouped dataset and independent anchor production/review increments.
4. MODEL architecture, smoke training, checkpoint/resume/export, evaluation,
   and external artifact manifests.
5. SIM injected neural provider, deterministic sampling, runtime fallback,
   debug provenance, replay, and neural rollout.
6. QA independent data/package/calibration/safety/CPU/rollout gates followed by
   Orchestrator M0-M4 regression, acceptance record, and publication.

## M4 activation record

- Accepted base: public
  `main@02b9e53b8ec11b06235be704dec7d5fcd7495945`.
- Integration branch: `codex/aitown-orch-m4`.
- Execution baseline: `docs/orchestration/M4_EXECUTION_BASELINE.md`.
- Model decision: ADR-0005, ADR-0012, and ADR-0013.
- Active online protocol remains exactly `0.3.0`; there is no M4 wire bump.
- Active internal feature/label versions are exactly `v0.1` / `v0.1`.
- Generated rows, checkpoints, weights, reports, and runs remain outside Git.

## M4 raw-data integration record

- Data contracts/generator source: `fc60364`, corrected snapshot `7eb0ba8`,
  grouped validator `abb9d92`, resumable matrix `8950d97`, bounded projection
  `42926be`, and isolated parallel scheduler `73ca45f`.
- Formal dataset source: `73ca45fa6de7708a2213db124633b419a62d6df9`;
  quality analyzer source: `881a023611ad3f7331c286fe88e78514b923982a`.
- Formal matrix: five fixed seeds, 499,978 rows, 71,636 decision groups,
  23 Parquet shards, train/validation/test 390,326/54,344/55,308, and 22/22
  behavior candidate coverage.
- Dataset manifest SHA-256:
  `e256ecf426d4d0b2ab4bfb63060873e88233c1aaeb14498cc536ef7f3161eccb`.
- Quality report SHA-256:
  `298f7dc159cace7c6a607324e90107ea10c117ebdf33a3c49a8d29855c0c5231`.
- Durable artifacts remain under `/root/autodl-fs/STWM/m4`; no rows, runs,
  weights, reports, caches, or credentials entered Git.

## M4 reviewed-anchor decision record

- ADR-0013 freezes exactly 300 approved anchors: 210 TRAIN, 30 VALIDATION, and
  60 ANCHOR_HOLDOUT across seven independent social-behavior batches.
- Anchor tasks retain immutable source feature/baseline-label hashes; Codex
  judgments, reviewer issues, and approval manifests are separate immutable
  artifacts with explicit producer/reviewer provenance.
- The approved overlay may replace only bounded soft targets for its named
  suite. Raw Parquet rows, heuristic ranking labels, public authority, M3, and
  protocol `0.3.0` remain unchanged.

## M4 anchor-task integration record

- Selector/validator sources: `75ba030` / `31211a7`.
- The external task packet contains exactly 300 canonical tasks with the frozen
  210/30/60 partition and independently regenerates from dataset manifest
  `e256ecf426d4d0b2ab4bfb63060873e88233c1aaeb14498cc536ef7f3161eccb`.
- Task JSONL SHA-256 is
  `d463506978f2b4671bfdabad07e70756d948ff672167059760e0b4120c10dc54`;
  validation report SHA-256 is
  `8c4dc2fbc060020076a360249ff9fa0d8d970d0cecdfb1b04c33f14ce3b6428f`.
- This record accepts task selection only. Judgment, review, approval, training
  overlay, and all neural gates remain pending.
