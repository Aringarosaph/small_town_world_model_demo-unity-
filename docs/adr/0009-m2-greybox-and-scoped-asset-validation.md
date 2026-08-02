# ADR-0009: M2 functional greybox and scoped asset validation

- Status: Accepted
- Date: 2026-08-02

## Context

The V0 specification describes a complete eight-location asset-registry audit,
while the M2 milestone exit gate is intentionally a one-NPC Unity vertical
slice. Requiring the complete town scene before the bridge can be exercised
would make final art and M3 content an entry dependency for M2.

The producer authorized M2 on 2026-08-02 and selected the functional-greybox
route. Unity Hub is signed in with a Personal license, and Editor `6000.4.2f1`
is installed.

## Decision

M2 uses a no-art functional greybox for `npc_01` and the route
`home_a -> cafe_bar -> home_a`.

The blocking M2 asset-registry profile contains only:

- `SemanticLocation` bindings for `home_a` and `cafe_bar`;
- one `NpcView` bound to `npc_01`;
- a `BED`, `FRIDGE`, and `DINING_SEAT` with the slots needed to present the
  accepted M1 home behaviors;
- a `WORKSTATION` at `cafe_bar` with the `CAFE_MORNING` capability and a usable
  interaction slot;
- entrance or navigation anchors sufficient to travel between the two
  locations.

Missing or invalid M2-profile entries are blocking errors. Missing objects and
locations required by the complete V0 catalog are still reported, but remain
warnings during M2. The complete V0 registry becomes a blocking profile only
when the complete heuristic town is activated in M3.

The validation profile is server/runtime policy. It does not give Unity
authority and does not require Unity to select or weaken its own validation
rules.

M2 uses local WebSocket JSON and the frozen protocol envelope. Any actual
protocol or schema change still requires a separate compatibility review,
semantic-version decision, regenerated artifacts, and Orchestrator acceptance.

Unity dependencies must be built-in or official packages unless a later ADR
approves an exception. Exact package versions are frozen after the first
successful controlled import with Editor `6000.4.2f1`.

## Consequences

- Bridge, navigation, reconnect, diagnostics, and authority separation can be
  accepted without final art or the full town scene.
- Test prefabs and generated greybox fixtures may be committed; Unity generated
  caches and imported third-party source assets may not be committed.
- The full eight-location registry remains visible as actionable diagnostic
  debt instead of being silently ignored.
- Python remains the sole authority. Unity arrival and presentation signals can
  advance an action phase but cannot directly settle needs, wages, resources,
  events, or state versions.
