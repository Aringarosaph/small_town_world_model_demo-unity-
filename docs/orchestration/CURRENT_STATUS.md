# Current status

## Milestone

`M1 - Headless hard-rule vertical slice (active)`

## State

- Orchestrator thread: `AITOWN-ORCH`
- Contracts thread: M0 handoff integrated; retained as long-term owner
- QA thread: M0 handoff integrated; retained as long-term owner
- Simulation thread: `AITOWN-SIM`, active for M1
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

## Next gate

M1 exits only when one active NPC runs three deterministic game days without an
illegal state, produces complete structured decision/action/event/transaction
evidence, and authoritative replay reaches the identical final-state hash.

## M1 in progress

- [x] Accept M0 on public `origin/main`.
- [x] Freeze the M1 execution and acceptance boundary.
- [x] Activate `AITOWN-SIM` and `AITOWN-QA` for M1.
- [ ] Integrate the Headless authority runtime and CLI.
- [ ] Integrate deterministic/replay QA gates.
- [ ] Pass local and GitHub M1 acceptance.
- [ ] Push the accepted M1 baseline.

## Blockers

None. Real DeepSeek credentials, Unity assets, and the cloud training host are intentionally not required in M0.
