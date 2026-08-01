# Integration matrix

| Interface | Owner | Consumers | M0 artifact | Change gate |
|---|---|---|---|---|
| Domain IDs and enums | CONTRACTS | SIM, UNITY, MODEL, DIALOGUE, QA | Python DTOs and JSON Schema | Schema version + ADR |
| World configuration | CONTRACTS | SIM, MODEL, QA | `config/v0/` | Config hash + validation |
| Behavior/object catalogs | CONTRACTS | SIM, UNITY, MODEL, QA | YAML catalogs | Catalog version + coverage test |
| Message envelope | CONTRACTS | SIM, UNITY, QA | `protocol/` | Protocol semver + compatibility test |
| Authority transactions | SIM | UNITY, MODEL, QA | M1 | ADR + invariant tests |
| Semantic asset registry | UNITY | SIM, QA | M2 | Protocol update + Unity validation |
| OutcomeModel DTO | CONTRACTS | SIM, MODEL, QA | M0 protocol only | Feature/model version + regression |
| Knowledge/SpeechPlan | CONTRACTS | SIM, DIALOGUE, UNITY, QA | M0 schema | Schema + permission tests |
| Decision trace and run layout | QA | All | M0 docs/checks | Observability review |

## Merge order for M0

1. Orchestrator repository and ADR baseline.
2. Contracts configuration and validation.
3. QA/CI checks adapted to the integrated contract.
4. Full validation and M0 release commit.

