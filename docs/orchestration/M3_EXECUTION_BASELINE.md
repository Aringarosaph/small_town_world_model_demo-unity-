# M3 execution baseline

Status: accepted and frozen by AITOWN-ORCH; implementation accepted at
`cc7f581da0548cb5aebd3d215db3e7bd93575d11` on 2026-08-03.

Base: accepted public `main@7b2618de09bd87eb49716ac40f1d0ba697f00351`.

## Product outcome

M3 delivers a complete heuristic small society that remains demonstrable with
no trained model and no API:

- exactly 10 enabled NPCs, 4 households, 8 locations, 22 behaviors, 15 object
  types, and 90 directed relationship edges;
- all household, schedule, object, action, event, relationship, and knowledge
  authority remains in Python;
- Unity `6000.4.2f1` presents the complete society as a functional greybox;
- fixed-rule multi-seed 7-day and 30-day runs are deterministic, replayable,
  invariant-safe, explainable, and bounded.

## Compatibility boundary

M3 is additive. The M1 one-agent engine/run/replay path and the M2 protocol
`0.2.0` bridge/evidence path remain accepted regression surfaces. M3 uses:

- society runtime and checkpoint schema `stwm.simulation.m3-authority-checkpoint/v1`;
- readiness evidence `stwm.qa.m3-readiness/v1`;
- release evidence `stwm.qa.m3-acceptance-evidence/v1`;
- negotiated protocol `0.3.0`, with `0.2.0` retained only for M2 compatibility;
- catalog provenance reported separately as `0.1.0`.

ADR-0011 owns protocol, checkpoint, candidate, JointAction, and compatibility
semantics. No implementation may overload `0.2.0` with the M3 payload shapes.

## Runtime increments

Work lands as integrated vertical increments:

1. Society initialization and scheduler: all ten NPCs enabled, due-agent queue,
   same-snapshot proposals, global IDs, M3 invariants, and M1 four-behavior
   compatibility.
2. Full semantic instances and all thirteen non-social behaviors, including
   shared-resource reservation and family economy conservation.
3. Work sessions for every NPC, overlap-aware coworker events, wages, purchases,
   consumption, and low-resource edge events.
4. Eight social behaviors plus `end_conversation`, directed relationship effects,
   witnessed/direct/told knowledge, conversations, and deterministic templates.
5. Invite/JointAction acceptance, participant barriers, atomic reservations,
   failure/cancellation release, checkpoint/resume, and authoritative replay.
6. Protocol `0.3.0`, full bridge profile, Unity full-town greybox, Debug UI, and
   external evidence.

The HeuristicOutcomeModel is the only M3 outcome provider. Candidate generation,
hard previews, masks, bounds, reservations, and final commits remain rule-owned.

## Full-town semantic manifest

The shared manifest uses stable IDs and catalog default slot counts. The strict
M3 registry requires:

- each home: one bed and one dining seat per resident; one fridge, shower, and
  TV; sofa slot capacity at least the household member count;
- workstations: cafe morning 2, cafe evening 2, shop 2, workshop 4, with the
  matching capability tags;
- shop: shelf capacity at least 2 and at least one checkout counter;
- cafe/bar: at least one cafe counter, one bar counter, four dining-seat slots,
  and two public-rest-seat slots;
- break seats: shop at least 2 and workshop at least 4 public-seat slots;
- park: route capacity at least 8, four public-seat slots, two leisure slots,
  and a two-slot conversation anchor;
- each public location: a two-slot conversation anchor;
- every configured behavior animation semantic, plus local coverage of props
  `MEAL`, `GROCERY_BAG`, `DRINK`, and `EVENT_ICON`;
- facing support for `greet`, `chat`, `joke`, `compliment`, `share_event`,
  `invite_join`, `apologize`, and `confront`;
- NavMesh reachability from each location entrance to every enabled required slot.

Python applies the server-owned `M3_FULL` semantic profile. Unity also applies
component, facing, prop, and route checks locally. Both gates must pass before
`client_ready`; either failure blocks the society. M2's scoped profile remains.

## Behavior and authority coverage

Every one of the 22 behaviors has a deterministic targeted fixture covering:

- legal and illegal candidate conditions;
- hard-cost preview and Resolver acceptance/rejection;
- reservation and complete/failed/cancelled lifecycle where applicable;
- allowed need, mood, relationship, knowledge, resource, and event effects;
- authoritative replay;
- Unity animation, prop, facing, and participant presentation semantics.

This is behavior coverage, not a requirement that each NPC execute every
behavior. All ten NPCs must nevertheless be enabled, scheduled, make decisions,
settle actions, and avoid permanent idle or work states. Across the complete
release soak set, all 22 behaviors must occur at least once; targeted fixtures
remain the proof for rare behavior correctness.

## Economy, relationship, and knowledge gates

For each household:

`final money = initial money + unique wages - grocery/cafe/bar charges`

`final food = initial food + 8 * grocery purchases - completed home meals`

Failed or cancelled actions do not charge resources, and every wage or charge
commits at most once. Money and food never become negative.

All 90 relationship edges remain explicit. A model-backed social effect may
change only the catalog mask and the frozen Target-to-Actor direction. The
committed action/event and before/after edge values must be traceable.

M3 covers `DIRECT_PARTICIPANT`, `WITNESSED`, and `TOLD`. `share_event` rejects an
unknown event. `PLAYER_TOLD`, truth conflicts, secrecy, multi-hop decay, and
epistemic graphs remain outside M3.

## Determinism, replay, and soak

The fixed release seeds are:

- 7-day: `12345`, `24680`, `97531`, `314159`, `271828`;
- 30-day: `12345`, `24680`, `97531`.

The canonical seed `12345` must match under repeated runs and driver chunks
`1`, `7`, and `60` minutes. Snapshot resume from each six-hour checkpoint and
authoritative replay must match final state, ledger, and ordered authority-log
hashes. Different seeds are reported; different hashes are not forced as an
invariant.

The PR fast gate includes all M0-M2 regressions, protocol/contracts, 22 targeted
fixtures, one-day ten-NPC smoke, JointAction probes, and short determinism. It
targets 10 minutes and fails at 15 minutes on 2 vCPU/4 GiB.

The release slow gate runs the full seed lists, replay/pathology/performance
reports, and zero-skipped Unity batchmode. Python may use at most four 2-vCPU/
4-GiB shards with a 60-minute hard limit. On the local MacBook Air, 30-day and
Unity gates run one instance at a time. Reproducible local Unity evidence remains
acceptable; a remote licensed Unity lane is optional.

## Pathology and performance gates

- Candidate count is at most 12 per agent and 120 per decision batch.
- No terminal, missing, or expired action owns a reservation; no slot has two
  owners.
- An agent with a legal non-idle candidate may not select only idle for 24 game
  hours. Work cannot remain active beyond its shift/action bound.
- A recoverable need may not stay at zero longer than 6 game hours.
- A household with zero food and less than one grocery purchase price must show
  wage/resource recovery within one configured workweek. All four households
  may not remain simultaneously below the money-low threshold for 7 days.
- For any relationship axis, more than 80% of edges may not remain within 0.01
  of either boundary for 7 consecutive days.
- Events are catalog-typed and exactly-once by semantic action key. Threshold
  events are edge-triggered. Total events are capped at 1,000 per game day and
  growth must remain linear.
- On the producer's Apple-silicon MacBook Air with Python 3.12, a 30-day single
  run must finish within 15 minutes, peak RSS must remain below 1 GiB, and the
  post-warmup RSS slope must not exceed 1 MiB per game day. Decision-batch p95 is
  below 50 ms and tick p99 below 100 ms. Hardware, OS, Python, wall time, and RSS
  collection method are recorded with the evidence.

## Unity acceptance

The M3 functional greybox contains all ten `NpcView`s, eight semantic locations,
the full instance manifest, and no final-art dependency. Unity must demonstrate:

- complete snapshot replacement, explicit-null delta clearing, active-action
  rebind, and stale/version rejection;
- concurrent navigation and presentation without duplicate slot claims;
- central two-or-more-participant JointAction start/phase/cancel/fail/reconnect;
- all behavior animation/prop/facing mappings;
- a read-only ten-NPC Debug UI showing authority state, household resources,
  relations, known events, Top-K candidates, hard preview, heuristic prediction,
  utility terms, selection, and Resolver conflicts;
- zero-skipped EditMode and PlayMode results plus a real protocol `0.3.0` `/town`
  smoke against the production Python bridge.

Unity consumes recorded/real M3 slices; it does not run the 30-day soak in real
time and never fabricates Python authority evidence.

## Explicit exclusions

- M4 neural inference, training data, cloud training, switching, and calibration;
- M5 DeepSeek, player utterance parsing, PLAYER_TOLD, and API credentials;
- M6 fixed golden-chain demonstration and final art;
- any post-V0 Claim/Belief, Commitment, GNN, RSSM, RL, institution, or free
  behavior-generation system.

## Stop conditions

Stop and return to AITOWN-ORCH before changing a frozen ID, numeric direction,
catalog count, authority owner, or the boundaries above. Other implementation
choices are delegated to the responsible task owner.
