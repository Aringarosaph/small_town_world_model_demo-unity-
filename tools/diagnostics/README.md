# M0, M1, M2 and M3 diagnostics

`check_m3.py` is the M3 complete heuristic-society readiness and release gate.
It validates the exact 10/4/8/22/15/90 surface, QA profiles, additive 0.3/0.2
protocol metadata, shared full-town manifest, external `M3_FULL` registry and
`stwm.qa.m3-acceptance-evidence/v1`. Missing CONTRACTS/SIM/UNITY surfaces are
owner-attributed `PENDING` in the default fast mode; partial integration is a
failure and `--require-m3` makes all pending fatal.

```bash
python tools/diagnostics/check_m3.py \
  --json-output /absolute/external/m3-readiness.json
python tools/diagnostics/check_m3.py --require-m3 \
  --registry /absolute/external/full-registry.json \
  --evidence /absolute/external/m3-acceptance-evidence.json
```

The validator consumes producer facts and contains no candidates, economy,
social, JointAction, replay or Unity product implementation. Ordinary CI runs
only its fast readiness surface; fixed 7/30-day soaks remain an
Orchestrator-ordered release action.

`check_m2.py` is the M2 functional gray-box gate. It checks the accepted M1
ancestor, protocol `0.2.0` target fixtures, direction/cancellation/reconnect
rules, the ADR-0009 scoped asset profile, Unity generated-file policy and
external acceptance evidence. It imports catalog/DTO definitions and contains
no transport, navigation, cancellation or simulation implementation.

The evidence validator distinguishes ADR-0010 stale branches: an exact current
generation/world/action/agent/`TRAVELING` cancellation commits once, while only
terminal/nonmatching or obsolete-generation stale inputs are zero-mutation
resync outcomes. It rejects both the legacy broad stale counter and a duplicate
exact-stale transaction counter; `python_authority_cancel_transaction_count` is
the sole A-branch transaction field.

```bash
python tools/diagnostics/check_m2.py \
  --registry integration_tests/fixtures/m2/m2-slice-valid.json \
  --json-output /tmp/stwm-m2-diagnostics.json
```

With CONTRACTS 0.2.0 integrated, protocol, direction Schema and cancellation
checks are strict and have no pending state. ADR-0011 permits repository current
to become 0.3.0 only while `active_m2_acceptance_versions=["0.2.0"]` and every
0.2 artifact/direction check remains intact. Before UNITY integration the
default command reports its named pending owners. The final gate adds
`--require-m2 --evidence <external-json>`; pending is then fatal. Complete-V0
content absent from the scoped M2 registry is emitted as `WARNING`, while
missing slice content is `FAIL`.

`check_m1.py` is the pending-capable black-box M1 adapter. It executes the
SIM-owned `town_core.simulation.qa_adapter` after integration and validates the
three-day run matrix, invariants, deterministic hashes, replay, work/wage and
rejection probes. It never implements simulation rules.

```bash
python tools/diagnostics/check_m1.py \
  --output-root /tmp/stwm-m1-qa \
  --json-output /tmp/stwm-m1-diagnostics.json
```

Add `--require-sim` only for the final integrated M1 gate. Before SIM is present,
the default command reports one readable `PENDING`; partial or broken
integration always fails.

## M0 freeze diagnostics

`check_m0.py` provides four independent groups:

- `structure`: M0 repository artifacts and their owning thread;
- `sensitive`: tracked/unignored secret, runtime, model, dataset, and Unity
  generated-file detection;
- `scope`: frozen V0 catalog sets, dimensions, minimum events, and the
  authoritative configuration validator;
- `freeze`: reviewed SHA-256 coverage plus the Orchestrator's Appendix D
  checklist sign-off.

Strict acceptance:

```bash
python tools/diagnostics/check_m0.py
```

Parallel M0 development (only upstream-owned failures become `PENDING`):

```bash
python tools/diagnostics/check_m0.py --allow-pending-m0-inputs
```

The default authoritative validator command is:

```bash
python -m town_core.cli validate-config --config config/v0
```

If CONTRACTS exposes an equivalent entry point, set
`AITOWN_M0_CONFIG_VALIDATE_CMD` to that command in the integration workflow.
The diagnostic uses `PYTHONPATH=<repo>/python` and never defines product Schema.

After CONTRACTS integration, prepare the real candidate manifest:

```bash
python -m tools.diagnostics.prepare_m0_freeze \
  --source-commit <integrated-contracts-commit>
```

The script writes `m0_config_freeze.json`, refuses to overwrite it by default,
records every eligible hash, and leaves every checklist item false. An
Orchestrator must then manually review Appendix D, fill `approved_by` and
`approved_at_utc`, and mark each verified item true. The tooling deliberately
does not provide an auto-approve mode.
