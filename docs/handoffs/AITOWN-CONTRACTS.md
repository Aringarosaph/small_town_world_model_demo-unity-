# AITOWN-CONTRACTS M0/M2 Handoff

## M2 protocol 0.2.0 delivery

ADR-0010 records the 2026-08-02 AITOWN-ORCH decision to add the missing
Unity-to-Python `movement_cancelled` report and make protocol `0.2.0` the sole
active M2 acceptance version. Protocol `0.1.0` remains a legacy decode and
bootstrap-negotiation input; it cannot pass the M2 cancellation gate.

The M2 contract adds:

- bootstrap `client_hello` parsing for `0.2.0` and `0.1.0`, preserving the
  client's unique preference order;
- selected-version equality between the `server_hello` envelope and payload;
- `MovementCancellationReason` and `movement_cancelled` at protocol `0.2.0`;
- exact `correlation_id == payload.action_id` validation for all action,
  movement, and presentation messages;
- separate `PythonToUnityMessage` and `UnityToPythonMessage` unions and JSON
  Schemas, so inbound routing rejects Python-authority `action_cancelled` and
  outbound routing rejects Unity-report `movement_cancelled`;
- examples for M2 negotiation, scoped registry/readiness, reconnect snapshot,
  movement success/failure/cancellation, authoritative cancellation, and
  presentation completion;
- a strict M2 re-freeze of changed protocol/domain artifacts. The manifest keeps
  the original `0.1.0` M0 source evidence and does not weaken any Appendix D or
  digest check.

### M2 protocol gap matrix

| Surface | Protocol 0.1.0 audit | Protocol 0.2.0 disposition |
| --- | --- | --- |
| `client_hello` / `server_hello` | Hard-coded to `0.1.0`; no preference negotiation | Bootstrap accepts both known versions; M2 selects only `0.2.0`; server envelope equals selected version |
| `asset_registry` / result | DTOs and Schema present | Shape remains compatible; ADR-0009 blocking M2 profile is server/runtime policy |
| `client_ready` | Present and correlated to registry message ID | Compatible; reconnect must not resume before the new ready message |
| `world_snapshot` | Full `WorldState` payload present | Reused as the authoritative reconnect overwrite; no resync JSON type |
| Clock | Envelope and clock payload present | Reused; server continues to enforce ADR-0003 Unity Live `{0,1,2,4}` policy |
| Action lifecycle | Started, phase-changed, and cancelled present | Action messages now require action correlation; `action_cancelled` is Python-to-Unity only |
| Movement arrived / failed | Both present | Compatible and action-correlated |
| Movement cancelled | Missing from enum, union, Schema, and examples | Added only to Unity-to-Python at `0.2.0`; distinct from failure |
| Presentation | `presentation_completed` present | Compatible and action-correlated; never settles hard state directly |
| Heartbeat | No JSON type | WebSocket ping/pong; no protocol message added |
| Reconnect / resync | Envelope fields and snapshot available, behavior unspecified | Full hello/registry/snapshot/ready sequence frozen by ADR-0010; no new JSON type |
| Unified envelope | Present | Both versions bootstrap-decodable; session messages use the selected version |
| `state_version` | Non-negative field present | Runtime rule frozen: never accept a future version; stale reports require exact current generation/action/agent/phase match |
| Correlation | Nullable free string | Action/movement/presentation messages require non-null exact action ID |
| Idempotency | Unique `message_id` field but no storage semantics | ADR-0010 freezes same-ID same-content no-op and same-ID different-content protocol error; runtime owns storage |

### Required downstream M2 work

- SIM must validate connection generation, world/action/agent/phase, reported
  version, and message-id replay before one atomic cancellation transaction
  releases reservations, advances authority version, and emits
  `action_cancelled`.
- UNITY must use the direction-specific `0.2.0` Schema/DTOs, prefer `0.2.0` in
  `client_hello`, and treat the report as non-authoritative.
- QA must cover legacy decode, incompatible version rejection, direction misuse,
  duplicate/conflicting IDs, future/stale versions, obsolete connection
  generations, cancellation release, and full reconnect readiness.
- Existing M1 run metadata records only `protocol_version`, populated from the
  frozen catalog. It cannot represent the required M2 distinction without an
  evidence-schema change. SIM/QA must record both
  `catalog_protocol_version=0.1.0` and
  `negotiated_protocol_version=0.2.0` in M2 run/session evidence.

`config/v0/world.yaml` intentionally remains at `0.1.0` as the M0 catalog
provenance value. Bridge negotiation must read `protocol/version.json` and the
selected session version, never that catalog field.

### M2 validation

Final formatted content was validated with Python `3.12.11`:

```bash
python -m town_core.cli validate-config --config config/v0
# valid; catalog provenance protocol_version=0.1.0

pytest -q python/tests/contracts
# 31 passed

pytest -q python/tests integration_tests/test_m0_acceptance.py
# 77 passed

pytest -q integration_tests/test_m1_headless.py
# 4 passed

pytest -q integration_tests/test_m1_acceptance.py
# 1 passed in 75.71s using the unchanged default 180s gate

ruff format --check .
# 90 files already formatted

ruff check .
# All checks passed

mypy
# Success: no issues found in 51 source files

python tools/diagnostics/check_m0.py
# pass=58 pending=0 fail=0; 57 frozen files verified
```

The protocol feature commit is `392f941`; the additive formatting/content
follow-up is `247711a`. The M2 re-freeze manifest uses the full `247711a` commit
as both its top-level source and `refreeze.source_content_commit`; it does not
point at the pre-format feature commit.

## Current responsibility

Own the frozen configuration, domain Schema, Python/Unity protocol, catalog
validation, and generated contract artifacts. This handoff does not implement
simulation mutation, Unity behavior, model inference/training, networking, or
LLM calls.

Authoritative inputs reviewed in full:

- `AI_Town_V0_Orchestrator_Implementation_Spec.md` (implementation truth source)
- `AI_Town_Long_Term_Architecture_Roadmap.md` (constraints only)
- Orchestrator frozen-summary delegation
- ADR-0003 witness-scope clarification supplied by Orchestrator

The source specifications and main-branch ADR files were not present in this
worktree. They were read from the producer paths supplied by Orchestrator; no
copy was added because `docs/specs/` and `docs/adr/` are outside this task's
allowed write scope.

## Completed since last handoff

- Added a Python 3.12 `python/` package layout with Pydantic v2 and PyYAML.
- Added strict, frozen, extra-forbidden domain/config/protocol models.
- Froze the V0 axes: 5 needs, 4 personality axes, 2 mood axes, and 4 directed
  relationship axes.
- Added 10 adult NPCs, 4 households, 8 locations with a complete symmetric
  travel-time matrix, exact jobs/shifts, 22 behaviors, and 15 object types.
- Added household-shared integer money/food, fixed prices/wage, need decay,
  utility weights, event ontology, model boundary, and deferred prompt manifests.
- Added deterministic relationship initialization ranges using the world seed.
- Added catalog loading plus exact-count, stable-ID, reciprocal membership,
  job/shift, travel, behavior/object/event, utility, prompt, and cross-file checks.
- Added the QA-compatible `python -m town_core.cli validate-config --config config/v0` command.
- Added versioned JSON Schema and validated JSON examples under `protocol/`.
- Added contract tests for catalog validity, invalid references, envelope/artifact
  drift, directed relationship prediction, central JointAction aggregation,
  high-level perception, disabled route planning, resource bounds, and ADR-0003.

## Files changed

- `pyproject.toml`
- `config/v0/`
- `protocol/version.json`
- `protocol/jsonschema/`
- `protocol/examples/`
- `python/town_core/__init__.py`
- `python/town_core/cli.py`
- `python/town_core/domain/`
- `python/town_core/catalogs/`
- `python/tests/contracts/`
- `docs/handoffs/AITOWN-CONTRACTS.md`

## Interfaces changed

### Versions

- Config: `v0`
- Domain Schema: `v0.1`
- Unity/Python active M2 protocol: `0.2.0`
- Legacy protocol decode/bootstrap compatibility: `0.1.0`
- World-model feature contract: `v0.1`
- Python runtime: `3.12.x`
- Unity editor: `6000.4.2f1`

### Catalog authority

`town_core.catalogs.load_catalog(path)` is the single M0 configuration entry.
It returns a validated `CatalogBundle` or raises `CatalogValidationError`.

Required files:

- `world.yaml`
- `population.yaml`
- `households.yaml`
- `locations.yaml`
- `objects.yaml`
- `behaviors.yaml`
- `schedules.yaml`
- `economy.yaml`
- `utility.yaml`
- `events.yaml`
- `model.yaml`
- `prompts/manifest.yaml` plus the two versioned Markdown templates

### Protocol authority

All WebSocket messages use the flat `ProtocolMessage` envelope:

```text
protocol_version, message_id, message_type, sent_at_utc,
world_id, state_version, correlation_id, payload
```

The generic union covers the minimum V0 handshake, registry, snapshot, clock,
action, delta/event/debug, movement/presentation, player utterance, and
time-control messages named in the implementation specification. Live Bridge
boundaries must use the direction-specific unions introduced by ADR-0010.

### Frozen semantic decisions

- Learned relationship output is only `TARGET_TO_ACTOR`; Actor→Target learned
  output is absent from the prediction DTO.
- JointAction is created by `CENTRAL_RESOLVER`, has unique participants, and is
  serialized in stable ascending Agent ID order.
- V0 perception is authoritative only at one high-level location. Observed agents
  and objects from any other location fail validation.
- Route planning is `DISABLED`. Candidates may carry destination and estimated
  travel minutes, but extra waypoint/path fields fail validation.
- Event witness scope is distinct from perception authority. Each event type is
  explicitly either `PARTICIPANTS_ONLY` or `HIGH_LEVEL_LOCATION`; private
  invitations, apologies, event sharing, household crises, and similar events do
  not automatically disclose themselves to everyone at the location.
- Money and food belong to households and use non-negative integers. There are
  no personal accounts or dynamic prices.
- Schedules contain only recurring work entries in V0; sleep, meals, and leisure
  remain need-driven.

### Schema artifacts

Pydantic is the source of truth. Regenerate committed artifacts with:

```bash
python -m town_core.domain.schema_artifacts --output protocol
```

`python/tests/contracts/test_protocol_artifacts.py` rejects drift between the
generator and committed files.

## Tests added/run

Validated locally with Python 3.14 as a forward-compatibility smoke test while
the project metadata intentionally restricts supported runtime to Python 3.12.x.
Dependencies were installed in an external temporary directory, not the repo.

```bash
python -m town_core.cli validate-config --config config/v0
# {"valid": true, ...}

pytest -q
# 13 passed

ruff check .
# All checks passed!

mypy
# Success: no issues found in 17 source files
```

Clean Python 3.12 verification setup:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m town_core.cli validate-config --config config/v0
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/mypy
```

## Known limitations

- The V0 specification contains inconsistent behavior-ID examples:
  `behavior_sleep` appears in the generic ID section, while behavior definitions,
  candidates, schedules, and most payloads use `sleep`, `work_shift`,
  `eat_at_cafe`, and `apologize`. This contract uses the latter unprefixed IDs.
  Changing them now requires a protocol/config migration ADR.
- Relationship initialization stores explicit role-based ranges and a fixed seed,
  not 90 materialized directed edges. Simulation Core must deterministically
  materialize all ordered NPC pairs and persist them in the initial config
  snapshot; it must not create random defaults on read.
- `objects.yaml` freezes the 15 object-type/affordance contracts. Concrete object
  instances and slot counts come from Unity `asset_registry` during M2 and are
  not fabricated in M0.
- JSON Schema is generated from Python/Pydantic. Unity C# DTO generation is not
  included in this path scope; Unity Bridge should implement against the
  committed JSON Schema/examples.
- Event correction/retraction fields are reserved in `WorldEvent`, but correction
  semantics remain deferred as allowed by V0.
- Prompt schemas/templates are frozen for compatibility, but the backend remains
  `deferred_to_m5`; there is no API client or prompt execution here.
- The protocol defines DTO validation and normative direction/version policy,
  not WebSocket transport, idempotency storage, or state mutation. ADR-0010
  freezes the required runtime behavior for its SIM/UNITY/QA owners.

## Pending decisions

None within the active M2 contract. Any post-M2 partial-snapshot optimization
requires a later protocol/version ADR; ADR-0010 requires a full snapshot for M2
reconnect.
- Concrete Unity object instance counts and animation mappings must be supplied by
  the scene asset registry and validated against the frozen behavior requirements.

## Next recommended task

SIM and UNITY should consume the direction-specific `0.2.0` schemas and implement
the ADR-0010 runtime rules. QA should add the cancellation/version/generation
fixtures listed above and require separate catalog and negotiated protocol fields
in M2 evidence.

## Blocking dependencies

No blocker remains for M0 or the M2 contract delivery. Downstream implementation
should not rename IDs, add axes, add route fields, broaden event visibility,
change relationship direction, or reinterpret cancellation authority without an
ADR and version bump.
