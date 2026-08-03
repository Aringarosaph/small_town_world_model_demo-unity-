# M3 release checklist

## Governance and compatibility

- [x] Producer authorizes M3.
- [x] M3 execution baseline and ADR-0011 are accepted.
- [x] Protocol `0.3.0` and the M3 contract re-freeze are integrated.
- [x] M0, M1, and M2 accepted gates remain green.

## Society authority

- [x] Exactly 10 NPCs participate in the society runtime.
- [x] All 22 behaviors pass targeted rule, lifecycle, and replay fixtures.
- [x] The same-snapshot central Resolver is deterministic and conflict-safe.
- [x] Household money/food conservation and exactly-once settlement pass.
- [x] All 90 directed relationship edges obey mask and direction rules.
- [x] Direct, witnessed, and told knowledge paths pass; unknown sharing fails.
- [x] Conversation and JointAction checkpoints resume and replay exactly.
- [x] Deterministic non-API background templates never produce an empty line.

## Unity functional greybox

- [x] The shared full-town semantic manifest passes Python and Unity gates.
- [x] 10 NpcViews, 8 locations, 15 object types, required capacities, props,
  facing, animations, and routes validate.
- [x] Multi-agent deltas, presentation binding, JointAction, and reconnect pass.
- [x] The read-only Debug UI displays complete M3 decision explanations.
- [x] EditMode, PlayMode, and live protocol `0.3.0` smoke have zero skips.

## Soak and release evidence

- [x] Five fixed 7-day heuristic runs pass.
- [x] Three fixed 30-day heuristic runs pass.
- [x] Chunk, repeat, checkpoint-resume, and authoritative replay hashes match.
- [x] Reservation, liveness, need, economy, relation, event, and memory pathology
  gates pass.
- [x] Performance targets pass on the recorded reference machine.
- [x] External `stwm.qa.m3-acceptance-evidence/v1` has no fail, pending, skip,
  or not-run gate.
- [x] Handoffs, README, status, integration record, and known issues are current.
- [x] AITOWN-ORCH accepts M3; publication of this acceptance commit to public
  `main` is the final release action.
