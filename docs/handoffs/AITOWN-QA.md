# AITOWN-QA handoff

## Responsibility and scope

Long-lived QA/observability owner for **Small Town World Model（STWM）**.
`AITOWN-QA` remains an internal compatibility name. M0–M2 are accepted; the
current increment adds the M3 complete heuristic-society QA baseline from entry
`2a516159ab41f88c90ea2932bbc117b595c569c3`.

QA did not implement candidates, economy/social effects, JointAction,
checkpoint/replay producers, WebSocket transport, Unity presentation, or a
second simulation ruleset. It did not modify frozen config, protocol/domain
files, generated CONTRACTS Schema, Unity product code, or `pyproject.toml`.

## M3 QA delivery

- `tools/diagnostics/check_m3.py`: pending-capable readiness CLI plus strict
  external registry/evidence validator. `--require-m3` converts all pending to
  failure.
- exact JSON Schemas/templates for `stwm.qa.m3-readiness/v1` and
  `stwm.qa.m3-acceptance-evidence/v1`.
- executable release, targeted 22-behavior and full-registry/capacity profiles
  under `integration_tests/fixtures/m3/`.
- QA unit coverage for exact pending ownership, strict conversion, additive
  M2/M3 version metadata, complete evidence, threshold boundaries, replay hash
  mismatch and external artifact integrity.
- integration-aware M3 adapter, additive fast/slow/society/registry/JointAction/
  soak/performance markers, and the Python 3.12 fast readiness CI lane.
- `docs/qa/M3_ACCEPTANCE.md`, M3 CI strategy, external runs/log policy and this
  handoff.

The QA gate contains frozen IDs, counts, thresholds and evidence equations only.
It imports/consumes upstream facts and never executes a replacement society
ruleset or fabricates Python/Unity PASS evidence.

## M3 exact integration interfaces

### CONTRACTS

1. `protocol/version.json` sets repository current `protocol_version=0.3.0`,
   exact `active_m3_acceptance_versions=["0.3.0"]`, retained
   `active_m2_acceptance_versions=["0.2.0"]`, and bootstrap preference beginning
   `["0.3.0", "0.2.0"]`. At current 0.3 it also declares exact
   `movement_cancelled_versions=["0.3.0", "0.2.0"]` and immutable M2
   compatibility artifacts; the retained current-0.2 document uses exact
   `["0.2.0"]`.
2. Retain all M2 `0.2.0` examples, schemas, direction unions and ADR-0010
   semantics. QA's M2 gate no longer requires current=0.2, but still rejects a
   missing M2 acceptance profile, movement cancellation artifact, direction or
   correlation rule. M2 fixtures/evidence continue to negotiate `0.2.0`.
3. Publish version-aware 0.3 DTOs/schemas/examples for structured
   `action_started` participants, presentation-complete `world_snapshot`,
   field-mask/explicit-null `agent_state_delta`, `household_state_delta`, and
   read-only `debug_decision_trace`. M3 QA reads the versioned
   `protocol-message-v030`, `python-to-unity-message-v030`, and
   `unity-to-python-message-v030` schemas; M2 keeps validating the 0.2
   compatibility schemas.
4. Publish `config/v0/semantic_instances.yaml` with schema
   `stwm.catalog.m3-semantic-instances/v1`, profile `M3_FULL`, catalog provenance
   `0.1.0`, exact `location_ids`/`npc_view_ids`, and object records containing
   `supported_animation_semantics` with optional `assigned_agent_id` (never an
   `enabled` shadow field). QA validates the exact top/object keys, all 74
   instances, capacity, assignments, animation/prop/facing coverage, and the
   authoritative `town_core.catalogs.load_m3_catalogs` result. This is the sole
   instance manifest consumed by SIM and UNITY.

### SIM

Provide the SIM-owned `python/town_core/simulation/m3_qa_adapter.py` and real
external artifacts with these schema identities:

```text
stwm.simulation.m3-authority-evidence/v1
stwm.simulation.m3-behavior-coverage/v1
stwm.simulation.m3-soak-report/v1
stwm.simulation.m3-replay-report/v1
stwm.simulation.m3-pathology-report/v1
stwm.simulation.m3-performance-report/v1
stwm.simulation.m3-authority-checkpoint/v1
```

The acceptance exporter maps producer facts into the exact matrices in
`M3_ACCEPTANCE_EVIDENCE.template.json`: 22 behavior rows, 10 liveness rows, 4
household conservation rows, directed relationship/knowledge/JointAction
summaries, determinism/checkpoint facts, exact 5×7-day plus 3×30-day soak rows,
pathology and reference performance. Every soak row carries final-state,
ledger, and authority-log hashes plus equal replay hashes. Do not make QA import
product internals to recompute a PASS.

### UNITY

Provide:

```text
unity/Assets/AITown/Editor/M3AcceptanceEvidenceExporter.cs
unity/Assets/AITown/Editor/M3FunctionalGrayboxBuilder.cs
unity/Assets/AITown/Editor/M3ReadinessEvidenceExporter.cs
unity/Assets/AITown/Resources/M3FunctionalGrayboxManifest.json
unity/Assets/AITown/Scripts/Semantic/M3SemanticManifest.cs
```

The real builder must consume `M3SemanticManifestDocument.LoadDefault()` through
the Resources seam. `M3ReadinessEvidenceExporter` is explicitly
`AcceptanceEligible=false`; it proves only the builder/readiness surface and
must not substitute for `M3AcceptanceEvidenceExporter`. The final exporter
produces these sanitized artifacts:

```text
stwm.unity.m3-registry-report/v1
stwm.unity.m3-semantic-coverage/v1
stwm.unity.m3-debug-trace/v1 (JSONL)
zero-skipped EditMode XML
zero-skipped PlayMode XML
batchmode log
```

The Unity matrix has the exact fields in the acceptance schema: 10/8/15
surface, all animation/prop/facing/NavMesh mappings, snapshot replacement,
explicit-null clearing, action rebind, stale rejection, zero duplicate slot
claims, JointAction lifecycle/reconnect, read-only complete debug trace, live
0.3.0 smoke, and zero skipped tests. Unity must not assert Python authority
facts.

### ORCHESTRATOR/CI

1. Centralize the additive marker names from both QA `conftest.py` files into
   `pyproject.toml` once CONTRACTS is no longer modifying shared configuration.
2. Keep the ordinary M3 lane fast. It targets 10 minutes, hard-stops at 15 and
   requests 2 vCPU/4 GiB. Do not add the complete soak to PR CI.
3. Order the slow release shutter after upstream integration: at most four
   2-vCPU/4-GiB Python shards with 60-minute hard limits. On the producer
   MacBook Air run exactly one local Python/Unity process at a time.
4. A licensed remote macOS ARM64 Unity lane is optional. Real zero-skipped
   artifacts remain required regardless of where batchmode runs.
5. Store the evidence bundle outside the checkout. Upload only redacted
   artifacts with matching relative path, SHA-256, bytes and schema. Never
   commit `runs/`, Unity caches/results, credentials or machine-local output.
6. Final acceptance runs M0/M1/M2 regressions, the M2 compatibility gate and
   `check_m3.py --require-m3 --registry ... --evidence ...`; it permits no
   pending, skip or not-run result.

## M3 current integration-aware state

At the frozen entry, QA-owned governance, repository guards, catalog surface,
release profiles and exact schema/template checks pass. Seven deliberate
pending findings remain:

```text
M3_PROTOCOL_0_3_PENDING                         CONTRACTS
M3_SHARED_SEMANTIC_MANIFEST_PENDING            CONTRACTS
M3_SIM_QA_ADAPTER_PENDING                      SIM
M3_UNITY_EVIDENCE_EXPORTER_PENDING             UNITY
M3_UNITY_FUNCTIONAL_GRAYBOX_PENDING            UNITY
M3_FULL_REGISTRY_EVIDENCE_PENDING              UNITY
M3_ACCEPTANCE_EVIDENCE_PENDING                 QA/integration
```

Their default status supports parallel implementation. Under `--require-m3`
all seven are failures. No complete 7-day/30-day slow soak was run on this QA
branch.

Focused M3 Ruff/format and strict Mypy pass. The combined M2/M3 validator suite
on the frozen QA branch has 44 passes and three intentional upstream-absence
skips. Default `check_m3` is 11 PASS/7 PENDING/0 FAIL; strict mode is 11 PASS/0
PENDING/7 FAIL. Against the ORCH snapshot containing real CONTRACTS 0.3, Unity
foundation, and M3 SIM runtime, the focused suite is 46 passes/one acceptance
skip and default `check_m3` is 14 PASS/4 PENDING/0 FAIL. Its remaining findings
are the SIM QA adapter, final Unity acceptance exporter, external full registry,
and external acceptance evidence; CONTRACTS and the Unity functional-greybox
Resources seam pass. The frozen entry's broader `mypy --strict tools/diagnostics
python/tests/qa integration_tests` also traverses SIM-owned
`python/town_core/simulation/engine.py` and reports two existing explicit-export
errors for `NeedValues` and `MoodValues`; QA did not modify that product file.
ORCH/SIM should resolve or explicitly baseline those errors before relying on
the shared all-directory Mypy lane.

## M2 historical delivery

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
- an exact-match stale cancellation on the current generation remains
  processable and commits exactly once;
- stale terminal/nonmatching cancellations produce zero authority
  transaction/mutation plus diagnostic resync;
- wrong-direction, future-version, obsolete-generation, and late old-transport
  inputs are rejected with zero authority mutation;
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

ORCH commit `7e11d24` integrates the SIM artifact
`stwm.bridge.m2-authority-evidence/v1`. QA consumes its scalar observations and
the `stale_exact_current_action` / `stale_nonmatching_or_terminal` probes; it
does not infer or reproduce simulation rules.

The final `stwm.qa.m2-acceptance-evidence/v1` cancellation object has **exactly**
these keys:

```text
conflicting_same_message_id_rejected_without_mutation
correlation_id_equals_action_id
direction
direction_rejected_without_mutation
duplicate_same_message_id_is_idempotent
future_state_version_rejected_without_mutation
python_authority_cancel_transaction_count
stale_exact_current_action_processed
stale_nonmatching_or_terminal_authority_mutation_count
stale_nonmatching_or_terminal_authority_transaction_count
stale_nonmatching_or_terminal_diagnostic_resync
unity_direct_authority_mutation_count
```

`python_authority_cancel_transaction_count=1` is the sole QA summary field for
the processable exact-current-action stale branch; the SIM probe
`stale_exact_current_action.authority_transaction_count` is its source. Do not
also emit `stale_exact_current_action_transaction_count`. The three
`stale_nonmatching_or_terminal_*` fields come from that SIM probe's
`authority_mutation_count`, `authority_transaction_count`, and
`outcome == DIAGNOSTIC_RESYNC`, respectively.

The final reconnect object has **exactly** these keys:

```text
fresh_snapshot_not_older_than_last_acknowledged_version
full_hello_and_registry_repeated
late_obsolete_generation_authority_mutation_count
new_client_ready_before_resume
new_message_ids
obsolete_generation_rejected
```

SIM's legacy broad `stale_state_message_authority_mutation_count` must not be
copied from either source object into QA evidence: it ambiguously hides the
processable A branch. `late_terminal_message_authority_mutation_count` and
reconnect session/detail objects remain source evidence, not duplicate QA
summary fields. The strict validator rejects all extra keys.

### UNITY

Provide deterministic mock/recorded injection for handshake, asset registry,
arrived/failed/cancelled, disconnect and reconnect; export the actual registry,
redacted transcript, EditMode/PlayMode XML and batchmode log. Export
`stwm.qa.m2-acceptance-evidence/v1` to a repository-external result directory.
The agreed Editor/batchmode export entry point must return nonzero on any failed
gate. Update `SelectCancellationObservations` and
`SelectReconnectObservations` to emit the exact key sets above. In particular,
derive the three B-branch fields from the SIM probe rather than selecting either
legacy broad stale field.

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

ADR-0010 stale-semantics audit adds a strict evidence split: the current
generation/world/action/agent/`TRAVELING` exact-match stale cancellation must be
processed with `python_authority_cancel_transaction_count=1`; stale
terminal/nonmatching reports must have authority-transaction and
authority-mutation counts zero plus diagnostic resync. The final exact key sets
above replace the deprecated broad `stale_state_message_authority_mutation_count`
shape and avoid a duplicate exact-stale transaction field.
QA-scoped Ruff/format and strict Mypy pass. The focused Python 3.12 audit has
26 passes and one expected Unity-absence skip; the standalone diagnostic has
17 passes, 26 ADR-0009 warnings, two Unity-owned pending items, and zero
failures.

## Final commands

```bash
ruff check .
ruff format --check .
mypy python/town_core
mypy --strict --explicit-package-bases \
  tools/diagnostics/check_m2.py tools/diagnostics/check_m3.py \
  python/tests/qa/test_m2_diagnostics.py python/tests/qa/test_m3_diagnostics.py \
  python/tests/qa/conftest.py integration_tests/conftest.py \
  integration_tests/test_m3_acceptance.py
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

M3 QA focused verification and final integration commands:

```bash
ruff check tools/diagnostics python/tests/qa integration_tests
ruff format --check tools/diagnostics python/tests/qa integration_tests
mypy --strict --explicit-package-bases \
  tools/diagnostics python/tests/qa integration_tests
pytest --strict-config --strict-markers \
  python/tests/qa/test_m2_diagnostics.py python/tests/qa/test_m3_diagnostics.py
pytest --strict-config --strict-markers -m "m3 and m3_fast" integration_tests
python tools/diagnostics/check_m3.py \
  --json-output /absolute/external/m3-readiness.json
python tools/diagnostics/check_m3.py --require-m3 \
  --registry /absolute/external/m3/full-registry.json \
  --evidence /absolute/external/m3/m3-acceptance-evidence.json \
  --json-output /absolute/external/m3/m3-readiness.json
```
