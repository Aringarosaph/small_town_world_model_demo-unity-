# Small Town World Model master plan

Public project name: **Small Town World Model（STWM，小镇世界模型）**. Existing
`AITOWN-*` task names remain stable internal compatibility identifiers.

## Governance

`AITOWN-ORCH` owns the single source of truth, dependency order, cross-thread contracts, integration gates, and release acceptance.

Long-term responsibility threads:

- `AITOWN-CONTRACTS`: schemas, configuration, catalogs, and protocol.
- `AITOWN-SIM`: authority state, actions, resolver, events, replay, and headless runtime.
- `AITOWN-UNITY`: Unity bridge, semantic assets, navigation, presentation, and debug UI.
- `AITOWN-MODEL`: anchors, data generation, training, evaluation, and inference packages.
- `AITOWN-DIALOGUE`: bounded DeepSeek interface, prompts, fixtures, and template fallback.
- `AITOWN-QA`: tests, observability, soak tests, golden chains, and release evidence.

## Milestones

| Milestone | Outcome | Entry gate | Exit gate |
|---|---|---|---|
| M0 | Frozen repository, contracts, configuration, protocol, CI | Producer specifications accepted | Config and schema validation pass without Unity or a model |
| M1 | One-NPC headless authority slice | M0 frozen | Three deterministic days, replayable and invariant-safe |
| M2 | One-NPC Unity bridge slice | M1 protocol stable | Home to work to home, navigation failures reported |
| M3 | Complete heuristic small society | M2 bridge stable | 10 NPCs, 22 behaviors, 30-day heuristic soak |
| M4 | Distilled social outcome model | M3 rules and features frozen | Neural gate, calibration, CPU inference, heuristic fallback |
| M5 | Bounded DeepSeek dialogue | Knowledge and SpeechPlan frozen | No knowledge leakage, async fallback, API-independent runtime |
| M6 | Golden-chain showcase | M3-M5 integrated | Automated replay, Unity preset, QA release checklist |

## Integration rule

Every change must land as a working vertical increment. Cross-thread contract changes require an ADR, version update, tests, and an updated handoff.

## Accepted milestones

M1 implements one active NPC in `HEADLESS_FAST` mode using only `idle`, `sleep`,
`eat_at_home`, and `work_shift`. Its accepted output is a deterministic three-day
run plus authoritative replay with matching final-state hash. The exact boundary
and gate live in `docs/orchestration/M1_EXECUTION_BASELINE.md`.

M2 implements and accepts the functional-greybox one-NPC Unity bridge slice
defined in `docs/orchestration/M2_EXECUTION_BASELINE.md`. Acceptance includes a
real Python `/town` WebSocket handshake, zero-skipped Unity EditMode/PlayMode,
external authority evidence, and passing remote Python gates. The producer
accepted reproducible local Unity batchmode evidence as the M2 release gate;
a licensed remote Unity lane is optional future infrastructure.

M3 is accepted and frozen at
`cc7f581da0548cb5aebd3d215db3e7bd93575d11` under
`docs/orchestration/M3_EXECUTION_BASELINE.md` and ADR-0011. It includes the
compatibility-preserving 10-NPC society runtime, protocol `0.3.0`, the full
functional greybox, deterministic background templates, fixed multi-seed
7/30-day heuristic soak, and strict external release evidence.

M4 was activated by the producer on 2026-08-04 under
`docs/orchestration/M4_EXECUTION_BASELINE.md` and ADR-0012. It is additive: the
current work is limited to bounded social Outcome Model features, reviewed
anchors, external data/training, evaluation, provider switching, local CPU
inference, and heuristic fallback. M5 DeepSeek and M6 release work remain closed.
