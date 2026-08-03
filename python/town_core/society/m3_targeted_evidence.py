"""Executable deterministic M3 targeted probes for release evidence.

The producer calls the same functions exercised by the parameterized pytest
surface. Every PASS record therefore names an independently executable probe;
ordinary soak occurrence is never relabeled as targeted coverage.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, cast

from town_core.domain.config_models import CatalogBundle, MoodValues, NeedValues
from town_core.domain.decision_models import HardCostPreview
from town_core.domain.enums import (
    ActionPhase,
    BehaviorId,
    EventType,
    EventWitnessScope,
    JointActionAuthority,
    KnowledgeAcquisitionType,
    MoodAxis,
    NeedName,
    ProposalResult,
    RelationshipAxis,
)
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.domain.m3_models import INVITED_ACTIVITY_ALLOWLIST
from town_core.domain.state_models import KnowledgeRecord, WorldEvent, WorldState
from town_core.simulation.clock import RuntimeMode
from town_core.society.checkpoint import advance_authority_log_hash, checkpoint_hash, knowledge_key
from town_core.society.engine import SocietyEngine, _TickContext
from town_core.society.initialization import build_initial_society_checkpoint
from town_core.society.invariants import assert_society_invariants
from town_core.society.models import (
    AuthorityCheckpoint,
    ConversationRecord,
    ScoredSocietyCandidate,
    SocietyAdvanceResult,
    WorkSessionRecord,
)
from town_core.society.rules import stable_unit
from town_core.society.transactions import apply_transaction_record

BEHAVIOR_PROBE_KEYS = (
    "legal_candidate",
    "illegal_candidate",
    "hard_cost_preview",
    "resolver_accept",
    "resolver_reject",
    "reservation_and_lifecycle",
    "allowed_effects",
    "authoritative_replay",
)

AUTHORITY_PROBE_KEYS = (
    "knowledge_unknown_share_rejected",
    "joint_action_cancel_release",
    "joint_action_failure_release",
    "joint_action_timeout_release",
)
INVITATION_ACCEPTANCE_PROBE_KEY = "joint_action_invitation_acceptance"

ProbeKey = Literal[
    "legal_candidate",
    "illegal_candidate",
    "hard_cost_preview",
    "resolver_accept",
    "resolver_reject",
    "reservation_and_lifecycle",
    "allowed_effects",
    "authoritative_replay",
]
AuthorityProbeKey = Literal[
    "knowledge_unknown_share_rejected",
    "joint_action_cancel_release",
    "joint_action_failure_release",
    "joint_action_timeout_release",
]


class TargetedProbeFailure(ValueError):
    """Raised instead of emitting a false targeted PASS record."""


@dataclass(slots=True)
class _Assertions:
    count: int = 0

    def require(self, condition: bool, message: str) -> None:
        self.count += 1
        if not condition:
            raise TargetedProbeFailure(message)


def _behavior_test_id(behavior_id: BehaviorId, probe: str) -> str:
    return (
        f"python/tests/society/test_m3_targeted_evidence.py::test_behavior_targeted_probe[{behavior_id.value}-{probe}]"
    )


def _authority_test_id(probe: str) -> str:
    return f"python/tests/society/test_m3_targeted_evidence.py::test_authority_targeted_probe[{probe}]"


def _pass_record(test_id: str, assertion_count: int) -> dict[str, object]:
    if assertion_count <= 0:
        raise TargetedProbeFailure(f"targeted probe made no assertions: {test_id}")
    return {"status": "PASS", "test_ids": [test_id], "assertion_count": assertion_count}


def _move_agent(
    checkpoint: AuthorityCheckpoint,
    *,
    agent_id: str,
    destination: str,
) -> AuthorityCheckpoint:
    world = checkpoint.world
    agent = world.agents[agent_id]
    if agent.current_location_id == destination:
        return checkpoint
    locations = dict(world.locations)
    origin = locations[agent.current_location_id]
    target = locations[destination]
    locations[origin.location_id] = origin.model_copy(
        update={"current_agent_ids": [item for item in origin.current_agent_ids if item != agent_id]}
    )
    locations[destination] = target.model_copy(
        update={"current_agent_ids": sorted([*target.current_agent_ids, agent_id])}
    )
    agents = dict(world.agents)
    agents[agent_id] = agent.model_copy(update={"current_location_id": destination})
    return checkpoint.model_copy(update={"world": world.model_copy(update={"agents": agents, "locations": locations})})


def _fixture_checkpoint(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    behavior_id: BehaviorId,
) -> AuthorityCheckpoint:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    minute = 485 if behavior_id is BehaviorId.TAKE_BREAK else 600
    agents = {
        agent_id: agent.model_copy(
            update={
                "needs": NeedValues(hunger=0.5, energy=0.5, hygiene=0.5, fun=0.5, social=0.5),
                "mood": MoodValues(valence=0.0, stress=0.5),
                "decision_due_at": 10_000,
            }
        )
        for agent_id, agent in checkpoint.world.agents.items()
    }
    world = checkpoint.world.model_copy(update={"game_minute": minute, "state_version": minute, "agents": agents})
    checkpoint = checkpoint.model_copy(update={"world": world})
    actor = checkpoint.world.agents["npc_01"]

    work_sessions: dict[str, WorkSessionRecord] = {}
    if behavior_id in {BehaviorId.WORK_SHIFT, BehaviorId.TAKE_BREAK}:
        work_sessions["work_session_npc_01_day_0000"] = WorkSessionRecord(
            session_id="work_session_npc_01_day_0000",
            agent_id="npc_01",
            day=0,
            start_game_minute=360,
            end_game_minute=840,
            grace_minutes=15,
            effective_work_minutes=125 if behavior_id is BehaviorId.TAKE_BREAK else 0,
        )
    if behavior_id is BehaviorId.TAKE_BREAK:
        checkpoint = _move_agent(
            checkpoint,
            agent_id="npc_01",
            destination=actor.assigned_work_location_id,
        )
    if behavior_id is BehaviorId.BUY_GROCERIES:
        households = dict(checkpoint.world.households)
        household = households[actor.household_id]
        households[actor.household_id] = household.model_copy(update={"food_units": 0})
        checkpoint = checkpoint.model_copy(
            update={"world": checkpoint.world.model_copy(update={"households": households})}
        )

    relationships = list(checkpoint.world.relationships)
    if behavior_id in {BehaviorId.APOLOGIZE, BehaviorId.CONFRONT}:
        relationships = [
            edge.model_copy(update={"tension": 0.8})
            if edge.source_agent_id == "npc_02" and edge.target_agent_id == "npc_01"
            else edge
            for edge in relationships
        ]
        checkpoint = checkpoint.model_copy(
            update={"world": checkpoint.world.model_copy(update={"relationships": relationships})}
        )

    events: list[WorldEvent] = []
    knowledge: dict[str, KnowledgeRecord] = {}
    if behavior_id is BehaviorId.SHARE_EVENT:
        event = WorldEvent(
            event_id="event_00000001",
            event_type=EventType.POSITIVE_INTERACTION,
            game_minute=590,
            location_id="home_a",
            actor_ids=["npc_01"],
            affected_agent_ids=["npc_02"],
            witness_agent_ids=[],
            source_action_id=None,
            importance=0.8,
            witness_scope=EventWitnessScope.PARTICIPANTS_ONLY,
            payload={"fixture": "known_share"},
        )
        record = KnowledgeRecord(
            agent_id="npc_01",
            event_id=event.event_id,
            source_agent_id=None,
            acquisition_type=KnowledgeAcquisitionType.DIRECT_PARTICIPANT,
            confidence=1.0,
            first_known_minute=590,
            last_reinforced_minute=590,
        )
        events = [event]
        knowledge[knowledge_key("npc_01", event.event_id)] = record
        fixture_agents = dict(checkpoint.world.agents)
        fixture_agents["npc_01"] = fixture_agents["npc_01"].model_copy(update={"known_event_ids": [event.event_id]})
        checkpoint = checkpoint.model_copy(
            update={"world": checkpoint.world.model_copy(update={"agents": fixture_agents, "event_cursor": 1})}
        )

    conversations: dict[str, ConversationRecord] = {}
    if behavior_id is BehaviorId.END_CONVERSATION:
        conversation = ConversationRecord(
            conversation_id="conversation_00000001",
            participant_ids=["npc_01", "npc_02"],
            started_at_game_minute=590,
            last_activity_game_minute=590,
        )
        conversations[conversation.conversation_id] = conversation
        checkpoint = checkpoint.model_copy(
            update={
                "world": checkpoint.world.model_copy(update={"dialogue_session_ids": [conversation.conversation_id]})
            }
        )

    checkpoint = checkpoint.model_copy(
        update={
            "events": events,
            "knowledge_records": knowledge,
            "work_sessions": work_sessions,
            "conversations": conversations,
        }
    )
    assert_society_invariants(checkpoint, catalog, m3_catalogs)
    return checkpoint


def _scored_candidate(
    engine: SocietyEngine,
    context: _TickContext,
    behavior_id: BehaviorId,
) -> tuple[WorldState, ScoredSocietyCandidate]:
    source = context.provisional_world(state_version=context.source.world.state_version)
    session = context.work_sessions.get("work_session_npc_01_day_0000")
    candidates = engine.rulebook.enumerate_candidates(
        source,
        "npc_01",
        work_session=session,
        conversations=context.conversations,
        event_importance={event.event_id: float(event.importance) for event in context.events},
        events_by_id={event.event_id: event for event in context.events},
        reserved_money=0,
        reserved_food=0,
        next_candidate_id=lambda: f"candidate_{context.bump('candidate'):08d}",
        behavior_allowlist=frozenset({behavior_id}),
    )
    matching = [item for item in candidates if item.candidate.behavior_id is behavior_id]
    if not matching:
        raise TargetedProbeFailure(f"legal fixture produced no {behavior_id.value} candidate")
    prediction = engine.rulebook.predict(
        source,
        matching[0],
        prediction_id=f"prediction_{context.bump('prediction'):08d}",
    )
    scored = engine.rulebook.score_candidates(
        source,
        [matching[0]],
        {matching[0].candidate.candidate_id: prediction},
        work_session=session,
        recent_behavior=None,
        event_importance={event.event_id: float(event.importance) for event in context.events},
    )[0]
    return source, scored


def _start_action(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    behavior_id: BehaviorId,
) -> tuple[AuthorityCheckpoint, SocietyEngine, SocietyAdvanceResult, str, set[str]]:
    initial = _fixture_checkpoint(catalog, m3_catalogs, behavior_id)
    engine = SocietyEngine(catalog, m3_catalogs, initial)
    context = _TickContext(initial, initial.world.game_minute)
    source, scored = _scored_candidate(engine, context, behavior_id)
    proposal = engine._proposal(source, scored, f"proposal_{context.bump('proposal'):08d}")
    result, action_id = engine._resolve_and_create(context, source, proposal, scored)
    if result is not ProposalResult.ACCEPTED or action_id is None:
        raise TargetedProbeFailure(f"Resolver did not accept legal {behavior_id.value}: {result.value}")
    start = engine._commit(context, advances_time=False)
    reservations = set(engine.export_checkpoint().action_runtimes[action_id].reservation_ids)
    return initial, engine, start, action_id, reservations


def _replay_results(
    initial: AuthorityCheckpoint,
    results: Iterable[SocietyAdvanceResult],
) -> AuthorityCheckpoint:
    replayed = initial
    sequence = replayed.authority_record_count
    authority_hash = replayed.authority_log_hash
    for result in results:
        for raw_record in result.authority_records:
            sequence += 1
            envelope = {
                "schema": "stwm.simulation.m3-authority-record/v1",
                "sequence": sequence,
                "kind": raw_record["kind"],
                "payload": raw_record["payload"],
            }
            if raw_record["kind"] == "transaction":
                payload = raw_record["payload"]
                if not isinstance(payload, dict):
                    raise TargetedProbeFailure("targeted replay transaction payload is not an object")
                replayed = apply_transaction_record(replayed, payload)
            authority_hash = advance_authority_log_hash(authority_hash, envelope)
            replayed = replayed.model_copy(
                update={"authority_record_count": sequence, "authority_log_hash": authority_hash}
            )
    return replayed


def _expected_hard_cost(catalog: CatalogBundle, behavior_id: BehaviorId) -> HardCostPreview:
    if behavior_id is BehaviorId.EAT_AT_HOME:
        return HardCostPreview(household_food_units=-1)
    if behavior_id is BehaviorId.BUY_GROCERIES:
        return HardCostPreview(
            household_money=-catalog.economy.groceries.price,
            household_food_units=catalog.economy.groceries.food_units_delta,
        )
    if behavior_id is BehaviorId.EAT_AT_CAFE:
        return HardCostPreview(household_money=-catalog.economy.cafe_meal.price)
    if behavior_id is BehaviorId.DRINK_AT_BAR:
        return HardCostPreview(household_money=-catalog.economy.bar_drink.price)
    return HardCostPreview()


def execute_behavior_probe(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    behavior_id: BehaviorId,
    probe: ProbeKey,
) -> int:
    assertions = _Assertions()
    checkpoint = _fixture_checkpoint(catalog, m3_catalogs, behavior_id)
    engine = SocietyEngine(catalog, m3_catalogs, checkpoint)
    context = _TickContext(checkpoint, checkpoint.world.game_minute)
    source, scored = _scored_candidate(engine, context, behavior_id)
    candidate = scored.candidate.candidate

    if probe == "legal_candidate":
        assertions.require(candidate.behavior_id is behavior_id, "legal candidate behavior mismatch")
        assertions.require(candidate.actor_id == "npc_01", "legal candidate actor mismatch")
        assertions.require(
            candidate.destination_location_id is not None,
            "legal candidate has no deterministic destination",
        )
    elif probe == "illegal_candidate":
        disabled_agents = dict(source.agents)
        disabled_agents["npc_01"] = disabled_agents["npc_01"].model_copy(update={"enabled": False})
        disabled = source.model_copy(update={"agents": disabled_agents})
        illegal = engine.rulebook.enumerate_candidates(
            disabled,
            "npc_01",
            work_session=context.work_sessions.get("work_session_npc_01_day_0000"),
            conversations=context.conversations,
            event_importance={event.event_id: float(event.importance) for event in context.events},
            reserved_money=0,
            reserved_food=0,
            next_candidate_id=lambda: "candidate_99999999",
            behavior_allowlist=frozenset({behavior_id}),
        )
        assertions.require(illegal == [], "disabled actor received an illegal candidate")
        assertions.require(candidate.behavior_id is behavior_id, "illegal probe lost its behavior fixture")
    elif probe == "hard_cost_preview":
        expected = _expected_hard_cost(catalog, behavior_id)
        assertions.require(candidate.hard_cost_preview == expected, "hard-cost preview differs from economy rules")
        assertions.require(
            candidate.hard_cost_preview.household_money <= 0,
            "candidate preview attempts to mint household money",
        )
    elif probe == "resolver_accept":
        proposal = engine._proposal(source, scored, f"proposal_{context.bump('proposal'):08d}")
        result, action_id = engine._resolve_and_create(context, source, proposal, scored)
        assertions.require(result is ProposalResult.ACCEPTED, "legal candidate was rejected")
        assertions.require(action_id is not None and action_id in context.active_actions, "accepted action missing")
        assertions.require(
            action_id is not None and context.agents["npc_01"].current_action_id == action_id,
            "accepted action did not claim its actor",
        )
    elif probe == "resolver_reject":
        proposal = engine._proposal(source, scored, f"proposal_{context.bump('proposal'):08d}")
        stale = proposal.model_copy(update={"state_version": max(0, proposal.state_version - 1)})
        result, action_id = engine._resolve_and_create(context, source, stale, scored)
        assertions.require(result is ProposalResult.STATE_STALE, "stale proposal was not rejected")
        assertions.require(action_id is None, "rejected proposal created an action")
        assertions.require(not context.active_actions, "rejected proposal mutated active actions")
    elif probe == "reservation_and_lifecycle":
        _, accepted_engine, _, action_id, reservations = _start_action(catalog, m3_catalogs, behavior_id)
        assertions.require(bool(reservations), "accepted action created no participant reservation")
        assertions.require(
            any(accepted_engine.export_checkpoint().reservations[item].kind == "PARTICIPANT" for item in reservations),
            "accepted action lacks its participant reservation",
        )
        terminal = accepted_engine.cancel_action(action_id, reason="M3_TARGETED_BEHAVIOR_LIFECYCLE")
        final = accepted_engine.export_checkpoint()
        assertions.require(action_id not in final.world.active_actions, "cancelled action remains active")
        assertions.require(not reservations.intersection(final.reservations), "cancel leaked reservations")
        assertions.require(
            any(item["phase"] == ActionPhase.CANCELLED.value for item in terminal.actions),
            "cancel transaction lacks the terminal phase",
        )
    elif probe == "allowed_effects":
        behavior = engine.rulebook.behaviors[behavior_id]
        prediction = scored.prediction
        for need_axis in NeedName:
            value = float(getattr(prediction.need_delta_preview, need_axis.value))
            bounds = behavior.output_bounds.need_deltas.get(need_axis)
            assertions.require(
                value == 0.0 if bounds is None else float(bounds.minimum) <= value <= float(bounds.maximum),
                f"predicted {need_axis.value} effect exceeds catalog bounds",
            )
        for mood_axis in MoodAxis:
            value = float(getattr(prediction.actor_mood_delta, mood_axis.value))
            bounds = behavior.output_bounds.actor_mood_deltas.get(mood_axis)
            assertions.require(
                value == 0.0 if bounds is None else float(bounds.minimum) <= value <= float(bounds.maximum),
                f"predicted actor {mood_axis.value} effect exceeds catalog bounds",
            )
        assertions.require(
            set(prediction.event_probabilities) == set(behavior.emitted_event_types),
            "predicted event types exceed the catalog allowlist",
        )
        relationship = prediction.relationship_delta_target_to_actor
        for relationship_axis in RelationshipAxis:
            bounds = behavior.output_bounds.relationship_target_to_actor.get(relationship_axis)
            value = 0.0 if relationship is None else float(getattr(relationship, relationship_axis.value))
            assertions.require(
                value == 0.0 if bounds is None else float(bounds.minimum) <= value <= float(bounds.maximum),
                f"predicted relationship {relationship_axis.value} effect exceeds catalog bounds",
            )
    elif probe == "authoritative_replay":
        initial, accepted_engine, start, action_id, _ = _start_action(catalog, m3_catalogs, behavior_id)
        terminal = accepted_engine.cancel_action(action_id, reason="M3_TARGETED_BEHAVIOR_REPLAY")
        replayed = _replay_results(initial, [start, terminal])
        final = accepted_engine.export_checkpoint()
        assertions.require(checkpoint_hash(replayed) == checkpoint_hash(final), "replay checkpoint hash differs")
        assertions.require(replayed.authority_log_hash == final.authority_log_hash, "replay authority hash differs")
        assertions.require(replayed.transaction_chain_hash == final.transaction_chain_hash, "replay chain differs")
        assert_society_invariants(replayed, catalog, m3_catalogs)
        assertions.require(True, "replayed checkpoint invariant failure")
    else:
        raise TargetedProbeFailure(f"unsupported behavior probe: {probe}")
    return assertions.count


def _unknown_share_probe(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> tuple[int, dict[str, object]]:
    assertions = _Assertions()
    known = _fixture_checkpoint(catalog, m3_catalogs, BehaviorId.SHARE_EVENT)
    known_engine = SocietyEngine(catalog, m3_catalogs, known)
    known_context = _TickContext(known, known.world.game_minute)
    _, scored = _scored_candidate(known_engine, known_context, BehaviorId.SHARE_EVENT)

    agents = dict(known.world.agents)
    agents["npc_01"] = agents["npc_01"].model_copy(update={"known_event_ids": []})
    unknown = known.model_copy(
        update={
            "world": known.world.model_copy(update={"agents": agents}),
            "knowledge_records": {},
        }
    )
    engine = SocietyEngine(catalog, m3_catalogs, unknown)
    context = _TickContext(unknown, unknown.world.game_minute)
    source = context.provisional_world(state_version=unknown.world.state_version)
    proposal = engine._proposal(source, scored, f"proposal_{context.bump('proposal'):08d}")
    before_hash = checkpoint_hash(engine.export_checkpoint())
    before_version = engine.state.state_version
    result, action_id = engine._resolve_and_create(context, source, proposal, scored)
    after_hash = checkpoint_hash(engine.export_checkpoint())
    assertions.require(result is ProposalResult.TARGET_UNAVAILABLE, "unknown share was not rejected")
    assertions.require(action_id is None, "unknown share created an action")
    assertions.require(before_hash == after_hash, "unknown-share rejection mutated authority")
    assertions.require(before_version == engine.state.state_version, "unknown-share rejection changed version")
    return assertions.count, {
        "result": result.value,
        "before_checkpoint_hash": before_hash,
        "after_checkpoint_hash": after_hash,
        "before_state_version": before_version,
        "after_state_version": engine.state.state_version,
        "authority_transaction_count": 0,
    }


def _start_traveling_joint(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    *,
    runtime_mode: RuntimeMode,
) -> tuple[AuthorityCheckpoint, SocietyEngine, SocietyAdvanceResult, str, set[str]]:
    initial = _fixture_checkpoint(catalog, m3_catalogs, BehaviorId.WALK_IN_PARK)
    engine = SocietyEngine(
        catalog,
        m3_catalogs,
        initial,
        runtime_mode=runtime_mode,
        movement_timeout_minutes=1,
    )
    context = _TickContext(initial, initial.world.game_minute)
    source, base = _scored_candidate(engine, context, BehaviorId.WALK_IN_PARK)
    joint_candidate = base.candidate.candidate.model_copy(update={"target_agent_id": "npc_02"})
    scored = base.model_copy(update={"candidate": base.candidate.model_copy(update={"candidate": joint_candidate})})
    actor_proposal_id = f"proposal_{context.bump('proposal'):08d}"
    target_proposal_id = f"proposal_{context.bump('proposal'):08d}"
    proposal = engine._proposal(source, scored, actor_proposal_id)
    result, action_id = engine._resolve_and_create(
        context,
        source,
        proposal,
        scored,
        force_joint=True,
        source_invite_action_id="action_99999999",
        participant_proposal_ids={"npc_01": actor_proposal_id, "npc_02": target_proposal_id},
    )
    if result is not ProposalResult.ACCEPTED or action_id is None:
        raise TargetedProbeFailure(f"central Resolver failed targeted JointAction: {result.value}")
    start = engine._commit(context, advances_time=False)
    checkpoint = engine.export_checkpoint()
    if checkpoint.world.active_actions[action_id].phase is not ActionPhase.TRAVELING:
        raise TargetedProbeFailure("targeted JointAction did not enter TRAVELING")
    reservations = set(checkpoint.action_runtimes[action_id].reservation_ids)
    return initial, engine, start, action_id, reservations


def _joint_terminal_probe(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    terminal: Literal["cancel", "failure", "timeout"],
) -> tuple[int, dict[str, object]]:
    assertions = _Assertions()
    mode = RuntimeMode.UNITY_LIVE if terminal == "timeout" else RuntimeMode.HEADLESS_FAST
    initial, engine, start, action_id, reservations = _start_traveling_joint(
        catalog,
        m3_catalogs,
        runtime_mode=mode,
    )
    active = engine.export_checkpoint()
    joint = active.joint_actions[action_id].joint_action
    participant_ids = sorted(item.agent_id for item in joint.participants)
    reservation_records = [active.reservations[item] for item in sorted(reservations)]
    reservation_kind_counts = {
        kind: sum(item.kind == kind for item in reservation_records)
        for kind in ("OBJECT_SLOT", "HOUSEHOLD_RESOURCE", "LOCATION", "PARTICIPANT")
    }
    reservation_owner_action_ids = sorted({item.owner_action_id for item in reservation_records})
    participant_ownership_count = sum(
        active.world.agents[agent_id].current_action_id == action_id for agent_id in participant_ids
    )
    assertions.require(joint.authority is JointActionAuthority.CENTRAL_RESOLVER, "joint authority is not central")
    assertions.require(
        participant_ids == ["npc_01", "npc_02"],
        "joint participants differ",
    )
    assertions.require(bool(reservations), "joint action has no atomic reservations")
    assertions.require(
        reservation_owner_action_ids == [action_id],
        "joint reservations do not share the central action owner",
    )
    assertions.require(
        reservation_kind_counts["PARTICIPANT"] == len(participant_ids),
        "joint action lacks one participant reservation per participant",
    )
    assertions.require(
        participant_ownership_count == len(participant_ids),
        "joint action does not exclusively own every participant",
    )
    before_hash = checkpoint_hash(active)
    before_version = active.world.state_version
    if terminal == "cancel":
        terminal_result = engine.cancel_action(action_id, reason="M3_TARGETED_JOINT_CANCEL")
        expected_phase = ActionPhase.CANCELLED
    elif terminal == "failure":
        terminal_result = engine.fail_action(action_id, reason="M3_TARGETED_JOINT_FAILURE")
        expected_phase = ActionPhase.FAILED
    else:
        runtime = active.action_runtimes[action_id]
        timeout_minute = max(runtime.travel_arrival_minutes.values()) + 2
        terminal_result = engine.advance_to(timeout_minute)
        expected_phase = ActionPhase.FAILED
    final = engine.export_checkpoint()
    assertions.require(action_id not in final.world.active_actions, "terminal joint action remains active")
    assertions.require(action_id not in final.joint_actions, "terminal JointAction ledger entry remains active")
    assertions.require(not reservations.intersection(final.reservations), "terminal joint leaked reservations")
    assertions.require(
        all(final.world.agents[item].current_action_id != action_id for item in ("npc_01", "npc_02")),
        "terminal joint retained its participant ownership",
    )
    assertions.require(
        all(action_id not in obj.occupied_slots.values() for obj in final.world.objects.values()),
        "terminal joint retained object occupancy",
    )
    assertions.require(
        any(
            item["action_id"] == action_id and item["phase"] == expected_phase.value for item in terminal_result.actions
        ),
        "terminal joint authority phase was not emitted",
    )
    replayed = _replay_results(initial, [start, terminal_result])
    replay_match = checkpoint_hash(replayed) == checkpoint_hash(final)
    assertions.require(replay_match, "joint terminal transaction replay differs")
    assertions.require(replayed.authority_log_hash == final.authority_log_hash, "joint authority replay hash differs")
    assert_society_invariants(final, catalog, m3_catalogs)
    assertions.require(True, "joint terminal invariant failure")
    return assertions.count, {
        "action_id": action_id,
        "terminal_path": terminal,
        "before_checkpoint_hash": before_hash,
        "after_checkpoint_hash": checkpoint_hash(final),
        "before_state_version": before_version,
        "after_state_version": final.world.state_version,
        "authority_transaction_count": len(terminal_result.transactions),
        "joint_authority": joint.authority.value,
        "participant_ids": participant_ids,
        "participant_ownership_count_before": participant_ownership_count,
        "reservation_count_before": len(reservations),
        "reservation_kind_counts_before": reservation_kind_counts,
        "reservation_owner_action_ids_before": reservation_owner_action_ids,
        "reservation_remnant_count": len(reservations.intersection(final.reservations)),
        "terminal_phase": expected_phase.value,
        "replay_match": replay_match,
    }


def execute_invitation_acceptance_probe(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> tuple[int, dict[str, object]]:
    """Drive a real invite decision through acceptance and its JointAction."""

    assertions = _Assertions()
    initial = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    agents = {
        agent_id: agent.model_copy(
            update={"needs": NeedValues(hunger=0.5, energy=0.5, hygiene=0.5, fun=0.0, social=0.0)}
        )
        for agent_id, agent in initial.world.agents.items()
    }
    initial = initial.model_copy(update={"world": initial.world.model_copy(update={"agents": agents})})
    assert_society_invariants(initial, catalog, m3_catalogs)
    engine = SocietyEngine(
        catalog,
        m3_catalogs,
        initial,
        behavior_allowlist=frozenset({BehaviorId.IDLE, BehaviorId.INVITE_JOIN}),
    )
    results: list[SocietyAdvanceResult] = []
    invite_outcomes: dict[str, tuple[float, float, str | None, str | None]] = {}
    joint_action_id: str | None = None
    active_joint: AuthorityCheckpoint | None = None
    accepted_event: WorldEvent | None = None

    for minute in range(1, 121):
        result = engine.advance_to(minute)
        results.append(result)
        checkpoint = engine.export_checkpoint()
        for runtime in checkpoint.action_runtimes.values():
            candidate = runtime.candidate.candidate
            if candidate.behavior_id is not BehaviorId.INVITE_JOIN:
                continue
            probability = runtime.prediction.acceptance_probability
            if probability is None:
                continue
            draw = stable_unit(
                "m3-social-outcome-v1",
                checkpoint.world.random_seed,
                runtime.action_id,
                candidate.behavior_id.value,
                runtime.actor_id,
                candidate.target_agent_id,
            )
            invite_outcomes[runtime.action_id] = (
                float(probability),
                draw,
                candidate.target_agent_id,
                runtime.candidate.invited_activity_id.value if runtime.candidate.invited_activity_id else None,
            )
        for action_id, record in sorted(checkpoint.joint_actions.items()):
            matching = next(
                (
                    event
                    for event in checkpoint.events
                    if event.event_type is EventType.INVITATION_ACCEPTED
                    and event.source_action_id == record.source_invite_action_id
                ),
                None,
            )
            if matching is not None:
                joint_action_id = action_id
                active_joint = checkpoint
                accepted_event = matching
                break
        if joint_action_id is not None:
            break

    assertions.require(joint_action_id is not None, "restricted invite fixture produced no accepted JointAction")
    assertions.require(active_joint is not None, "accepted JointAction has no authority checkpoint")
    assertions.require(accepted_event is not None, "accepted invitation emitted no INVITATION_ACCEPTED event")
    if joint_action_id is None or active_joint is None or accepted_event is None:
        raise TargetedProbeFailure("accepted invitation fixture lost its authority observation")
    joint_record = active_joint.joint_actions[joint_action_id]
    joint = joint_record.joint_action
    invite_action_id = joint_record.source_invite_action_id
    invite_outcome = invite_outcomes.get(invite_action_id)
    assertions.require(invite_outcome is not None, "accepted invite did not pass through a scored social outcome")
    if invite_outcome is None:
        raise TargetedProbeFailure("accepted invitation fixture lost its deterministic outcome")
    probability, draw, target_agent_id, invited_activity_id = invite_outcome
    participant_ids = sorted(item.agent_id for item in joint.participants)
    reservations = set(active_joint.action_runtimes[joint_action_id].reservation_ids)
    reservation_records = [active_joint.reservations[item] for item in sorted(reservations)]
    reservation_kind_counts = {
        kind: sum(item.kind == kind for item in reservation_records)
        for kind in ("OBJECT_SLOT", "HOUSEHOLD_RESOURCE", "LOCATION", "PARTICIPANT")
    }
    assertions.require(draw <= probability, "accepted invitation draw exceeds its predicted probability")
    assertions.require(joint.authority is JointActionAuthority.CENTRAL_RESOLVER, "accepted joint is not central")
    assertions.require(len(participant_ids) == 2, "accepted JointAction does not have two participants")
    assertions.require(target_agent_id in participant_ids, "accepted invite target is absent from JointAction")
    assertions.require(bool(reservations), "accepted JointAction created no atomic reservations")
    assertions.require(
        {item.owner_action_id for item in reservation_records} == {joint_action_id},
        "accepted JointAction reservations do not share one authority owner",
    )
    assertions.require(
        reservation_kind_counts["PARTICIPANT"] == len(participant_ids),
        "accepted JointAction lacks participant reservations",
    )
    assertions.require(
        all(active_joint.world.agents[item].current_action_id == joint_action_id for item in participant_ids),
        "accepted JointAction does not exclusively own its participants",
    )
    joint_created_phase_count = sum(
        item["action_id"] == joint_action_id and item["phase"] == ActionPhase.CREATED.value
        for result in results
        for item in result.actions
    )
    assertions.require(
        joint_created_phase_count == 1,
        "accepted JointAction lacks one CREATED authority phase",
    )

    terminal_phase: str | None = None
    planned_end = active_joint.world.active_actions[joint_action_id].planned_end_game_minute
    assertions.require(planned_end is not None, "accepted JointAction has no bounded planned end")
    if planned_end is None:
        raise TargetedProbeFailure("accepted JointAction fixture lost its planned end")
    deadline = planned_end + 120
    for minute in range(active_joint.world.game_minute + 1, deadline + 1):
        result = engine.advance_to(minute)
        results.append(result)
        phases = [
            str(item["phase"])
            for item in result.actions
            if item["action_id"] == joint_action_id
            and item["phase"]
            in {
                ActionPhase.COMPLETED.value,
                ActionPhase.FAILED.value,
                ActionPhase.CANCELLED.value,
                ActionPhase.INTERRUPTED.value,
            }
        ]
        if phases:
            terminal_phase = phases[-1]
        if joint_action_id not in engine.export_checkpoint().world.active_actions:
            break

    final = engine.export_checkpoint()
    accepted_events = [
        event
        for event in final.events
        if event.event_type is EventType.INVITATION_ACCEPTED and event.source_action_id == invite_action_id
    ]
    assertions.require(len(accepted_events) == 1, "accepted invitation event is missing or duplicated")
    assertions.require(terminal_phase == ActionPhase.COMPLETED.value, "accepted JointAction did not complete")
    assertions.require(joint_action_id not in final.joint_actions, "completed JointAction remains active")
    assertions.require(not reservations.intersection(final.reservations), "completed JointAction leaked reservations")
    assertions.require(
        all(final.world.agents[item].current_action_id != joint_action_id for item in participant_ids),
        "completed JointAction retained participant ownership",
    )
    assertions.require(
        all(joint_action_id not in obj.occupied_slots.values() for obj in final.world.objects.values()),
        "completed JointAction retained object occupancy",
    )
    replayed = _replay_results(initial, results)
    replay_match = checkpoint_hash(replayed) == checkpoint_hash(final)
    assertions.require(replay_match, "accepted invitation replay checkpoint differs")
    assertions.require(
        replayed.authority_log_hash == final.authority_log_hash, "accepted replay authority hash differs"
    )
    assertions.require(
        replayed.transaction_chain_hash == final.transaction_chain_hash,
        "accepted replay transaction chain differs",
    )
    assert_society_invariants(final, catalog, m3_catalogs)
    assertions.require(True, "accepted invitation invariant failure")
    return assertions.count, {
        "invite_action_id": invite_action_id,
        "joint_action_id": joint_action_id,
        "invited_activity_id": invited_activity_id,
        "acceptance_probability": probability,
        "deterministic_draw": draw,
        "invitation_accepted_event_count": len(accepted_events),
        "invitation_accepted_event_ids": [event.event_id for event in accepted_events],
        "invitation_event_source_action_id": accepted_event.source_action_id,
        "joint_source_invite_action_id": joint_record.source_invite_action_id,
        "joint_authority": joint.authority.value,
        "participant_ids": participant_ids,
        "reservation_count_before": len(reservations),
        "reservation_kind_counts_before": reservation_kind_counts,
        "reservation_remnant_count": len(reservations.intersection(final.reservations)),
        "joint_created_phase_count": joint_created_phase_count,
        "joint_terminal_phase": terminal_phase,
        "before_checkpoint_hash": checkpoint_hash(initial),
        "after_checkpoint_hash": checkpoint_hash(final),
        "before_state_version": initial.world.state_version,
        "after_state_version": final.world.state_version,
        "authority_transaction_count": sum(len(result.transactions) for result in results),
        "replay_match": replay_match,
    }


def execute_authority_probe(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    probe: AuthorityProbeKey,
) -> tuple[int, dict[str, object]]:
    if probe == "knowledge_unknown_share_rejected":
        return _unknown_share_probe(catalog, m3_catalogs)
    terminal_by_probe: dict[AuthorityProbeKey, Literal["cancel", "failure", "timeout"]] = {
        "joint_action_cancel_release": "cancel",
        "joint_action_failure_release": "failure",
        "joint_action_timeout_release": "timeout",
    }
    return _joint_terminal_probe(catalog, m3_catalogs, terminal_by_probe[probe])


def generate_m3_targeted_evidence(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> dict[str, object]:
    behavior_results: dict[str, dict[str, dict[str, object]]] = {}
    for behavior_id in BehaviorId:
        results: dict[str, dict[str, object]] = {}
        for raw_probe in BEHAVIOR_PROBE_KEYS:
            probe = cast(ProbeKey, raw_probe)
            count = execute_behavior_probe(catalog, m3_catalogs, behavior_id, probe)
            results[probe] = _pass_record(_behavior_test_id(behavior_id, probe), count)
        behavior_results[behavior_id.value] = results

    authority_results: dict[str, dict[str, object]] = {}
    observations: dict[str, dict[str, object]] = {}
    for raw_probe in AUTHORITY_PROBE_KEYS:
        authority_probe = cast(AuthorityProbeKey, raw_probe)
        count, observation = execute_authority_probe(catalog, m3_catalogs, authority_probe)
        authority_results[authority_probe] = _pass_record(_authority_test_id(authority_probe), count)
        observations[authority_probe] = observation
    acceptance_count, acceptance_observation = execute_invitation_acceptance_probe(catalog, m3_catalogs)
    acceptance_result = _pass_record(
        "python/tests/society/test_m3_targeted_evidence.py::test_sim_targeted_invitation_acceptance_probe",
        acceptance_count,
    )
    observations[INVITATION_ACCEPTANCE_PROBE_KEY] = acceptance_observation
    return {
        "behavior_probe_results": behavior_results,
        "authority_probe_results": authority_results,
        "sim_authority_probe_results": {INVITATION_ACCEPTANCE_PROBE_KEY: acceptance_result},
        "authority_probe_observations": observations,
        "invited_activity_ids": [item.value for item in INVITED_ACTIVITY_ALLOWLIST],
    }
