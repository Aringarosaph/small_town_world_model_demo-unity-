# AITOWN-QA handoff

## Responsibility and scope

Long-lived QA/observability owner for **Small Town World Model（STWM）**.
`AITOWN-QA` remains an internal compatibility name. M0 and M1 are accepted; this
increment adds the M2 functional gray-box QA baseline only.

QA did not implement WebSocket transport, Unity runtime/navigation, Python
authority cancellation, or a second simulation ruleset. It did not modify
frozen config, protocol/domain files, generated Schema, Unity product code, or
`pyproject.toml`.

## Delivered

- `tools/diagnostics/check_m2.py`: integration-aware M2 diagnostic and strict
  external evidence validator.
- `m2-slice-valid.json`: exact ADR-0009 profile with `accepted=true`, two
  locations, `npc_01`, and BED/FRIDGE/DINING_SEAT/CAFE_MORNING WORKSTATION.
- invalid registry mutations plus a separate complete-V0 future reference.
- handshake and navigation/reconnect fixtures targeting protocol `0.2.0` and
  independent Unity-to-Python `movement_cancelled`.
- QA unit tests, a pending-capable M2 repository adapter, M2 marker conventions,
  and a Python 3.12 `m2-qa-readiness` CI lane.
- `stwm.qa.m2-acceptance-evidence/v1`, external artifact policy, bridge log
  fields, Unity EditMode/PlayMode/batchmode strategy, and acceptance docs.
- sensitive-file and Unity Library/Logs/TestResults/cache guards.

The scoped asset validator imports frozen catalog/DTO types. Missing M2 slice
content is `ERROR`; missing complete-V0 content is explicit `WARNING`. The full
V0 reference remains diagnostic-only until M3.

## Strict protocol and authority requirements

ORCH decided ADR-0010 semantics while this work was active:

- protocol version is `0.2.0`;
- `movement_cancelled` is a distinct Unity-to-Python message;
- neither `action_cancelled` nor `movement_failed/CANCELLED` is an alias;
- movement report `correlation_id` equals `action_id`;
- identical same-`message_id` retransmission is idempotent;
- conflicting canonical content under the same ID is rejected;
- wrong direction, stale state, obsolete connection generation, and late old
  transport messages produce zero authority mutation;
- Python performs exactly one authoritative cancellation transaction; Unity's
  report has zero direct authority mutation.

Reconnect allocates new IDs, repeats full hello and registry, receives a fresh
snapshot no older than the old connection's last acknowledged authority
version, and resumes only after the new `client_ready`. Unity cache is
non-authoritative.

## Exact integration interfaces

### CONTRACTS

The accepted source commit `392f941` is integrated on this branch as `59a3d28`;
its formatting follow-up `247711a` is integrated as `1231dfa`.
It contains protocol `0.2.0`, the
`movement_cancelled` enum/DTO/message union, generated JSON Schema and examples,
direction permission tests, and compatibility tests. After integration:

```bash
python tools/diagnostics/check_m2.py --require-m2
```

reports neither `M2_PROTOCOL_0_2_PENDING` nor
`M2_MOVEMENT_CANCELLED_CONTRACT_PENDING`. The later CONTRACTS re-freeze manifest
is integration evidence and does not block this DTO/QA commit. Do not weaken
these checks to retain 0.1 compatibility as an accepted M2 result.

### SIM/Python bridge

Expose production-bridge test observations for message acceptance/rejection,
before/after state hash and version, committed transaction count, dedupe versus
same-ID conflict, and connection generation. The adapter must drive existing
authority transitions and must not reproduce domain rules. Cancellation must
prove exactly one Python transaction and zero mutation for duplicate,
conflicting, stale, wrong-generation and late messages.

### UNITY

Provide deterministic mock/recorded injection for handshake, asset registry,
arrived/failed/cancelled, disconnect and reconnect; export the actual registry,
redacted transcript, EditMode/PlayMode XML and batchmode log. Export
`stwm.qa.m2-acceptance-evidence/v1` to a repository-external result directory.
The agreed Editor/batchmode export entry point must return nonzero on any failed
gate.

### ORCHESTRATOR/CI

1. Preserve CONTRACTS `392f941`, then integrate the SIM bridge and UNITY before
   final acceptance.
2. Centralize `m2`, `unity_pending`, `protocol`, `unity`, `graybox`, and
   `batchmode` markers in `pyproject.toml`; QA avoided the shared file while
   CONTRACTS was active.
3. Add the licensed macOS ARM64 Unity workflow described in
   `docs/qa/M2_UNITY_CI.md` after the Unity project/test assemblies exist.
4. Keep `Library/`, logs, XML/JSON results and evidence outside the checkout;
   upload only sanitized artifacts.
5. Run M0/M1 regression and the final strict command. Final M2 acceptance
   permits no pending result.

## Current integration-aware result

This branch contains the accepted M1 baseline and ORCH M2 baseline. QA fixtures,
asset validation, repository guards and evidence-template validation pass.
CONTRACTS protocol 0.2.0, typed cancellation, correlation validators, generic
and direction-specific Schema, examples, and QA fixtures pass with no protocol
pending. The default diagnostic now reports only two readable Unity-owned
pending items: runtime/test integration and external acceptance evidence.

`--require-m2` intentionally converts those two to failures. That is a temporary
parallel-development state, not final M2 semantics. Per ORCH, the full M1
three-day gate must be run later in the single-instance integration sequence,
not concurrently on the MacBook Air.

Final independent QA verification after CONTRACTS formatting integration:

- Ruff format: 101 repository files passed;
- QA-scoped Ruff and strict Mypy: passed;
- protocol 0.2 artifact tests plus M2 QA: 37 passed, one Unity-absence skip;
- default M2 diagnostic with scoped registry: 17 pass, 26 ADR-0009 warnings,
  two Unity-owned pending, zero failures;
- strict M2 diagnostic: 17 pass, 26 warnings, zero pending, and exactly the two
  expected Unity runtime/evidence failures.

The complete M1 three-day gate was deliberately not rerun, per ORCH's
single-instance resource ordering. CONTRACTS re-freeze evidence remains an
ORCH integration step and does not block this QA commit.

## Final commands

```bash
ruff check .
ruff format --check .
mypy python/town_core
mypy --strict --explicit-package-bases \
  tools/diagnostics python/tests/qa integration_tests
pytest --strict-config --strict-markers -m "not m2" \
  python/tests integration_tests
pytest --strict-config --strict-markers \
  python/tests/qa/test_m2_diagnostics.py
STWM_M2_QA_EVIDENCE=/absolute/external/m2-evidence.json \
pytest --strict-config --strict-markers -m m2 integration_tests
python tools/diagnostics/check_m0.py
python tools/diagnostics/check_m1.py \
  --output-root /absolute/external/m1-qa --require-sim
python tools/diagnostics/check_m2.py \
  --require-m2 \
  --registry /absolute/external/asset-registry.json \
  --evidence /absolute/external/m2-evidence.json \
  --json-output /absolute/external/m2-diagnostics.json
```
