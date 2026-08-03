# M3 acceptance record

Status: accepted and frozen by AITOWN-ORCH on 2026-08-03.

## Accepted boundary

- Accepted implementation commit:
  `cc7f581da0548cb5aebd3d215db3e7bd93575d11`.
- Accepted base: public
  `main@7b2618de09bd87eb49716ac40f1d0ba697f00351`.
- Product surface: 10 NPCs, 4 households, 8 locations, 22 behaviors,
  15 semantic object types, 74 semantic objects, and 90 directed
  relationship edges.
- Runtime: the complete deterministic `HeuristicOutcomeModel` society,
  central Resolver and JointAction authority, versioned checkpoints, and
  authoritative replay.
- Online presentation: protocol `0.3.0`, `M3_FULL` registry, full-town Unity
  functional greybox, structured multiplayer presentation, reconnect, and
  read-only decision explanations.
- Compatibility: accepted M1 and M2 execution profiles remain intact; M2
  acceptance continues to negotiate exactly protocol `0.2.0`.

M4 neural inference/training, M5 DeepSeek, M6 golden-chain publication, final
art, and all post-V0 roadmap systems are outside this acceptance.

## Release matrix

The release producer ran one job at a time on the producer Apple-silicon
MacBook Air. It completed:

- canonical seven-day run, same-seed repeat, and chunk sizes `1`, `7`, `60`;
- five fixed seven-day seeds;
- three fixed thirty-day seeds;
- a checkpoint every six game hours;
- deterministic resume and authoritative replay for every release run.

All 11 release jobs completed. Every replay matched the final state, ledger,
authority log, and checkpoint chain. No release job modified its source run.

## Society results

- All 10 configured NPCs participate in scheduling, decisions, settlement,
  event visibility, and replay.
- All 22 behaviors pass their targeted authority matrix and occur naturally in
  the release soaks. The rarest natural counts are
  `end_conversation=1`, `drink_at_bar=3`, and `invite_join=7`.
- JointAction includes a real accepted invitation and real rejected
  invitations, central resolution, participant exclusivity, atomic reservation,
  cancel/failure/timeout release, and matching replay.
- Household money and food conservation, wages and costs exactly once,
  relation direction/masks, direct/witnessed/told knowledge, unknown-share
  rejection, and deterministic non-empty background dialogue all pass.
- Pathology totals are zero for duplicate semantic events, reservation leaks,
  slot conflicts, permanent-idle agents, work-bound violations, unrecovered
  households, and relationship-boundary violations.
- Maximum recoverable zero-need interval is 353 game minutes against the
  frozen 360-minute maximum.

## Performance results

The worst observed release values remain inside the frozen M3 limits:

| Metric | Worst observed |
|---|---:|
| Thirty-day wall time | 613.696061 seconds |
| Peak RSS | 83,738,624 bytes |
| RSS slope | 664,443.187542 bytes/game-day |
| Tick p99 | 21.677417 ms |
| Decision batch p95 | 0.827917 ms |
| Maximum candidates per agent | 12 |
| Maximum decision batch | 120 |

## Unity results

The final evidence was regenerated against the exact accepted source commit
with Unity `6000.4.2f1`:

- EditMode: 72 passed, 0 failed, 0 skipped, 0 inconclusive;
- production `/town` PlayMode: 6 passed, 0 failed, 0 skipped,
  0 inconclusive;
- 22 authoritative behavior-presentation rows each map to a real passing test;
- `M3_FULL`: 8 locations, 10 NpcViews, 74 objects, 15 object types, 105 slots,
  14 animation semantics, and 840 routes, with 0 blocking issues;
- real protocol `0.3.0` hello, registry, snapshot, ready, Top-K decision trace,
  reconnect, stale rejection, and JointAction presentation all pass;
- the Python authority remains the only writer of simulation state.

## Repository and final gates

- Focused M3 validation: 213 passed, 1 expected external-evidence skip.
- Full Python repository validation: 456 passed, 2 expected external-evidence
  skips, 2 loopback tests run separately and passed.
- Ruff format/lint and strict Mypy pass.
- M0-M2 regression manifest: `PASS`.
- Final `check_m3.py --require-m3`: 19 pass, 0 pending, 0 fail.
- Final assembled schema: `stwm.qa.m3-acceptance-evidence/v1`.

## External evidence ledger

The release artifacts are machine-local evidence, not Git content. Raw runs,
Unity XML/logs, and generated bundles remain outside the repository.

Evidence root:
`/private/tmp/stwm-m3-final5-evidence-cc7f581`

| Artifact | SHA-256 | Bytes |
|---|---|---:|
| `sim/bundle-manifest.json` | `26d8bb3649db5c2a88abe0d336b5c5aa93fe7398adecb2c2fe930c342861e2ce` | 2,345 |
| `unity/m3-unity-partial-acceptance-evidence.json` | `9cc571dd61dcca5f27a3d17ecdec3e0d094ec53e30dceca6361839e52006d6f5` | 14,119 |
| `repository/m3-readiness.json` | `faef6ee2c2031a7a50f5843a98ced081d08c90043c8ffab5e535ba8ad1897cdd` | 6,166 |
| `repository/m0-m2-regressions/m0-m2-regression-manifest.json` | `6d4c64772ceeba851d9828dc8bcedb5d5e4e1ea06d8b6b523f235fb7a4c27cdc` | 6,192 |
| `final/m3-acceptance-evidence.json` | `fae795c7855b3a00c084fac10befd23505cfe508c96a06f63f55a6fd7286b59d` | 34,780 |
| `final/final-validation.json` | `d6c612c2e405a597738af5750b422d24980e3cdb22dd145d33214b0a940d8e83` | 6,181 |

The evidence-bound registry copy is
`final/artifacts/full_registry.json`. Its descriptor is part of the final
acceptance document, so the strict registry/evidence path binding is preserved.

## Acceptance

AITOWN-ORCH accepts M3 as implemented, verified, replayable, and frozen at the
commit above. Any change to this product boundary requires an ADR where
applicable, compatibility review, regenerated owner evidence, and a new
Orchestrator acceptance. M4 remains inactive until a separate execution
baseline is explicitly authorized.
