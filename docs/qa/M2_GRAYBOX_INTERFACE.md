# M2 gray-box QA interface

This is a test port, not a second protocol or simulation implementation. Exact
DTOs and generated Schema belong to CONTRACTS; Python authority transitions
belong to SIM; transport, scene registration and presentation belong to UNITY.
QA supplies fixtures, diagnostics and evidence validation only.

## Protocol and direction

All bridge messages use protocol `0.2.0`, the versioned envelope, stable IDs,
and explicit `state_version`. Direction permission is a strict gate.
The frozen catalog's `0.1.0` value remains provenance; evidence records it as
`catalog_protocol_version` and records the session as
`negotiated_protocol_version=0.2.0`.

| Message | Direction | QA obligation |
| --- | --- | --- |
| `client_hello` | Unity → Python | announces Unity and supported protocol |
| `server_hello` | Python → Unity | selects exactly `0.2.0` or rejects |
| `asset_registry` | Unity → Python | reports stable semantic inventory |
| `asset_registry_result` | Python → Unity | returns accepted flag and deterministic issues |
| `world_snapshot` | Python → Unity | authoritative full state for initial/reconnect sync |
| `client_ready` | Unity → Python | permits resume only after successful registration/sync |
| `movement_arrived` | Unity → Python | reports physical arrival; Python decides the transaction |
| `movement_failed` | Unity → Python | reports the frozen failure reason; no arrival commit |
| `movement_cancelled` | Unity → Python | reports physical cancellation; Python owns cancellation |

`movement_cancelled` is not `action_cancelled` and must not be represented as
`movement_failed` with a synthetic `CANCELLED` reason.

## Handshake and readiness

The ordered happy path is:

```text
Unity client_hello
Python server_hello
Unity asset_registry
Python asset_registry_result(accepted=true)
Python world_snapshot
Unity client_ready
```

Protocol mismatch, registry `accepted=false`, a missing required message, or a
wrong-direction message is fatal. Python must not start/resume simulation before
`client_ready`; Unity must order state by `state_version`, not receive time.

## Scoped registry

`integration_tests/fixtures/m2/m2-slice-valid.json` is the canonical M2-positive
fixture. It contains exactly two locations, one NpcView, and the four semantic
object types authorized by ADR-0009. It asserts `accepted=true` and zero errors.
The omitted six locations, nine NpcViews and eleven object types produce the
three `FULL_V0_*_MISSING` warning codes.

`full-v0-registry-reference.json` contains the complete frozen catalog surface
for future comparison. It is not permission to require M3 content in M2.

Unity must export the actual `asset_registry` envelope as JSON. Python must
produce an `asset_registry_result` with deterministic issue severity/code and
entity ID. Neither side may replace semantic IDs with scene instance IDs or
coordinates.

## Navigation and cancellation

The mock/replay fixture covers `arrived`, `failed`, and `cancelled`. At minimum,
`movement_failed` supports `NO_PATH`, `DESTINATION_DISABLED`, `SLOT_BLOCKED`,
`AGENT_DISABLED`, `TIMEOUT`, and `UNKNOWN`.

For every movement report:

- direction is Unity to Python;
- envelope `correlation_id` equals the authority `action_id`;
- an identical retransmission with the same `message_id` is processed once;
- a same-ID message with different canonical content is rejected as a conflict;
- stale `state_version`, wrong direction, obsolete generation, and late old
  transport input produce zero authority mutation.

For `movement_cancelled`, Python commits exactly one authoritative cancellation
transaction and emits any resulting authoritative action/state messages. Unity
does not directly cancel the authority action or settle any hard/soft effect.

## Reconnect/resync generation

The bridge test adapter must expose a monotonically distinguishable connection
generation. Reconnect requires:

1. close or invalidate the old generation;
2. allocate new message IDs;
3. repeat full hello and asset registration;
4. receive a new full snapshot whose version is at least the old connection's
   last acknowledged authority version;
5. send a new `client_ready` before execution resumes;
6. inject one late old-generation input and one stale-version input and record
   zero authority mutations for both.

Unity cache may accelerate presentation reconstruction but may never replace
the fresh authoritative snapshot.

## Required owner test ports

- CONTRACTS: ADR-0010, protocol `0.2.0`, `movement_cancelled` enum/DTO/message
  union, generated JSON Schema, examples, direction tests and compatibility
  tests.
- SIM: a production-bridge adapter capable of reporting accepted/rejected
  message outcomes, committed transaction count, before/after state hash and
  state version, dedupe/conflict result, and connection generation. It may not
  duplicate simulation rules in a QA adapter.
- UNITY: deterministic mock/recorded transport injection, scoped registry JSON
  export, reconnect generation control, late/stale injection, and external
  `stwm.qa.m2-acceptance-evidence/v1` export from EditMode/PlayMode/batchmode.

Fixture JSON is input/expectation data. It is never authoritative runtime state
and may not be used by product code as a replacement implementation.
