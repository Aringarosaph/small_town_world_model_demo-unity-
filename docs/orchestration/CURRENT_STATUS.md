# Current status

## Milestone

`M4 - Distilled social outcome model (active: execution baseline)`

## State

- Orchestrator thread: `AITOWN-ORCH`
- Contracts thread: standby; M4 uses additive Python-private contracts under ADR-0012
- QA thread: standby pending M4 contracts/evidence increment
- Simulation thread: standby pending injected OutcomeModel increment
- Unity thread: standby after accepted full-town functional greybox
- Model responsibility: active under `AITOWN-ORCH`; separate task deferred during quota-constrained entry
- Accepted base branch: public `main`
- Active integration branch: `codex/aitown-orch-m4`
- Remote: `origin`
- Unity version: `6000.4.2f1`
- Training environment: AutoDL RTX 4090 entry audit passed; 50GB local data and 200GB file storage mounted
- DeepSeek: deferred to M5; `.env` secret not present in the repository

## M0 complete

- [x] Initialize Git and connect the authorized empty remote.
- [x] Add MIT license and repository ignore baseline.
- [x] Import authoritative specification snapshots.
- [x] Record initial architecture decisions.
- [x] Integrate configuration, catalogs, DTOs, and protocol.
- [x] Integrate CI and QA acceptance checks.
- [x] Review and sign the Appendix D freeze manifest.
- [x] Run all M0 validation: 28 tests and 58 diagnostics passed.
- [x] Push the accepted M0 baseline to `origin/main`.
- [x] Pass GitHub Actions `QA baseline` and `M0 readiness` on integration commit `a5ee1af`.

## M1 acceptance result

- Exactly one active NPC (`npc_01`) runs from minute 0 to 4320.
- Only `idle`, `sleep`, `eat_at_home`, and `work_shift` are available.
- Baseline, repeat, 7-minute chunks, and 60-minute chunks reach identical final
  state and four-log authority hashes.
- Replay applies ordered authority transactions without recomputing policy and
  reaches the recorded final-state hash.
- Normal, late-within-grace, and missed work sessions produce the expected
  events and exactly-once wage results.
- M0 frozen configuration, protocol, and domain DTOs remain unchanged.
- Local integration validation: 64 tests, 58/58 M0 diagnostics, 15/15 M1
  diagnostics, Ruff, format, and strict Mypy all pass on Python 3.12.11.
- Accepted final-state hash:
  `dda5aae504b65700c2a6e2da4386ee6dab022ee8792917887c7bf905960e3cbd`.
- Accepted four-log authority hash:
  `a0268e4f88b1b861959fa26137d73c656b8c3d1ab5d4b1590b124844d7487297`.
- GitHub Actions run `30722721963` passed `QA baseline`, `M0 readiness`, and
  `M1 QA readiness` for acceptance commit `3d43c15`.

## M1 completion

- [x] Accept M0 on public `origin/main`.
- [x] Freeze the M1 execution and acceptance boundary.
- [x] Activate `AITOWN-SIM` and `AITOWN-QA` for M1.
- [x] Integrate the Headless authority runtime and CLI.
- [x] Integrate deterministic/replay QA gates.
- [x] Pass local M1 acceptance.
- [x] Pass GitHub M1 acceptance and push the accepted M1 baseline.

## M2 completion

- [x] Producer authorized M2 and selected the functional-greybox route.
- [x] Unity Hub login and Personal license confirmed by the producer.
- [x] Editor `6000.4.2f1` and sufficient local disk space verified.
- [x] Freeze the one-NPC slice and scoped asset-validation policy.
- [x] Activate CONTRACTS, SIM, QA, and UNITY ownership.
- [x] Freeze exact Unity package versions after the controlled first import.
- [x] Integrate the Python bridge adapter and authority evidence test port.
- [x] Integrate the Unity bridge, semantic components, greybox fixture, and exporter.
- [x] Pass local M2 acceptance with real `/town` interoperability.
- [x] Push the M2 integration branch and pass remote Python CI.
- [x] Producer accepted reproducible local batchmode evidence as the M2 Unity
  release gate; a licensed remote Unity lane is optional future infrastructure.
- [x] Fast-forward the accepted M2 history to public `main`.

## M2 acceptance result

- Protocol `0.2.0` handshake, directional messages, registry, full snapshot,
  readiness, cancellation, reconnect generations, and resynchronization pass.
- Unity EditMode: 26 passed, 0 skipped.
- Unity PlayMode: 4 passed, 0 skipped, including the production `/town` live smoke.
- Python tests: 123 passed; integration tests: 7 passed.
- Diagnostics: M0 58/58, M1 15/15, M2 19/19; M2 has 26 allowed M3-debt warnings,
  0 pending, and 0 failures.
- Ruff format/lint and strict Mypy pass; the final authority state hash is
  `f0859d472a8ca7bbdd34393f75c342cfe16f84cb04deab38674bc92e9300aa6c`.
- Final evidence was regenerated outside the repository against integration
  commit `6b5b7d05c79186e0cd8f4b57fbd9552bfa54cbd1`.
- GitHub Actions runs `30749456317` and `30749720664` passed QA baseline, M0 readiness, M1 QA
  readiness, and M2 QA readiness after the M2 ancestry gate fetched full history.
- On 2026-08-02 the producer accepted the reproducible local Unity evidence as
  the M2 release gate. This closes M2 without requiring a remote Unity license.

## M3 completion

- [x] Producer authorized M3 on 2026-08-02.
- [x] Entry audits completed for CONTRACTS, SIM, QA, and UNITY.
- [x] Freeze `docs/orchestration/M3_EXECUTION_BASELINE.md`.
- [x] Accept ADR-0011: compatibility profiles, M3 AuthorityCheckpoint, and
  additive protocol `0.3.0`.
- [x] Freeze fixed 7/30-day seed lists, pathology/performance thresholds, and
  the full-town semantic capacity policy.
- [x] Integrate CONTRACTS protocol/catalog artifacts and re-freeze.
- [x] Integrate the ten-NPC heuristic society runtime and M3 replay.
- [x] Integrate independent M3 QA readiness and release evidence gates.
- [x] Integrate the full-town Unity greybox and multiplayer presentation.
- [x] Pass fixed multi-seed soak and local zero-skipped Unity batchmode.
- [x] Pass the strict final M3 gate: 19 pass, 0 pending, 0 fail.
- [x] Accept implementation commit
  `cc7f581da0548cb5aebd3d215db3e7bd93575d11` as the frozen M3 product boundary.

## M3 acceptance result

- Exact surface: 10 NPCs, 4 households, 8 locations, 22 behaviors, 15 object
  types, and 90 directed relationship edges.
- Release matrix: five fixed 7-day runs, three fixed 30-day runs, and canonical
  repeat/chunks `1`, `7`, and `60`; every run replays to matching state,
  checkpoint, ledger, and authority hashes.
- All 22 behaviors occur naturally in release soaks and pass eight targeted
  SIM probes; the rarest accepted counts include `end_conversation=1`,
  `drink_at_bar=3`, and `invite_join=7`.
- JointAction covers real invitation acceptance and rejection, central
  resolution, participant exclusivity, atomic reservations, cancel/fail/timeout
  release, zero split actions, and matching replay.
- Pathology result: 0 duplicate semantic events, reservation leaks, slot
  conflicts, permanent-idle agents, work-bound violations, unrecovered
  households, or relationship-boundary violations. Maximum recoverable
  zero-need interval is 353 minutes against the 360-minute limit.
- Worst recorded 30-day performance on the producer Apple-silicon MacBook Air:
  613.696061 seconds wall time, 83,738,624 bytes peak RSS, 664,443.187542
  bytes/game-day RSS slope, 21.677417 ms tick p99, and 0.827917 ms decision
  batch p95.
- Unity `6000.4.2f1`: EditMode 72/72 and real production `/town` PlayMode 6/6,
  both with zero skipped, failed, or inconclusive tests. The M3_FULL registry
  covers 8 locations, 10 NPC views, 74 objects, 15 types, 105 slots, 14
  animation semantics, and 840 routes with zero blocking issues.
- M0-M2 strict regressions pass and the final M3 diagnostic reports 19 pass,
  0 pending, and 0 fail.
- The external acceptance evidence and its hashes are recorded in
  `docs/orchestration/M3_ACCEPTANCE_RECORD.md`; raw runs remain outside Git.

## M3 frozen boundary

- M3 activates exactly 10 NPCs, 22 behaviors, 4 households, 8 locations,
  15 object types, and 90 directed relationship edges.
- The accepted M3 profile continues to use only the deterministic HeuristicOutcomeModel.
- Protocol `0.3.0` is mandatory for M3; protocol `0.2.0` remains the immutable
  M2 compatibility profile.
- M3 includes deterministic background templates but no DeepSeek or player
  language authority.
- M4 may consume this boundary but cannot change its hard authority or accepted
  heuristic behavior. M5 DeepSeek and M6 golden-chain release remain closed.

## M4 activation

- [x] Producer authorized M4 on 2026-08-04.
- [x] Create integration branch `codex/aitown-orch-m4` from accepted public main.
- [x] Audit SSH, RTX 4090/CUDA/PyTorch, real container limits, GitHub access,
  local data storage, and restart-persistent file storage.
- [x] Accept ADR-0012 and freeze `docs/orchestration/M4_EXECUTION_BASELINE.md`.
- [x] Freeze feature/label/package identities, grouped splits, model/fallback
  authority, metrics, external artifact ownership, and quota-safe pause points.
- [ ] Implement M4 contracts, postprocessor, provider protocol, recorded and
  heuristic providers, schemas, and focused tests.
- [ ] Implement resumable grouped dataset generation and reviewed anchor flow.
- [ ] Implement/train/evaluate the 1M-3M TorchOutcomeModel.
- [ ] Integrate provider switching, deterministic neural sampling, fallback,
  CPU inference, neural rollout, QA evidence, and M0-M3 regressions.

## M4 entry result

- Cloud: Ubuntu 22.04, Python 3.12.3, PyTorch 2.5.1+cu124, CUDA 12.4,
  RTX 4090 24GB, BF16 and CUDA smoke passed.
- Limits: 16 CPU, 120GB RAM, 30GB system disk, 50GB local data disk, and
  mounted read/write 200GB file storage.
- Cloud repository: `/root/autodl-tmp/STWM` at public
  `main@02b9e53b8ec11b06235be704dec7d5fcd7495945`, clean at entry.
- Durable M4 root: `/root/autodl-fs/STWM/m4`; generated data/weights remain
  external and hash-addressed.
- Account quota at activation was read as 90% used / about 10% remaining.
  Work must close an atomic increment and pause before exhaustion; manual reset
  credits are not consumed without producer approval.

## Blockers

No M3 blocker remains. M4 entry infrastructure and policy are ready. The next
dependency is the M4 internal contracts/provider increment; dataset generation
and training remain intentionally gated behind it. DeepSeek remains deferred to
M5, and final art remains outside the functional-greybox acceptance boundary.
