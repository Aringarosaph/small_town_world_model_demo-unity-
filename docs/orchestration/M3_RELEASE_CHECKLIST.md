# M3 release checklist

## Governance and compatibility

- [x] Producer authorizes M3.
- [x] M3 execution baseline and ADR-0011 are accepted.
- [ ] Protocol `0.3.0` and the M3 contract re-freeze are integrated.
- [ ] M0, M1, and M2 accepted gates remain green.

## Society authority

- [ ] Exactly 10 NPCs participate in the society runtime.
- [ ] All 22 behaviors pass targeted rule, lifecycle, and replay fixtures.
- [ ] The same-snapshot central Resolver is deterministic and conflict-safe.
- [ ] Household money/food conservation and exactly-once settlement pass.
- [ ] All 90 directed relationship edges obey mask and direction rules.
- [ ] Direct, witnessed, and told knowledge paths pass; unknown sharing fails.
- [ ] Conversation and JointAction checkpoints resume and replay exactly.
- [ ] Deterministic non-API background templates never produce an empty line.

## Unity functional greybox

- [ ] The shared full-town semantic manifest passes Python and Unity gates.
- [ ] 10 NpcViews, 8 locations, 15 object types, required capacities, props,
  facing, animations, and routes validate.
- [ ] Multi-agent deltas, presentation binding, JointAction, and reconnect pass.
- [ ] The read-only Debug UI displays complete M3 decision explanations.
- [ ] EditMode, PlayMode, and live protocol `0.3.0` smoke have zero skips.

## Soak and release evidence

- [ ] Five fixed 7-day heuristic runs pass.
- [ ] Three fixed 30-day heuristic runs pass.
- [ ] Chunk, repeat, checkpoint-resume, and authoritative replay hashes match.
- [ ] Reservation, liveness, need, economy, relation, event, and memory pathology
  gates pass.
- [ ] Performance targets pass on the recorded reference machine.
- [ ] External `stwm.qa.m3-acceptance-evidence/v1` has no fail, pending, skip,
  or not-run gate.
- [ ] Handoffs, README, status, integration record, and known issues are current.
- [ ] Producer accepts M3 and the accepted history is published to public `main`.

