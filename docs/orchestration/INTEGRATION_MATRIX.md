# Integration matrix

| Interface | Owner | Consumers | M0 artifact | Change gate |
|---|---|---|---|---|
| Domain IDs and enums | CONTRACTS | SIM, UNITY, MODEL, DIALOGUE, QA | Python DTOs and JSON Schema | Schema version + ADR |
| World configuration | CONTRACTS | SIM, MODEL, QA | `config/v0/` | Config hash + validation |
| Behavior/object catalogs | CONTRACTS | SIM, UNITY, MODEL, QA | YAML catalogs | Catalog version + coverage test |
| Message envelope | CONTRACTS | SIM, UNITY, QA | Protocol `0.2.0`; `0.1.0` legacy decode | Protocol semver + compatibility test |
| Authority transactions | SIM | UNITY, MODEL, QA | M1 | ADR + invariant tests |
| Semantic asset registry | UNITY | SIM, QA | M2 scoped profile from ADR-0009 | Protocol update + Unity validation |
| Movement/presentation reports | CONTRACTS | SIM, UNITY, QA | Directional `0.2.0` DTO/Schema | ADR + direction/version/idempotency tests |
| OutcomeModel DTO | CONTRACTS | SIM, MODEL, QA | M0 protocol only | Feature/model version + regression |
| Knowledge/SpeechPlan | CONTRACTS | SIM, DIALOGUE, UNITY, QA | M0 schema | Schema + permission tests |
| Decision trace and run layout | QA | All | M0 docs/checks | Observability review |

## Merge order for M0

1. Orchestrator repository and ADR baseline.
2. Contracts configuration and validation.
3. QA/CI checks adapted to the integrated contract.
4. Full validation and M0 release commit.

## M0 integration record

- Orchestrator baseline: `d12450a`
- Environment lock baseline: `32cd848`
- QA handoff integrated: `23acf49`
- Contracts handoff integrated and frozen source: `9bc2051`
- Appendix D sign-off: `tools/diagnostics/m0_config_freeze.json`

The next writable product boundary is M1's authority runtime. All rows marked
with an M0 artifact are frozen inputs to that work.

## Merge order for M1

1. Orchestrator naming, scope, CLI, evidence, and acceptance baseline.
2. Simulation runtime, tests, run writer, Headless CLI, and replay CLI.
3. QA adapters and independent determinism/replay/invariant gates.
4. Full repository validation and an audited three-day run.
5. Public `main` push followed by both GitHub Actions gates.

## M1 integration record

- Public naming and execution baseline: `a8c23b8`
- Simulation runtime handoff: source `2afad99`, integrated as `7b59c0c`
- Independent QA handoff: source `99da488`, integrated as `4b19cdd`
- Work attendance semantics: ADR-0008
- Final strict gate: `tools/diagnostics/check_m1.py --require-sim`
- Orchestrator acceptance commit: `3d43c15`
- GitHub Actions acceptance run: `30722721963` (all three jobs passed)

## M2 protocol integration record

- M2 functional-greybox and scoped-registry baseline: ADR-0009 / `0a4caa1`
- Movement cancellation and protocol `0.2.0`: ADR-0010 / `392f941`
- Additive formatted source consumed by the re-freeze: `247711a`
- Active M2 acceptance version: exactly `0.2.0`
- Legacy compatibility: `0.1.0` bootstrap/decode tests only; no cancellation gate
- Heartbeat: WebSocket ping/pong; no JSON message
- Reconnect: full hello/registry/snapshot/ready sequence; no resync JSON message
- Authority direction: Unity reports `movement_cancelled`; only Python emits the
  committed `action_cancelled`
- Evidence naming: M2 sessions record `catalog_protocol_version` separately from
  `negotiated_protocol_version`
- Freeze gate: protocol/domain changes require the ADR-0010 M2 re-freeze manifest;
  the original M0 `0.1.0` source evidence remains recorded
