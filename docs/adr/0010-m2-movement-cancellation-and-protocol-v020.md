# ADR-0010: Add movement cancellation reporting in protocol 0.2.0

- Status: Accepted
- Date: 2026-08-02
- Decision authority: AITOWN-ORCH task `019fbea0-12dc-7dd2-a52e-732d8dac0ce8`

## Context

The V0 implementation specification requires Unity navigation to report
`movement_arrived`, `movement_failed`, and `movement_cancelled` to Python. The
frozen protocol `0.1.0` contains the first two reports but has no
`movement_cancelled` discriminator, Pydantic DTO, JSON Schema branch, or example.
M2 also requires cancellation, connection-generation rejection, reconnect, and
full resynchronization without transferring authority to Unity.

Three compatibility choices were reviewed:

1. Reuse `action_cancelled` in both directions.
2. Add a distinct Unity-to-Python `movement_cancelled` report and bump the
   protocol.
3. Treat cancellation as `movement_failed` with a `CANCELLED` reason.

The first choice conflates an untrusted presentation report with a committed
Python authority decision. The third corrupts failure, retry, and timeout
semantics. A distinct report is the only option with an explicit direction,
safe authority boundary, and stable idempotency key.

AITOWN-ORCH approved option 2 and protocol `0.2.0` on 2026-08-02.

## Decision

### Version and negotiation

- Protocol `0.2.0` is the sole version accepted by the active M2 acceptance
  gate. Protocol `0.1.0` remains available only for bootstrap decoding,
  negotiation compatibility, and legacy non-M2 message tests.
- The `client_hello` bootstrap parser recognizes `0.2.0` and `0.1.0`. The client
  sends a unique preference-ordered list; an M2 client sends `0.2.0` first.
- `server_hello.payload.accepted_protocol_version` is the selected version. The
  `server_hello` envelope and every later message in that session use exactly
  the selected version.
- Protocol `0.1.0` cannot encode `movement_cancelled` and cannot satisfy the M2
  cancellation gate.

### Direction and authority

- `movement_cancelled` is Unity-to-Python only. It reports that local navigation
  has stopped and does not itself mutate `WorldState`, release a reservation,
  change an action phase, or advance `state_version`.
- `action_cancelled` remains Python-to-Unity only. It reports an authority
  decision that Python has already committed.
- A valid `movement_cancelled` report is an input to one Python authority
  cancellation transaction. That transaction terminates the current action,
  releases its reservations, advances `state_version` exactly once, and then
  emits `action_cancelled` to Unity.
- Direction-specific Pydantic unions and JSON Schemas are normative ingress and
  egress parsers. A generic `ProtocolMessage` remains available for logging and
  tooling, but must not replace direction enforcement at a live socket boundary.

The new payload is:

```text
action_id: ActionId
agent_id: AgentId
reason: NAVIGATION_STOPPED | SCENE_UNLOADED | CLIENT_SHUTDOWN | UNKNOWN
```

For every action lifecycle, movement, or presentation message,
`correlation_id` is non-null and equals `payload.action_id`.

### Version, generation, and idempotency checks

- A Unity report's envelope `state_version` is the last Python authority version
  applied by that client. A reported version greater than the server's current
  version is rejected.
- An older reported version is processable only when the report arrived on the
  current server-owned connection generation and its world, action, agent, and
  allowed phase still match exactly. Otherwise Python records a diagnostic and
  requests or sends authoritative resynchronization; the report is a no-op.
- Connection generation is transport context assigned by Python. It is not a
  client-selected JSON authority field. Inputs from an obsolete connection or
  late messages from its transport cannot mutate authority.
- The first occurrence of a `message_id` fixes its canonical content. Repeating
  the same ID and content is a no-op; reusing the ID with different content is a
  protocol error. A late cancellation for a terminal or unknown action is a
  diagnostic/resync no-op and can never affect a newer action.

### Liveness and resynchronization

- Heartbeat uses WebSocket ping/pong. No heartbeat JSON message is added.
- Reconnect creates new message IDs and repeats
  `client_hello -> server_hello -> asset_registry -> asset_registry_result ->
  world_snapshot -> client_ready`. No reconnect or resync JSON message is added.
- The fresh `world_snapshot` is the authority overwrite. Simulation does not
  resume before the new `client_ready`.

### Catalog provenance and evidence naming

`config/v0/world.yaml` retains `protocol_version: 0.1.0` as provenance for the
M0-frozen catalog and accepted M1 replay hashes. It is not the online Bridge
version source. Bridge sessions read `protocol/version.json`, negotiate the
session version, and thereafter use the selected value.

Run/session evidence must record these as separate fields:

```text
catalog_protocol_version = 0.1.0
negotiated_protocol_version = 0.2.0
```

The existing M1 run metadata has only `protocol_version` and therefore cannot
represent both values without an evidence-schema update. SIM and QA own that M2
runtime/evidence migration; this contract change does not edit the simulation
loop or run writer.

## Compatibility and generated artifacts

- The M2 contract publishes `protocol/version.json` at `0.2.0` and regenerates
  the generic and direction-specific Draft 2020-12 JSON Schemas.
- A legacy `0.1.0` `client_hello` and legacy non-cancellation messages remain
  decodable for compatibility tests.
- Examples cover M2 negotiation, registry/readiness, reconnect snapshot,
  movement arrival/failure/cancellation, the authoritative cancellation reply,
  and presentation completion.
- The M2 re-freeze manifest records the original `0.1.0` M0 source commit and
  the new ADR-approved `0.2.0` content commit. M0 freeze verification remains
  strict; no path, digest, or Appendix D check is weakened.

## Consequences

- Unity can explicitly report cancellation without gaining action authority or
  misclassifying it as navigation failure.
- SIM must implement the atomic authoritative cancellation transaction and its
  stale/version/generation/idempotency rules before the M2 gate can pass.
- UNITY must generate or hand-maintain `0.2.0` DTOs, use the Unity-to-Python
  schema for reports, and treat Python `action_cancelled` as the sole authority
  outcome.
- QA must test version rejection, both message directions, duplicate and
  conflicting message IDs, future/stale versions, obsolete connection
  generations, cancellation reservation release, and reconnect readiness.
