# Current status

## Milestone

`M0 - specifications and repository baseline`

## State

- Orchestrator thread: `AITOWN-ORCH`
- Contracts thread: M0 handoff integrated; retained as long-term owner
- QA thread: M0 handoff integrated; retained as long-term owner
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
- [ ] Push the accepted M0 baseline.

## Next gate

M1 may begin only after the accepted M0 commit is on `origin/main`. It is limited
to the one-NPC headless authority slice and must consume the frozen contracts.

## Blockers

None. Real DeepSeek credentials, Unity assets, and the cloud training host are intentionally not required in M0.
