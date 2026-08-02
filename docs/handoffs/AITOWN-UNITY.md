# AITOWN-UNITY M2/M3 handoff

## M3 active live/evidence increment

### QA partial-artifact audit correction

QA correctly rejected the first partial bundle even though its descriptors
matched bytes and SHA-256: raw text replacement inserted literal
`<REPOSITORY_ROOT>` inside XML attribute values, making the sanitized EditMode
and PlayMode files malformed. The additive Unity fix now sanitizes XML through
`XmlDocument` attributes/text with markup-safe `REPOSITORY_ROOT`/`USER_HOME`
values, writes through `XmlWriter`, then reparses and reruns zero-skip plus
required-case validation before creating any artifact descriptor. A malformed
literal-angle-bracket attribute is a blocking `XmlException` test case.

The corrected final bundle is generated at
`/tmp/stwm-m3-unity-delivery-xmlfix.zKSD7B`; it supersedes the original
`/tmp/stwm-m3-unity-delivery.9ylDR4` bundle for QA assembly.

### Production 0.3 interoperability and evidence (current)

- Local test-only SIM inputs were cherry-picked without changing Unity
  authority ownership: `d110b37` -> `0586b87`, `22a076c` -> `bfe1095`,
  `71f45ec` -> `18d49e3`, and the rich-readiness schema separation
  `cfc566a` -> `8079bfb`. The delta-wire fix
  `364d444a48bac90984d30267957d94dabe45f67b` was consumed locally as
  `5263e19` after ORCH integrated it as `1c709a5`. ORCH must take only the new
  Unity-owned commit from this branch because those SIM commits are already
  integrated upstream.
- The strict producer input is now
  `stwm.simulation.m3-readiness-evidence/v1`. Unity explicitly rejects the old
  `stwm.qa.m3-readiness/v1`, which remains QA's repository report only.
- `TownBridgeClient.EnvelopeSending` exposes read-only wire evidence; it does
  not alter send order, state, or authority. The environment-gated live test
  retains the exact `asset_registry` envelope accepted by Python and one real
  authoritative `debug_decision_trace` JSONL record.
- The strengthened live case requires production 0.3 `/town`, the full
  registry/snapshot/Ready sequence, structured action and Top-K messages with
  zero strict-decode errors, then a second fresh ClientWebSocket connection
  that again reaches snapshot/Ready without state regression.
- Recorded fixtures still own deterministic coverage for multi-participant
  JointAction binding, stable distinct slots/facing, active snapshot rebind,
  explicit-null field-mask clear, terminal release, and complete Top-K rows.
- `M3AcceptanceEvidenceExporter.ExportPartialBatch` consumes only the real SIM
  artifact, real live registry/trace, zero-skip XML and batch log. It writes
  hashed/sanitized external Unity registry/semantic/test artifacts plus
  `stwm.unity.m3-partial-acceptance-evidence/v1`.
- The current one-day SIM artifact declares
  `full_slow_soak_executed=false`; therefore exporter status remains
  `PENDING`, `acceptance_eligible=false`, and the PASS-only QA release schema
  is never emitted. Separate SIM 7/30-day release artifacts remain an
  ORCH-ordered slow gate.

During the first strengthened live run, Unity correctly found a production
wire mismatch: `m3_server.py` used `model_dump_json(exclude_none=False)`, so
unset optional agent-delta fields were serialized as present nulls and violated
the frozen exact field-mask rule. Unity did not relax validation or claim a
pass. SIM fixed only delta payload serialization by preserving
`model_fields_set`; ordinary masks omit unmasked fields, explicit null clear is
retained, household deltas use the same rule, and full snapshot defaults remain
complete. After consuming the exact SHA above, Unity's unchanged strict
validator completed the real rerun with no bridge errors.

Current validation:

| Check | Result | External evidence |
| --- | --- | --- |
| real SIM one-day readiness input | PASS, schema `stwm.simulation.m3-readiness-evidence/v1`, `passed=true`, slow soak explicitly false | `/tmp/stwm-m3-unity-delivery.9ylDR4/m3-simulation-readiness-evidence.json` |
| combined EditMode | PASS, 46/46, skipped 0 | `/tmp/stwm-m3-editmode-final.xml` |
| SIM M3 bridge/wire regression | PASS, 11/11 | `uv run --frozen --extra test pytest python/tests/bridge/test_m3_bridge.py -q` |
| strengthened production live PlayMode | PASS, 4/4, skipped 0, strict decode errors 0; real first/second ClientWebSocket sessions | `/tmp/stwm-m3-live-final.xml`, `/tmp/stwm-m3-live-final.log` |
| combined M2/M3 default PlayMode regression | PASS, 6/6 executable cases; only the two environment-gated live cases explicitly ignored | `/tmp/stwm-m3-playmode-regression.xml` |
| live registry/debug inputs | PASS, accepted 0.3 registry 8/10/15/105/14 and real Top-K JSONL | `/tmp/stwm-m3-unity-delivery.9ylDR4/unity/live-full-registry.json`, `/tmp/stwm-m3-unity-delivery.9ylDR4/unity/live-debug-trace.jsonl` |
| partial acceptance bundle | valid hashed/sanitized artifact references; overall truthfully PENDING because 7/30 slow-soak producer artifacts are absent | `/tmp/stwm-m3-unity-delivery.9ylDR4/m3-unity-partial-acceptance-evidence.json` |

## M3 A/B and CONTRACTS consumption history

### C-F CONTRACTS consumption (historical)

- Unity-owned implementation commit: `93c21cb`.
- CONTRACTS inputs were cherry-picked in the required order:
  `3fe06f659479dcdc0e0834b2e49dff2e2608eb71` -> local `e00594b`, then
  `ca8944b0ca9cd17a85791527815d2ac81b403186` -> local `09fdb75`.
- The only semantic-instance inventory is
  `config/v0/semantic_instances.yaml`, exact schema
  `stwm.catalog.m3-semantic-instances/v1`, profile `M3_FULL`, catalog protocol
  `0.1.0`. Unity reads this repository-root YAML directly. The former
  `unity/Assets/AITown/Resources/M3FunctionalGrayboxManifest.json` and meta are
  deleted; no locator with an embedded instance copy remains.
- `TownBridgeClient` now has explicit compatibility profiles. M2 continues to
  use `M2_SCOPED_V020`; the M3 scene uses `M3_FULL_V030`, advertises
  `[0.3.0, 0.2.0]`, requires the server to select `0.3.0`, applies the full
  registry gate, and emits 0.3 envelopes. M3 fallback to 0.2 is rejected.
- Protocol 0.3 DTOs and validation cover structured participant bindings,
  JointAction identity/roles/order, facing and props, full snapshot
  `active_presentations`, explicit-presence field-mask clear, household delta,
  and Top-K Resolver tuple rules. Python-only household/debug messages are
  read-only Unity inputs.
- Full snapshots release and replace Unity presentation groups/slot claims,
  then rebind every authoritative active presentation. Action start/phase/
  cancellation operate across all participants without choosing authority
  participants or slots locally.
- `TownDebugPanel` renders ten-NPC authority state, household resources, and
  complete authoritative Top-K hard preview/prediction/utility/selection/
  Resolver rows. No trace is shown as PENDING rather than synthesized.
- The readiness/exporter framework records manifest source, catalog and target
  protocol versions, CONTRACTS gate PASS, and separate PENDING
  gates for SIM authority, real 0.3 `/town` interop, and final zero-skipped XML.
  It remains `acceptance_eligible=false` and does not fabricate final QA PASS.

At that increment, the M3 scene intentionally kept `connectOnStart=false` and
the `STWM_M3_LIVE_BRIDGE=1` seam remained unrun because no production server
had been supplied. The current increment above supersedes that evidence state.

Current validation evidence:

| Check | Result | External evidence |
| --- | --- | --- |
| authoritative YAML -> builder + `M3_FULL` + NavMesh | PASS, 8 locations, 10 NPCs, 74 objects, 105 slots, 840 routes | `/tmp/stwm-m3-contracts-graybox.log` |
| combined EditMode | PASS, 42/42, skipped 0 | `/tmp/stwm-m3-contracts-editmode-final.xml` |
| M3 PlayMode | 3 PASS, 0 fail, 1 explicit M3 live Ignore | `/tmp/stwm-m3-contracts-playmode-final.xml` |
| combined M2/M3 PlayMode regression | 6 PASS, 0 fail, 2 explicit live Ignore (M2/M3) | `/tmp/stwm-m3-contracts-playmode-all.xml` |
| readiness/exporter framework | local + CONTRACTS PASS; overall PENDING and acceptance-ineligible | `/tmp/stwm-m3-contracts-readiness` |

The M3 local PlayMode passes cover full-scene strict registry/routes, stable
two-participant slot/facing claims, and recorded 0.3 handshake -> full snapshot
active-action rebind -> explicit-null clear -> terminal claim release. The
ignored case is only the real production `ClientWebSocket` `/town` smoke;
therefore these results are not represented as final zero-skipped acceptance.
SIM authority/live evidence and the final QA composition remain deferred to
their owning deliveries.

### Historical A/B foundation

- Frozen entry: `2a51615` (`M3_EXECUTION_BASELINE` + ADR-0011).
- Branch: `codex/aitown-unity-m3`; no remote push.
- Unity A/B implementation commit: `664786f`.
- Scope: Unity-owned, wire-independent full-town functional greybox and local
  presentation seams. Python, protocol, and QA files are untouched.

Delivered in this increment:

- a single replaceable manifest-driven builder for 8 locations, 10 capsule
  NPCs, 74 semantic objects spanning all 15 types, 105 catalog-default slots,
  and a baked 840-route matrix;
- strict local `M3_FULL` scanning for exact IDs/types/locations/capabilities,
  component coverage, 14 animation semantics, four props, eight facing
  behaviors, and NavMesh reachability, while preserving `M2_SCOPED`;
- greybox-only `NpcPropPresenter`, `SocialFacingController`, and an
  `ActionPresentationGroup` that claims only explicit future authority
  bindings in stable order and rolls back atomically on local conflicts;
- a ten-NPC read-only Debug selector/surface with protocol-0.3 fields visibly
  PENDING rather than inferred;
- targeted EditMode/PlayMode fixtures and an external readiness exporter whose
  overall result is necessarily PENDING and `acceptance_eligible=false` until
  real CONTRACTS/SIM/test inputs exist.

The A/B projection described below has now been replaced by direct consumption
of the CONTRACTS-owned YAML above.

Deferred exactly as assigned:

- protocol 0.3 hello/DTOs and M3 registry wire profile;
- explicit-null field-mask application, participant DTO binding, active-action
  snapshot rebind, complete Top-K decision UI, and 0.3 live `/town` smoke;
- SIM-owned authority/transcript and final QA acceptance composition.

Validation evidence for this increment:

| Check | Result | External evidence |
| --- | --- | --- |
| deterministic builder + `M3_FULL` + NavMesh routes | PASS, 8 entrances, 105 slots, 840 complete routes | `/tmp/stwm-m3-graybox-final.log` |
| combined EditMode | PASS, 33/33, skipped 0 | `/tmp/stwm-m3-editmode-final.xml` |
| M3-only PlayMode fixture | PASS, 2/2, skipped 0 | `/tmp/stwm-m3-playmode-fixture-final.xml` |
| combined PlayMode regression | 5 PASS, 0 fail, 1 expected M2 live-smoke Ignore | `/tmp/stwm-m3-playmode-full-final.xml` |
| readiness framework export | local fixture PASS; overall PENDING, acceptance ineligible | `/tmp/stwm-m3-readiness-2a51615` |

The combined PlayMode skip is the accepted environment-gated M2 protocol 0.2
live smoke. It is not accepted as final M3 evidence. Protocol 0.3 live smoke is
not present in this increment and is reported PENDING rather than skipped/pass.
The fixed Editor was `6000.4.2f1` on macOS ARM64. A stale orphaned versioned
Licensing Client from the first failed batch launch was the only process
terminated; Unity Hub and all Editor processes were left untouched.

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
