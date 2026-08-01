# M0 release checklist

## Repository

- [ ] MIT license is present.
- [ ] Remote is the authorized public GitHub repository.
- [ ] Secrets, Unity caches, runs, generated data, and checkpoints are ignored.
- [ ] Specification snapshots and source hashes are recorded.

## Frozen scope

- [ ] Exactly 10 NPCs, 4 households, 8 locations, 22 behaviors, and 15 object types validate.
- [ ] Five needs, four personality axes, two mood values, and four directed relationship values are defined.
- [ ] Unity is pinned to `6000.4.2f1`.
- [ ] Protocol, schema, feature, catalog, and prompt versions are explicit.

## Validation

- [ ] Configuration loads without Unity, a model, or DeepSeek.
- [ ] All cross references and value ranges validate.
- [ ] JSON Schema and protocol examples validate.
- [ ] Unit and QA tests pass on Python 3.12.
- [ ] Ruff and mypy pass.
- [ ] CI configuration is present.

## Governance

- [ ] ADRs match implemented contracts.
- [ ] Integration matrix is current.
- [ ] CONTRACTS and QA handoffs are complete.
- [ ] No M1+ product logic is included.

