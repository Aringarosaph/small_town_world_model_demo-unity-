"""Versioned M3 semantic-instance and deterministic dialogue catalogs."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt, PositiveInt, model_validator

from town_core.domain.base import ContractModel
from town_core.domain.enums import AnimationSemantic, BehaviorId, CapabilityTag, ObjectType
from town_core.domain.identifiers import AgentId, LocationId, ObjectId

type DialogueOutcome = Literal["DEFAULT", "ACCEPTED", "REJECTED"]


class SemanticInstance(ContractModel):
    object_id: ObjectId
    object_type: ObjectType
    location_id: LocationId
    capability_tags: Annotated[list[CapabilityTag], Field(min_length=1)]
    slot_count: PositiveInt
    supported_animation_semantics: Annotated[list[AnimationSemantic], Field(min_length=1)]
    assigned_agent_id: AgentId | None = None

    @model_validator(mode="after")
    def validate_unique_values(self) -> SemanticInstance:
        if len(self.capability_tags) != len(set(self.capability_tags)):
            raise ValueError("semantic instance capability tags must be unique")
        if len(self.supported_animation_semantics) != len(set(self.supported_animation_semantics)):
            raise ValueError("semantic instance animation semantics must be unique")
        return self


class FullTownSemanticManifest(ContractModel):
    schema_id: Literal["stwm.catalog.m3-semantic-instances/v1"] = Field(alias="schema")
    profile: Literal["M3_FULL"]
    catalog_protocol_version: Literal["0.1.0"]
    location_ids: Annotated[list[LocationId], Field(min_length=8, max_length=8)]
    npc_view_ids: Annotated[list[AgentId], Field(min_length=10, max_length=10)]
    objects: Annotated[list[SemanticInstance], Field(min_length=1)]
    required_animation_semantics: Annotated[list[AnimationSemantic], Field(min_length=1)]
    required_prop_semantics: Annotated[list[str], Field(min_length=4, max_length=4)]
    facing_behavior_ids: Annotated[list[BehaviorId], Field(min_length=8, max_length=8)]
    require_entrance_slot_reachability: Literal[True]

    @model_validator(mode="after")
    def validate_stable_identity(self) -> FullTownSemanticManifest:
        for label, values in (
            ("location IDs", self.location_ids),
            ("NPC view IDs", self.npc_view_ids),
            ("object IDs", [item.object_id for item in self.objects]),
            ("animation semantics", self.required_animation_semantics),
            ("prop semantics", self.required_prop_semantics),
            ("facing behaviors", self.facing_behavior_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"semantic manifest {label} must be unique")
        return self


class BackgroundDialogueTemplate(ContractModel):
    template_id: Annotated[str, Field(pattern=r"^m3_[a-z0-9_]+_(default|accepted|rejected)$")]
    behavior_id: BehaviorId
    outcome: DialogueOutcome
    lines: Annotated[list[Annotated[str, Field(min_length=1, max_length=240)]], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_lines(self) -> BackgroundDialogueTemplate:
        if len(self.lines) != len(set(self.lines)):
            raise ValueError("background dialogue lines must be unique within a template")
        return self


class BackgroundDialogueCatalog(ContractModel):
    schema_id: Literal["stwm.catalog.m3-background-dialogue/v1"] = Field(alias="schema")
    provider: Literal["DETERMINISTIC_TEMPLATE"]
    selection_seed_salt: NonNegativeInt
    fallback_line: Annotated[str, Field(min_length=1, max_length=240)]
    templates: Annotated[list[BackgroundDialogueTemplate], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_template_ids(self) -> BackgroundDialogueCatalog:
        ids = [item.template_id for item in self.templates]
        keys = [(item.behavior_id, item.outcome) for item in self.templates]
        if len(ids) != len(set(ids)):
            raise ValueError("background dialogue template IDs must be unique")
        if len(keys) != len(set(keys)):
            raise ValueError("background dialogue behavior/outcome keys must be unique")
        return self


class M3Catalogs(ContractModel):
    semantic_instances: FullTownSemanticManifest
    background_dialogue: BackgroundDialogueCatalog
