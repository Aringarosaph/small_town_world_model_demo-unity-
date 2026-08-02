# AITOWN-UNITY M2 handoff

## Outcome

The M2 Unity-owned One-NPC Bridge slice is implemented as a reproducible,
no-art functional greybox for `npc_01: home_a -> cafe_bar -> home_a`. Python
Town Core remains the sole authority. Unity only renders authoritative state,
navigates locally, adapts animation semantics, exposes diagnostics, and reports
presentation outcomes.

The work is on `codex/aitown-unity-m2`; no remote push was performed.

## Authority inputs integrated

- Public-M1 base: `d014e70`.
- M2 execution baseline `0a4caa1`, read as authority and integrated by ORCH.
- ADR-0010 / protocol `0.2.0` contract `392f941`, read as authority and
  integrated by ORCH.
- Unity implementation foundation: `9fdf9c7`.
- ORCH integration of that foundation: `6d2fec1`.
- Editor: macOS ARM64 Unity `6000.4.2f1`.

All accepted ADRs through ADR-0010, the M2 baseline, M1 baseline/handoffs,
protocol/config, and the accepted M1 authority implementation were audited
before implementation.

## Delivered

- Minimal Unity project files under `unity/Packages` and
  `unity/ProjectSettings`, with exact official package versions frozen in the
  package lock.
- `TownBridgeClient` and `ClientWebSocketTransport` with the protocol envelope,
  ordered 0.2/0.1 hello preference, strict M2 0.2 selection, ping/pong
  keepalive, main-thread dispatch, bounded message-id content dedupe,
  `state_version` guards, explicit connection generations, reconnect/backoff,
  and mandatory full snapshot resynchronization.
- Direction-correct movement/presentation DTOs including the explicit
  `movement_cancelled` state and no cancellation-as-failure fallback.
- `SemanticLocation`, `SemanticObject`, `InteractionSlot`, `NpcView`,
  `NpcNavigationController`, and `NpcAnimationDriver`.
- Deterministic M2 registry scanning, blocking errors, full-V0 warning debt,
  JSON export, Editor menus, and batch validation.
- Primitive-only graybox scene, standalone NavMesh data, bidirectional route
  validation, and slot reachability checks for the bed, fridge, dining seat,
  and `CAFE_MORNING` workstation. All three frozen M2 work animation semantics
  map to the no-Animator functional fallback.
- `TownDebugPanel`, recorded-envelope playback, a frozen 0.2.0 handshake
  recording, EditMode tests, and in-memory mock-server PlayMode tests.
- A strict external acceptance exporter that validates SIM-owned
  `stwm.bridge.m2-authority-evidence/v1`, preserves its original JSON/JSONL
  pair and SHA reference, merges a continuously renumbered audited transcript,
  and emits the exact QA `stwm.qa.m2-acceptance-evidence/v1` observation shape.
- Unity usage/design documentation and this handoff.

No user art, third-party art, or non-M2 behavior/content was changed.

## Frozen package inventory

| Package | Version | Source |
| --- | --- | --- |
| `com.unity.ai.navigation` | `2.0.12` | Unity registry |
| `com.unity.nuget.newtonsoft-json` | `3.2.2` | Unity registry |
| `com.unity.test-framework` | `1.6.0` | built-in |
| required Unity modules | `1.0.0` | built-in |

## Protocol and authority boundary

- Active M2 session version is exactly `0.2.0`; `0.1.0` remains hello/legacy
  decode compatibility only.
- `movement_cancelled` is Unity-to-Python and reports only a local navigation
  stop. Reasons are `NAVIGATION_STOPPED`, `SCENE_UNLOADED`,
  `CLIENT_SHUTDOWN`, or `UNKNOWN`.
- `action_cancelled` is Python-to-Unity and is the only authoritative action
  cancellation result.
- Action-related correlation is always non-null and exactly equals
  `payload.action_id`.
- Unity never mutates clock, high-level location, action phase, reservations,
  needs, money, food, events, or authority `state_version`.

## Validation evidence

Commands and final results are recorded outside the repository:

| Check | Evidence | Result |
| --- | --- | --- |
| Unity EditMode | `/tmp/stwm-m2-editmode-final.xml` | PASS, 26/26, skipped 0 |
| Unity PlayMode, default Mock | `/tmp/stwm-m2-playmode-default.xml` | 3 PASS, live smoke 1 explicit Ignore; not final evidence |
| Unity PlayMode, real `/town` server | `/tmp/stwm-m2-playmode-final-live.xml` | PASS, 4/4, skipped 0; live smoke passed |
| Graybox rebuild/registry/routes | `/tmp/stwm-m2-graybox-final3.log` | PASS |
| Real SIM artifact -> Unity exporter -> QA strict checker | `/tmp/stwm-m2-acceptance-final` | PASS, `check_m2 --require-m2`, no failed gate |
| Cross-thread Python/ruff/mypy | ORCH integration | Deferred to ORCH's post-cherry-pick unified run as directed; Unity branch does not modify Python |

The final live run used the production `BridgeWebSocketServer` from ORCH
integration commit `19f769e`, bound only to `127.0.0.1:8765/town`. Unity used the real
`ClientWebSocketTransport`, completed protocol 0.2.0 hello, registry, full
snapshot and ready, then disconnected cleanly. This proves current production
transport/handshake interoperability in addition to the Mock state-machine
coverage.

## SIM integration surface consumed

The Unity thread did not modify Python authority code. SIM implemented that
owned surface on `codex/aitown-sim-m2`; AITOWN-ORCH integrated `a2a4814` (local
WebSocket runtime), `8cfea57` (authoritative movement cancellation), and
`7e11d24` (external authority evidence adapter). QA canonical evidence commit
`fcd64126` is integrated by ORCH as `19f769e`.

The consumed live surface preserves all of the following server behavior:

1. bind the local `/town` endpoint and assign a server-owned connection
   generation;
2. enforce direction-specific protocol 0.2.0 parsing and the complete
   hello/registry/snapshot/ready sequence;
3. block simulation until the new connection's `client_ready`;
4. reject future versions, obsolete generations, wrong action/agent/phase, and
   conflicting message-ID content without mutation;
5. process a valid `movement_cancelled` through one atomic authority
   transaction that releases reservations, advances `state_version` once, and
   emits Python-to-Unity `action_cancelled`;
6. record both `catalog_protocol_version=0.1.0` and
   `negotiated_protocol_version=0.2.0` in M2 session evidence.

Unity's endpoint defaults to `ws://127.0.0.1:8765/town`; the committed fixture
has `connectOnStart=true`, so Play immediately attempts the production
handshake and exposes failure/reconnect state in `TownDebugPanel`.

## Licensing observation

Batchmode initially encountered Unity Hub Licensing Client protocol `1.18.1`
instead of the Editor's versioned channel. Read-only inspection found one
orphaned `6000.4.2f1` Editor Licensing Client with `PPID=1`; only that process
was terminated under the producer's explicit boundary. Unity automatically
started its bundled client and completed entitlement resolution. Unity Hub and
all Editor processes were left untouched. No GUI activation remains required.

## Known limitations

- The default suite validates transport/lifecycle behavior with mock and
  recorded fixtures and does not by itself prove production interoperability.
  The environment-gated live smoke was also run successfully against the real
  Python server as recorded above; it remains default-Ignore so ordinary local
  runs do not require a server. Final evidence export rejects that skipped form.
- The graybox animation mapping is intentionally semantic/timed and has no
  final Animator Controller or art dependency.
- Full eight-location/ten-NPC registry gaps remain visible warnings and become
  blocking only with the M3 full heuristic town profile.
- The bridge logs deprecation warnings from Unity 6 object-discovery/IMGUI APIs;
  they do not affect compile, tests, authority, or M2 readiness.

## Reproduction

See `docs/unity/README.md` for controlled import, fixture rebuild, menus,
endpoint configuration, and exact Unity batchmode commands.
