# AITOWN-CONTRACTS M0 Handoff

## Current responsibility

Own the M0 configuration, domain Schema, Python/Unity protocol, catalog validation,
and generated contract artifacts. This handoff does not implement simulation,
Unity behavior, model inference/training, networking, or LLM calls.

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
- Unity/Python protocol: `0.1.0`
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

The union covers the minimum V0 handshake, registry, snapshot, clock, action,
delta/event/debug, movement/presentation, player utterance, and time-control
messages named in the implementation specification.

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
- The protocol defines DTO validation, not WebSocket transport, idempotency
  storage, state mutation, or reconnect behavior.
- Main-branch ADR contents other than the supplied frozen summaries were not
  visible. Orchestrator should re-run integration checks after merging its ADRs.

## Pending decisions

- Orchestrator should confirm the unprefixed behavior-ID resolution above when
  reconciling main's ADRs.
- Simulation Core and Unity Bridge should agree whether the initial
  `world_snapshot` transports the full `WorldState` every time or uses a later
  protocol-minor partial snapshot optimization. V0 currently defines the full form.
- Concrete Unity object instance counts and animation mappings must be supplied by
  the scene asset registry and validated against the frozen behavior requirements.

## Next recommended task

Simulation Core can implement M1 against `CatalogBundle`, `WorldState`,
`CandidateAction`, `OutcomePrediction`, `ActionProposal`, `ResolvedAction`, and
`StateTransaction`, limited to Idle, Sleep, EatAtHome, and WorkShift. Unity Bridge
can independently consume `protocol/jsonschema/protocol-message.schema.json` and
the committed examples for its Mock handshake/registry work.

## Blocking dependencies

No blocker remains for M0 contract delivery. Downstream implementation should
not rename IDs, add axes, add route fields, broaden event visibility, or change
relationship direction without an ADR and version bump.
