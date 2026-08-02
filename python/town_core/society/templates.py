"""SIM selection/permission adapter for CONTRACTS-owned M3 dialogue."""

from __future__ import annotations

from town_core.catalogs import select_background_dialogue_line
from town_core.domain.enums import BehaviorId
from town_core.domain.m3_catalog_models import BackgroundDialogueCatalog, DialogueOutcome
from town_core.society.models import DialogueLineRecord


class BackgroundTemplateProvider:
    """Render bounded presentation text without authority side effects."""

    def __init__(self, catalog: BackgroundDialogueCatalog) -> None:
        self.catalog = catalog
        self.version = catalog.schema_id

    def render(
        self,
        *,
        line_id: str,
        game_minute: int,
        world_seed: int,
        action_id: str,
        behavior_id: BehaviorId,
        accepted: bool,
        speaker_agent_id: str,
        listener_ids: list[str],
        referenced_event_id: str | None,
        speaker_known_event_ids: list[str],
    ) -> DialogueLineRecord:
        if referenced_event_id is not None and referenced_event_id not in speaker_known_event_ids:
            raise ValueError("background dialogue cannot reference an event unknown to the speaker")
        outcome: DialogueOutcome = (
            "DEFAULT"
            if behavior_id in {BehaviorId.SHARE_EVENT, BehaviorId.END_CONVERSATION}
            else ("ACCEPTED" if accepted else "REJECTED")
        )
        deterministic_key = "|".join(
            (
                str(world_seed),
                action_id,
                speaker_agent_id,
                ",".join(sorted(listener_ids)),
                referenced_event_id or "",
            )
        )
        text = select_background_dialogue_line(
            self.catalog,
            behavior_id=behavior_id,
            outcome=outcome,
            deterministic_key=deterministic_key,
        )
        template = next(
            (item for item in self.catalog.templates if item.behavior_id is behavior_id and item.outcome == outcome),
            None,
        )
        return DialogueLineRecord(
            line_id=line_id,
            game_minute=game_minute,
            speaker_agent_id=speaker_agent_id,
            listener_ids=sorted(listener_ids),
            template_id=(template.template_id if template is not None else f"{self.version}:fallback"),
            text=text,
            referenced_event_ids=[] if referenced_event_id is None else [referenced_event_id],
        )
