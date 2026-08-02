# M2 One-NPC Unity Bridge implementation design

Authority references read during implementation: M2 baseline `0a4caa1` and
protocol 0.2.0 contract `392f941`. Their history is owned and integrated by
AITOWN-ORCH; the final Unity increment does not duplicate those commits.
Editor: macOS ARM64 Unity `6000.4.2f1`
Public project: Small Town World Model（STWM）
Internal owner: `AITOWN-UNITY`

## Product slice

The M2 fixture presents only `npc_01` moving between `home_a` and `cafe_bar`,
plus the minimum local presentation for `sleep`, `eat_at_home`, and
`work_shift`. Python Town Core remains the sole authority. Unity caches only
presentation state and never commits time, high-level location, action,
occupancy, needs, money, food, or events.

## Runtime shape

```text
Python authority / recorded fixture
  -> protocol 0.2.0 envelope
  -> TownBridgeClient (WebSocket, handshake, dedupe, state-version guard)
  -> main-thread dispatch
  -> NpcView
  -> NpcNavigationController / NpcAnimationDriver
  -> movement_arrived | movement_failed | movement_cancelled
     | presentation_completed
  -> Python authority
```

`TownBridgeClient` uses `ClientWebSocket` and the official Newtonsoft JSON
package. `ClientWebSocketOptions.KeepAliveInterval` supplies transport-level
ping/pong liveness without adding a JSON message. A reconnect always repeats
`client_hello -> server_hello -> asset_registry -> asset_registry_result ->
world_snapshot -> client_ready`; ordinary state messages are not applied until
the full snapshot establishes the new session baseline.

Message IDs are the idempotency key. Distinct messages at the same authority
`state_version` are valid; lower versions are stale. Version gaps alone do not
prove message loss because Python need not publish every authority tick.

## Scene semantics

- `SemanticLocation` owns high-level IDs and entrance anchors, never paths.
- `SemanticObject` owns object ID/type/location/capabilities and slots.
- `InteractionSlot` owns only pose, facing, animation support, and local
  presentation occupancy.
- `NpcView` binds `npc_01` and routes presentation commands.
- `NpcNavigationController` reports arrived, failed, or an internal explicit
  cancellation terminal state.
- `NpcAnimationDriver` maps semantic names to optional Animator triggers/bools
  and provides a no-art timed completion fallback for the fixture.

The Editor fixture builder creates primitives only. It does not touch user or
third-party assets.

## Registry and validation

The scanner emits the frozen `AssetRegistryPayload` shape. The M2 validation
profile requires:

- `home_a`, `cafe_bar`, and `npc_01` exactly once;
- a `BED/SLEEP`, `FRIDGE/FOOD_SOURCE_HOME`, and `DINING_SEAT/EAT` at `home_a`;
- a `WORKSTATION` with `WORK` and `CAFE_MORNING` at `cafe_bar`;
- at least one slot on every object;
- mapped `IDLE`, `WALK`, `SLEEP`, `EAT`, and one work semantic.

Duplicate IDs and missing required bindings are errors. Warnings do not block
diagnostic use.

## Protocol 0.2 cancellation boundary

ADR-0010 publishes protocol `0.2.0` with a distinct Unity-to-Python
`movement_cancelled` report. The client sends this report for local navigation
stops, while Python remains the only component allowed to terminate the action,
release authority reservations, advance `state_version`, and answer with the
Python-to-Unity `action_cancelled` authority decision. Cancellation is never
overloaded as `movement_failed`.

The accepted M1 engine has no WebSocket server or `UNITY_LIVE` adapter and still
advances travel from configured minutes. Unity validates transport behavior
against a mock transport and recorded envelopes until SIM supplies the live
authority endpoint. No Python authority code is changed here.
