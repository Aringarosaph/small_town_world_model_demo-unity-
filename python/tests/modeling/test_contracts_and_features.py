from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from town_core.catalogs import load_catalog, load_m3_catalogs
from town_core.domain.decision_models import OutcomePrediction
from town_core.domain.enums import BehaviorId, EventType, RelationshipDirection
from town_core.domain.state_models import KnowledgeRecord, MoodDelta, NeedDelta, WorldEvent, WorldState
from town_core.modeling.contracts import TrainingExample
from town_core.modeling.features import CandidateFeatureEncoder, split_for_scenario_group
from town_core.modeling.postprocess import CatalogOutcomePostprocessor
from town_core.modeling.providers import HeuristicOutcomeModel, RecordedOutcomeModel
from town_core.modeling.schema_artifacts import VERSION_DOCUMENT, build_schemas
from town_core.society.engine import SocietyEngine
from town_core.society.initialization import build_initial_society_checkpoint
from town_core.society.models import ConversationRecord

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONFIG_ROOT = REPOSITORY_ROOT / "config" / "v0"


class _FeatureCapture:
    def __init__(self, encoder: CandidateFeatureEncoder, *, seed: int) -> None:
        self.encoder = encoder
        self.seed = seed
        self.examples: list[TrainingExample] = []

    def record_decision(
        self,
        *,
        source_state: WorldState,
        decision: Mapping[str, object],
        events: Mapping[str, WorldEvent],
        knowledge_records: Mapping[str, KnowledgeRecord],
        conversations: Mapping[str, ConversationRecord],
        recent_behavior: BehaviorId | None,
    ) -> None:
        self.examples.extend(
            self.encoder.encode_decision(
                seed=self.seed,
                state=source_state,
                decision=decision,
                events=events,
                knowledge_records=knowledge_records,
                conversations=conversations,
                recent_behavior=recent_behavior,
            )
        )


def test_committed_m4_schemas_match_generator() -> None:
    committed_version = json.loads((REPOSITORY_ROOT / "model" / "version.json").read_text(encoding="utf-8"))
    assert committed_version == VERSION_DOCUMENT
    for name, schema in build_schemas().items():
        committed = json.loads(
            (REPOSITORY_ROOT / "model" / "jsonschema" / f"{name}.schema.json").read_text(encoding="utf-8")
        )
        assert committed == schema


def test_feature_capture_is_deterministic_and_authority_neutral() -> None:
    catalog = load_catalog(CONFIG_ROOT)
    m3_catalogs = load_m3_catalogs(CONFIG_ROOT, catalog=catalog)
    seed = 12345
    source_commit = "a" * 40
    initial = build_initial_society_checkpoint(catalog, m3_catalogs, seed=seed)
    capture = _FeatureCapture(CandidateFeatureEncoder(catalog, m3_catalogs, source_commit=source_commit), seed=seed)
    observed = SocietyEngine(catalog, m3_catalogs, initial, decision_observer=capture)
    baseline = SocietyEngine(catalog, m3_catalogs, initial)

    target = initial.world.game_minute + 240
    observed.advance_to(target)
    baseline.advance_to(target)

    assert capture.examples
    assert observed.export_checkpoint() == baseline.export_checkpoint()
    assert all(item.feature.source_commit == source_commit for item in capture.examples)
    assert all(item.feature.decision_group_id.startswith("m3_seed_12345_day_") for item in capture.examples)
    assert len({item.feature.row_id for item in capture.examples}) == len(capture.examples)
    assert all(
        item.feature.split == split_for_scenario_group(item.feature.scenario_group_id) for item in capture.examples
    )

    adapter = HeuristicOutcomeModel(catalog)
    reproduced = adapter.predict_batch([item.feature for item in capture.examples])
    for item, prediction in zip(capture.examples, reproduced, strict=True):
        assert (
            prediction.model_copy(update={"prediction_id": item.label.prediction.prediction_id})
            == item.label.prediction
        )

    recorded = RecordedOutcomeModel({item.feature.row_id: item.label.prediction for item in capture.examples})
    assert [item.candidate_id for item in recorded.predict_batch([item.feature for item in capture.examples])] == [
        item.feature.candidate_id for item in capture.examples
    ]


def test_catalog_postprocessor_masks_illegal_idle_outputs() -> None:
    catalog = load_catalog(CONFIG_ROOT)
    m3_catalogs = load_m3_catalogs(CONFIG_ROOT, catalog=catalog)
    seed = 12345
    initial = build_initial_society_checkpoint(catalog, m3_catalogs, seed=seed)
    capture = _FeatureCapture(CandidateFeatureEncoder(catalog, m3_catalogs, source_commit="b" * 40), seed=seed)
    engine = SocietyEngine(catalog, m3_catalogs, initial, decision_observer=capture)
    engine.advance_to(initial.world.game_minute + 1)
    idle = next(item for item in capture.examples if item.feature.raw_candidate.behavior_id.value == "idle")
    unsafe = OutcomePrediction(
        prediction_id=idle.label.prediction.prediction_id,
        candidate_id=idle.feature.candidate_id,
        need_delta_preview=NeedDelta(hunger=0.9, energy=0.9, hygiene=0.9, fun=0.9, social=0.9),
        actor_mood_delta=MoodDelta(valence=0.9, stress=0.9),
        target_mood_delta=None,
        relationship_direction=RelationshipDirection.TARGET_TO_ACTOR,
        relationship_delta_target_to_actor=None,
        acceptance_probability=None,
        event_probabilities={EventType.MEAL_CONSUMED: 1.0},
    )

    safe, violations = CatalogOutcomePostprocessor(catalog).process(idle.feature, unsafe)

    assert safe.need_delta_preview == NeedDelta(hunger=0.0, energy=0.0, hygiene=0.0, fun=0.0, social=0.0)
    assert safe.actor_mood_delta == MoodDelta(valence=0.0, stress=0.0)
    assert safe.event_probabilities == {}
    assert violations == {"masked_actor_mood": 2, "masked_need": 5, "unknown_or_masked_event": 1}
