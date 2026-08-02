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
- [x] The first public `main` run passes both remote CI jobs.

## Governance

- [x] ADRs match implemented contracts.
- [x] Integration matrix is current.
- [x] CONTRACTS and QA handoffs are complete.
- [x] Appendix D hashes and manual sign-off are recorded.
- [x] No M1+ product logic is included.

# M2 release checklist

## Runtime and authority

- [x] Python remains the only authority; Unity reports presentation outcomes only.
- [x] Protocol `0.2.0`, direction schemas, cancellation, dedupe, and correlation pass.
- [x] Reconnect repeats hello/registry/snapshot/ready with a new generation.
- [x] Exact-match stale cancellation commits once; terminal/nonmatching stale is zero-mutation resync.

## Unity functional greybox

- [x] Unity Editor is pinned to `6000.4.2f1` and package versions are locked.
- [x] The primitive-only M2 scene and NavMesh rebuild reproducibly.
- [x] The scoped asset registry accepts `npc_01`, `home_a`, `cafe_bar`, and required slots.
- [x] EditMode passes 26/26 with zero skipped tests.
- [x] PlayMode passes 4/4 with zero skipped tests, including the live `/town` smoke.

## Integrated validation

- [x] Python tests pass 123/123 and integration tests pass 7/7.
- [x] M0, M1, and M2 strict local diagnostics have zero pending/fail results.
- [x] Ruff lint/format and strict Mypy pass.
- [x] Final evidence is external, redacted, and tied to the integration commit.
- [x] Remote Python CI passes for the M2 branch (run `30749456317`).
- [x] The producer accepts reproducible local zero-skipped batchmode and live
  interoperability evidence as the M2 Unity publication gate.
- [x] The accepted M2 history is published to public `main`.
