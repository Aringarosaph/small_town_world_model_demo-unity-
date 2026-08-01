# M0 release checklist

## Repository

- [x] MIT license is present.
- [x] Remote is the authorized public GitHub repository.
- [x] Secrets, Unity caches, runs, generated data, and checkpoints are ignored.
- [x] Specification snapshots and source hashes are recorded.

## Frozen scope

- [x] Exactly 10 NPCs, 4 households, 8 locations, 22 behaviors, and 15 object types validate.
- [x] Five needs, four personality axes, two mood values, and four directed relationship values are defined.
- [x] Unity is pinned to `6000.4.2f1`.
- [x] Protocol, schema, feature, catalog, and prompt versions are explicit.

## Validation

- [x] Configuration loads without Unity, a model, or DeepSeek.
- [x] All cross references and value ranges validate.
- [x] JSON Schema and protocol examples validate.
- [x] Unit and QA tests pass on Python 3.12.
- [x] Ruff and mypy pass.
- [x] CI configuration is present.

## Governance

- [x] ADRs match implemented contracts.
- [x] Integration matrix is current.
- [x] CONTRACTS and QA handoffs are complete.
- [x] Appendix D hashes and manual sign-off are recorded.
- [x] No M1+ product logic is included.
