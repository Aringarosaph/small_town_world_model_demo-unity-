"""Append-only, deterministically ordered M1 event ledger."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import EventType
from town_core.domain.state_models import EventPayloadValue, WorldEvent


class EventLedger:
    """Own committed events and reject mutation-like append sequences."""

    def __init__(self, catalog: CatalogBundle, events: Sequence[WorldEvent] = ()) -> None:
        self._event_config = {item.event_type: item for item in catalog.events.event_types}
        self._events: list[WorldEvent] = []
        self.commit(events)

    @property
    def events(self) -> tuple[WorldEvent, ...]:
        return tuple(self._events)

    def create(
        self,
        event_type: EventType,
        *,
        staged_offset: int,
        game_minute: int,
        location_id: str,
        actor_ids: list[str],
        affected_agent_ids: list[str],
        witness_agent_ids: list[str],
        source_action_id: str | None,
        payload: dict[str, EventPayloadValue],
    ) -> WorldEvent:
        config = self._event_config[event_type]
        sequence = len(self._events) + staged_offset + 1
        return WorldEvent(
            event_id=f"event_{sequence:08d}",
            event_type=event_type,
            game_minute=game_minute,
            location_id=location_id,
            actor_ids=sorted(set(actor_ids)),
            affected_agent_ids=sorted(set(affected_agent_ids)),
            witness_agent_ids=sorted(set(witness_agent_ids)),
            source_action_id=source_action_id,
            importance=config.default_importance,
            witness_scope=config.witness_scope,
            payload=payload,
            supersedes_event_id=None,
        )

    def commit(self, events: Iterable[WorldEvent]) -> None:
        for event in events:
            expected_id = f"event_{len(self._events) + 1:08d}"
            if event.event_id != expected_id:
                raise ValueError(f"event order is unstable: expected {expected_id}, got {event.event_id}")
            if self._events and event.game_minute < self._events[-1].game_minute:
                raise ValueError("event game minutes must be monotonic")
            self._events.append(event)
