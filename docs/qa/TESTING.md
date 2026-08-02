# Test layout and markers

## Directory ownership

- `python/tests/qa/`: isolated tests for QA diagnostics, policies, and report
  formatting.
- `integration_tests/`: cross-boundary acceptance tests. M0 covers repository,
  frozen catalogs/protocol and sensitive files; M1 adds the Headless authority
  and replay adapter; M2 adds the gray-box protocol/Unity evidence adapter; M3
  adds the full heuristic-society readiness and external release adapter.
- Future product-unit suites live under the owning subsystem's path, for
  example `python/tests/simulation/`. QA does not create those suites before
  their milestone exists.

## Markers

| Marker | Meaning |
| --- | --- |
| `qa` | QA-owned validation or regression coverage |
| `m0` | M0 acceptance coverage only |
| `m1` | M1 one-NPC Headless authority acceptance |
| `m2` | M2 one-NPC Unity bridge gray-box acceptance |
| `m3` | M3 complete heuristic-society acceptance |
| `m3_fast` | M3 readiness checks that do not execute release soaks |
| `m3_slow` | Fixed-seed M3 soak or reference performance work |
| `society` | Ten-agent liveness and authority coverage |
| `full_registry` | Shared full-town manifest/registry coverage |
| `joint_action` | Central JointAction atomicity and release coverage |
| `soak7` | Fixed seven-game-day release evidence |
| `soak30` | Fixed thirty-game-day release evidence |
| `performance` | Reference-machine M3 performance evidence |
| `integration` | Crosses a package, process, protocol, or repository boundary |
| `contract_pending` | Executable check waiting for an upstream M0 artifact |
| `sim_pending` | May skip only while the complete M1 SIM runtime is absent |
| `unity_pending` | May skip only while the complete M2 Unity runtime/evidence is absent |
| `headless` | Executes or validates the Headless authority runtime |
| `determinism` | Same-seed and tick-chunk equivalence checks |
| `replay` | Snapshot plus committed-transaction authority replay |
| `invariant` | Illegal authority-state rejection and safety invariants |
| `protocol` | Versioned Python/Unity protocol and direction coverage |
| `unity` | Unity-owned runtime or exported evidence coverage |
| `graybox` | ADR-0009 no-art functional slice coverage |
| `batchmode` | Unity batchmode execution or evidence validation |
| `slow` | Excluded from the default fast lane |

M0/M1 markers are registered centrally in `pyproject.toml`. QA registers the
additive M3 markers in its local `conftest.py` files so this branch does not edit
shared project configuration while CONTRACTS owns the protocol 0.3 re-freeze.
Orchestrator should centralize the same names during integration.

`sim_pending` is not an `xfail`. It permits one explicit skip only while none of
the SIM runtime packages is present. Partial integration, adapter failure, or
invalid evidence fails normally.

`unity_pending` follows the same rule: complete absence may skip the adapter;
partial Unity integration, protocol mismatch, malformed evidence, or a failed
runtime assertion fails normally. The final `--require-m2` gate cannot skip or
remain pending.

## Lanes

Fast QA-owned regression:

```bash
pytest --strict-config --strict-markers \
  -m "not contract_pending and not m1 and not m2" python/tests/qa integration_tests
```

Full M0 readiness:

```bash
uv run --no-editable pytest --strict-config --strict-markers \
  -m "not m1 and not m2" python/tests integration_tests
uv run --no-editable python tools/diagnostics/check_m0.py
```

M1 black-box selection:

```bash
pytest --strict-config --strict-markers -m m1 integration_tests
```

M2 gray-box selection:

```bash
pytest --strict-config --strict-markers -m m2 integration_tests
python tools/diagnostics/check_m2.py \
  --registry integration_tests/fixtures/m2/m2-slice-valid.json
```

M3 fast readiness selection:

```bash
pytest --strict-config --strict-markers \
  python/tests/qa/test_m2_diagnostics.py python/tests/qa/test_m3_diagnostics.py
pytest --strict-config --strict-markers -m "m3 and m3_fast" integration_tests
python tools/diagnostics/check_m3.py --json-output /absolute/external/m3-readiness.json
```

Final M0–M2 repository regression attestation:

```bash
python tools/diagnostics/run_m3_regressions.py \
  --repository-report /absolute/external/m3/repository/m3-readiness.json \
  --output-root /absolute/external/m3/repository/m0-m2-regressions \
  --m2-registry /absolute/external/m2/asset-registry.json \
  --m2-evidence /absolute/external/m2/m2-evidence.json
```

This command owns `M3_M0_M2_REGRESSIONS`. A green subprocess with diagnostic
PENDING or pytest skip is still a lane failure. M1 three-day evidence is
generated once and hash/source-bound before its integration test reuses it.
The command does not run any M3 7/30-day soak.

`m3_slow`, `soak7`, `soak30`, and `performance` are release-shutter labels, not
permission to run the full matrix on an ordinary pull request. On the producer
MacBook Air, slow Python and Unity work is serialized to one instance.

An integrated upstream artifact must never be exempted merely to keep CI green.
The M0 repository acceptance test has no `contract_pending` marker after
integration and therefore gates every M0 test run. M1 becomes strict through
adapter capability detection and the final `check_m1.py --require-sim` command.
M2 becomes strict through the integrated protocol/Unity surface and
`check_m2.py --require-m2 --evidence <external-json>`.
M3 becomes strict only through `check_m3.py --require-m3 --registry
<external-json> --evidence <external-json>`; no pending, skipped or not-run fact
can pass that command.

## Test evidence

Every non-trivial failure report should include the command, repository commit,
seed when randomness exists, relevant run ID, and a path to redacted logs or a
machine-readable report. Tests must not mutate product state to manufacture a
pass.
