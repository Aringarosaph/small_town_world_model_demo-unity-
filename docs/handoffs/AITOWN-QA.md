# AITOWN-QA handoff

## Current responsibility

Long-lived QA/observability thread for milestone M0. This handoff covers only
CI, test conventions, repository/configuration acceptance, sensitive-file
diagnostics, freeze governance, and runtime evidence contracts.

## Completed since last handoff

- Added Python 3.12 GitHub Actions lanes for Ruff, strict Mypy, Pytest, baseline
  diagnostics, strict M0 readiness, and JSON diagnostic artifact upload.
- Established `qa`, `m0`, `integration`, `contract_pending`, and `slow` markers
  without editing CONTRACTS-owned `pyproject.toml`.
- Added readable owner-tagged checks for M0 repository structure, frozen scope,
  authoritative config loading, sensitive/generated files, and config/Schema
  freeze integrity.
- Added an actionable freeze generator. It records real integrated hashes but
  cannot auto-approve Appendix D.
- Documented the runtime `runs/` layout, structured log envelope, M0 acceptance,
  and explicit M1+ exclusions.

## Files changed

- `.github/workflows/python-ci.yml`
- `.github/requirements/qa.txt`
- `integration_tests/`
- `python/tests/qa/`
- `tools/diagnostics/`
- `docs/qa/`
- `docs/handoffs/AITOWN-QA.md`

No product logic, domain Schema, catalog, config, protocol, or
`pyproject.toml` file was changed.

## Interfaces changed

New diagnostic CLI:

```bash
python tools/diagnostics/check_m0.py [--check GROUP] \
  [--allow-pending-m0-inputs] [--json-output PATH]
```

Groups are `structure`, `sensitive`, `scope`, and `freeze`. Strict mode exits 1
on any failure. The parallel-development option downgrades only non-QA M0 input
failures to `PENDING`; secret and QA regressions remain fatal.

The default authoritative validation interface is:

```bash
python -m town_core.cli validate-config --config config/v0
```

If CONTRACTS chooses an equivalent command, set
`AITOWN_M0_CONFIG_VALIDATE_CMD` in the integrated workflow. Do not add a second
Schema implementation to QA.

New freeze preparation interface:

```bash
python -m tools.diagnostics.prepare_m0_freeze \
  --source-commit <integrated-contracts-commit>
```

## Tests added/run

Added isolated unit tests for path/content secret detection, explicit catalog
field extraction, valid freeze manifests, and hash drift. Added one strict
repository integration test marked `contract_pending` until all upstream M0
artifacts land.

Validation on Python 3.12.11:

- Ruff lint: passed;
- Ruff format check: passed;
- strict Mypy with explicit package bases: passed;
- fast Pytest lane: 14 passed, 1 `contract_pending` test deselected;
- pending-input diagnostic: 11 passed, 47 pending, 0 failed before the latest
  Orchestrator/CONTRACTS/Unity branches were integrated;
- strict diagnostic: 11 passed, 0 pending, 47 failed for those same missing
  upstream artifacts, as intended;
- strict Pytest lane: 14 passed and the single repository acceptance test failed
  on those readable upstream findings, as intended.

The full strict gate is intentionally not expected to pass before integration.

## Known limitations

- Catalog extraction assumes the explicit field names documented by the V0
  examples (`agent_id`/`npc_id`, `household_id`, `location_id`, `behavior_id`,
  `object_type`). If CONTRACTS freezes different names, update only the QA
  adapter after Orchestrator review; do not change product Schema from this
  thread.
- Token-presence checks for state dimensions and minimum events supplement, but
  do not replace, the authoritative config/Schema tests.
- Secret scanning is intentionally high-confidence and bounded to files under
  1 MB. It is a release guard, not a general-purpose credential scanner.
- The broad V0 Definition of Done is not an M0 gate. Later threads must add
  unit/property/integration/soak/golden-chain coverage with their capabilities.

## Pending decisions

- CONTRACTS should centralize equivalent pytest markers and tool settings in
  `pyproject.toml` after resolving its concurrent ownership; QA intentionally
  did not touch that file.
- Confirm whether the authoritative config command uses the recommended module
  path. If not, set `AITOWN_M0_CONFIG_VALIDATE_CMD` during integration.
- Confirm the CONTRACTS test paths. The gating CI lane executes all Python and
  integration tests; marking Schema/config coverage with `m0` still enables
  focused local runs and reporting.

## Next recommended task

After CONTRACTS and Orchestrator artifacts are merged:

1. run the pending-input diagnostic and resolve every adapter mismatch;
2. run the authoritative config and Schema tests;
3. generate `m0_config_freeze.json` from the integrated CONTRACTS commit;
4. have the Orchestrator manually review and sign every Appendix D item;
5. remove `contract_pending` from the full-repository acceptance test;
6. require both GitHub Actions jobs before declaring M0 complete.

## Blocking dependencies

Strict M0 acceptance waits for the integrated `pyproject.toml`, `config/v0`,
`protocol`, domain Schema, CONTRACTS tests/specs, Orchestrator records, Unity M0
directory skeleton, and the reviewed final freeze manifest. These are M0
artifacts, not requests for M1+ product logic.
