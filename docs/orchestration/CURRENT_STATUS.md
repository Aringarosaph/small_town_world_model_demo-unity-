# Current status

## Milestone

`M2 - One-NPC Unity Bridge functional-greybox slice (accepted)`

## State

- Orchestrator thread: `AITOWN-ORCH`
- Contracts thread: M2 delivery complete; available for compatibility review
- QA thread: M2 local and remote Python gates complete
- Simulation thread: M2 Python bridge and authority evidence complete
- Unity thread: M2 client, greybox, evidence exporter, and tests complete
- Accepted branch: public `main`
- Source integration branch: `codex/aitown-orch-m2`
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

## Blockers

None. M3 remains inactive until a separate producer authorization and
Orchestrator handoff. Final art, DeepSeek credentials, and the cloud training
host remain intentionally out of scope.
