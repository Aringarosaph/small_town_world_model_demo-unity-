# M0 acceptance: specification and repository baseline

## Decision

M0 establishes frozen contracts and a validation baseline. It does not require
simulation product logic. Strict M0 acceptance is green only when all automated
checks below pass and the Orchestrator has reviewed the final freeze manifest.

Authoritative inputs are the V0 implementation specification (M0, testing,
Definition of Done, and Appendix D) and the long-term roadmap's governance
principles. The roadmap is a constraint and future candidate pool, not an M0
backlog.

## Automated acceptance

| Area | M0 evidence | Gate |
| --- | --- | --- |
| Python CI | Python 3.12; Ruff lint/format; strict Mypy; Pytest | Required |
| Repository baseline | CONTRACTS, protocol, domain Schema, orchestration, Unity skeleton, and QA paths exist | Required |
| Configuration | Authoritative config validator loads all `config/v0` data without Unity or model runtime | Required |
| Frozen catalogs | Exactly 10 NPCs, 4 households, 8 locations, 22 behaviors, and 15 object types | Required |
| Frozen state surface | Five needs, four personality axes, two mood axes, four directed relationship axes | Required |
| Event baseline | All V0 minimum event types are present; compatible correction events may be additional | Required |
| Schema/protocol | Versioned domain Schema, JSON Schema/examples, and protocol version are present; CONTRACTS M0 tests pass | Required |
| Sensitive/generated files | No credentials, private keys, runtime logs, generated datasets, model binaries/checkpoints, LLM caches, or Unity-generated trees are candidates for commit | Required |
| Freeze integrity | Hash coverage for effective config, protocol, and domain Schema; every Appendix D item manually approved | Required |
| QA evidence | Runs and log contracts, marker conventions, diagnostics, machine-readable report, and handoff are present | Required |

The catalog scanner reads only explicit ID fields and frozen public values. It
does not parse or redefine product Schema. The authoritative config loader is
the final judge of field types, references, ranges, and cross-file validity.

## Orchestrator freeze procedure

After merging the final CONTRACTS input, run:

```bash
python -m tools.diagnostics.prepare_m0_freeze \
  --source-commit <integrated-contracts-commit>
```

This produces `tools/diagnostics/m0_config_freeze.json` with real hashes and all
governance checklist values set to `false`. The Orchestrator must review the V0
Appendix D items, fill `approved_by` and `approved_at_utc`, and turn only verified
items to `true`. There is intentionally no automatic approval command.

Run strict acceptance after review:

```bash
python tools/diagnostics/check_m0.py \
  --json-output runs/qa-m0/m0-diagnostics.json
pytest --strict-config --strict-markers -m "m0" python/tests integration_tests
```

During parallel M0 work only, the following lane permits upstream-owned absences
as visible `PENDING` findings while still failing any QA or sensitive-file
regression:

```bash
python tools/diagnostics/check_m0.py --allow-pending-m0-inputs
pytest --strict-config --strict-markers \
  -m "not contract_pending" python/tests/qa integration_tests
```

`--allow-pending-m0-inputs` is not an M0 acceptance result.

## Manual acceptance

The Orchestrator confirms:

- Appendix D is reviewed against authoritative artifacts, not chat context;
- the repository's documented non-goals cover V0 exclusions;
- any change to a frozen ID, direction, range, protocol, or semantic carries an
  ADR and an intentionally regenerated freeze;
- handoffs and orchestration status describe the same integrated commit;
- no cross-thread interface exists only in conversation history.

## Explicit non-requirements for M0

M0 must not be blocked on any of the following product capabilities:

- M1: simulation clock, resolver, action lifecycle, headless run/replay, needs,
  work, wages, or a three-day single-NPC slice;
- M2: live WebSocket/Unity handshake, asset registration behavior, navigation,
  animation execution, or reconnect behavior;
- M3: implemented 10-NPC society, all behavior execution, economy loop, social
  propagation, or a 30-day heuristic soak test;
- M4: training data, neural model, model evaluation, or model switching;
- M5: live DeepSeek calls, dialogue behavior, or runtime fallback;
- M6: automated golden chain, Unity demonstration preset, or release soak.

M0 freezes the catalogs, DTOs, configuration, protocol, semantic names, and
future test boundaries needed by those milestones; it does not implement them.
