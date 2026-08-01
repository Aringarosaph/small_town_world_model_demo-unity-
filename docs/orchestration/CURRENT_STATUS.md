# Current status

## Milestone

`M1 - Headless hard-rule vertical slice (accepted on public main)`

## State

- Orchestrator thread: `AITOWN-ORCH`
- Contracts thread: M0 handoff integrated; retained as long-term owner
- QA thread: M1 QA handoff integrated; retained as long-term owner
- Simulation thread: M1 handoff integrated; retained as long-term owner
- Git branch: `main`
- Remote: `origin`
- Unity version: `6000.4.2f1`
- Training environment: deferred to M4 cloud validation
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

## Blockers

None. Real DeepSeek credentials, Unity assets, and the cloud training host are intentionally not required in M1.
