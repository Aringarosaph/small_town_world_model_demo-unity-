# M1 release checklist

## Authority runtime

- [x] Exactly `npc_01` is enabled; the other nine NPC records remain immutable.
- [x] The authority clock commits exactly one transaction per game minute.
- [x] M1 exposes only `idle`, `sleep`, `eat_at_home`, and `work_shift`.
- [x] Utility selection and tie-breaking are deterministic for seed and state.
- [x] Resolver validation owns versions, resources, locations, and exclusive slots.
- [x] Needs and mood remain in range; household money and food remain non-negative.
- [x] Actions follow the exclusive lifecycle and release reservations.
- [x] Event records are append-only and monotonically ordered.

## Work and economy

- [x] Attendance is tracked per schedule occurrence, independently of actions.
- [x] Normal, late-within-grace, and missed outcomes are executable.
- [x] Completion and one fixed wage settle atomically and exactly once.
- [x] Missed work emits `WORK_MISSED` and pays nothing.

## Evidence and replay

- [x] Every run contains metadata, config snapshot, initial/final snapshots,
  decisions, actions, transactions, events, and summary.
- [x] Baseline, repeat, chunk-7, and chunk-60 runs have identical initial/final
  state and four-log authority hashes.
- [x] Replay applies ordered authority patches without rerunning decision policy.
- [x] Replay verifies transaction hashes, final snapshot, all four authority
  logs, invariants, and source-run immutability.
- [x] Damaged replay and six invalid-state probes fail without authority mutation.

## Repository gates

- [x] M0 freeze diagnostics remain fully green.
- [x] All 64 Python 3.12 tests, Ruff, format, and strict Mypy pass locally.
- [x] Generated runs and evidence remain outside Git.
- [x] M1 QA reports 15 pass, zero pending, and zero failures locally.
- [x] GitHub Actions passes the integrated M1 commit.
- [x] The accepted M1 commit is pushed to public `origin/main`.
