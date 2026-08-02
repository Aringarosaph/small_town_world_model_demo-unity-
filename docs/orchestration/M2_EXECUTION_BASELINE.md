# M2 execution baseline

## Outcome

M2 proves that the accepted M1 authority runtime can drive a Unity presentation
client without transferring business authority to Unity. One greybox NPC must
complete a visible `home_a -> cafe_bar -> home_a` work loop, while connection,
asset, navigation, and resynchronization failures remain explicit and testable.

## Fixed slice

- Public project name: Small Town World Model（STWM）.
- Active agent: `npc_01`.
- Home: `home_a`.
- Work location: `cafe_bar`.
- Workstation capability: `CAFE_MORNING`.
- Authority behaviors remain the accepted M1 allowlist: `idle`, `sleep`,
  `eat_at_home`, and `work_shift`.
- Presentation route: home activity, travel to work, work presentation, and
  return home.
- Visual target: functional greybox with no final-art dependency.
- Unity Editor: macOS ARM64 `6000.4.2f1`.
- Transport: local WebSocket with JSON messages and the versioned envelope.
- Authority clock: `game_minute`; Unity Live may request only `0x`, `1x`, `2x`,
  or `4x`.
- Action duration begins after confirmed arrival. Animation success is never an
  authority prerequisite for hard-state settlement.

## Required M2 semantic inventory

The blocking M2 registry profile is frozen by ADR-0009:

```text
home_a
  BED + slot
  FRIDGE + slot
  DINING_SEAT + slot
  entrance/navigation anchor

cafe_bar
  WORKSTATION + CAFE_MORNING + slot
  entrance/navigation anchor

npc_01
  NpcView + navigation controller + animation-semantic adapter
```

All IDs are stable semantic IDs. Scene instance IDs and coordinates may not be
used as cross-process authority identifiers.

## Required implementation

1. A reproducible Unity project import with exact official package versions.
2. A Python bridge adapter around the accepted M1 runtime; no second simulation
   loop and no duplicated settlement rules.
3. Versioned `client_hello` / `server_hello`, WebSocket transport liveness,
   readiness, orderly disconnect, reconnect, and full resynchronization.
4. An asset-registry scan with deterministic ERROR/WARNING/INFO diagnostics.
5. `world_snapshot`, clock, action lifecycle, and debug presentation messages
   ordered by `state_version` and correlated by stable IDs.
6. `movement_arrived`, `movement_failed`, cancellation, and presentation status
   reports from Unity to Python.
7. `SemanticLocation`, `SemanticObject`, `InteractionSlot`, `NpcView`,
   `NpcNavigationController`, and animation-semantic adapter components.
8. A no-art greybox fixture, mock or recorded bridge fixture, basic debug panel,
   and Editor validation/export/diagnostic commands.
9. Python tests plus Unity EditMode/PlayMode or batchmode evidence covering both
   success and failure paths.

## Acceptance gates

- Unity and Python reject incompatible protocol versions with a readable error.
- Valid M2 assets register successfully; missing or duplicate required IDs
  block readiness and identify the exact cause.
- Full-V0 registry gaps are warnings, not silent omissions, during M2.
- Unity accepts an authoritative snapshot and never applies stale state deltas.
- `npc_01` can navigate to the home interaction position and the
  `CAFE_MORNING` workstation, then return home.
- At least `NO_PATH`, `SLOT_BLOCKED`, cancellation, timeout, and disconnect are
  reported or covered by deterministic fixtures.
- Reconnection creates new message IDs, repeats the full handshake and asset
  registration, and produces a fresh authoritative snapshot rather than
  guessing missed state.
- The reconnect snapshot version is not older than the last authority version
  acknowledged on the previous connection; simulation does not resume before
  the new `client_ready`.
- Inputs from an obsolete connection generation and late messages from its
  transport are rejected without authority mutation.
- Python state, needs, money, wage settlement, events, and `state_version` do
  not depend on animation success.
- M0/M1 tests, replay hashes, strict diagnostics, lint, and type checks remain
  green.
- Unity caches, credentials, runs, and machine-local files remain untracked.

## Forbidden scope

- activating all ten NPCs or any behavior outside the accepted M1 allowlist;
- complete M3 town content or final art;
- neural inference, training, generated datasets, or model packages;
- DeepSeek, player language, or dialogue implementation;
- learned, language, or Unity-side mutation of authority fields;
- third-party Unity assets or packages without explicit review;
- silent changes to frozen M0 or accepted M1 contracts.

## Stop and escalation conditions

Work reports to `AITOWN-ORCH` if a frozen protocol change is unavoidable, Unity
cannot import reproducibly with the pinned Editor, iCloud churn causes a
measurable source/import failure, or a required GUI action cannot be replaced by
batchmode or Editor tooling. Final-art assembly is not an M2 entry dependency.
