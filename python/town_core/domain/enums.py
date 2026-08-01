"""Stable V0 enum values shared by configuration and protocol DTOs."""

from __future__ import annotations

from enum import StrEnum

CONFIG_VERSION = "v0"
SCHEMA_VERSION = "v0.1"
PROTOCOL_VERSION = "0.1.0"
FEATURE_VERSION = "v0.1"


class ConfigVersion(StrEnum):
    V0 = CONFIG_VERSION


class NeedName(StrEnum):
    HUNGER = "hunger"
    ENERGY = "energy"
    HYGIENE = "hygiene"
    FUN = "fun"
    SOCIAL = "social"


class PersonalityAxis(StrEnum):
    SOCIABILITY = "sociability"
    DISCIPLINE = "discipline"
    FRUGALITY = "frugality"
    IRRITABILITY = "irritability"


class MoodAxis(StrEnum):
    VALENCE = "valence"
    STRESS = "stress"


class RelationshipAxis(StrEnum):
    FAMILIARITY = "familiarity"
    AFFINITY = "affinity"
    TRUST = "trust"
    TENSION = "tension"


class RelationshipRole(StrEnum):
    HOUSEHOLD_MEMBER = "HOUSEHOLD_MEMBER"
    COWORKER = "COWORKER"
    NEIGHBOR = "NEIGHBOR"
    ACQUAINTANCE = "ACQUAINTANCE"


class RelationshipDirection(StrEnum):
    TARGET_TO_ACTOR = "TARGET_TO_ACTOR"


class LocationType(StrEnum):
    HOME = "HOME"
    CAFE_BAR = "CAFE_BAR"
    SHOP = "SHOP"
    WORKPLACE = "WORKPLACE"
    PARK = "PARK"


class ObjectType(StrEnum):
    BED = "BED"
    FRIDGE = "FRIDGE"
    DINING_SEAT = "DINING_SEAT"
    SHOWER = "SHOWER"
    SOFA = "SOFA"
    TV = "TV"
    WORKSTATION = "WORKSTATION"
    SHOP_SHELF = "SHOP_SHELF"
    CHECKOUT_COUNTER = "CHECKOUT_COUNTER"
    CAFE_COUNTER = "CAFE_COUNTER"
    BAR_COUNTER = "BAR_COUNTER"
    PUBLIC_SEAT = "PUBLIC_SEAT"
    PARK_ROUTE = "PARK_ROUTE"
    LEISURE_SPOT = "LEISURE_SPOT"
    CONVERSATION_ANCHOR = "CONVERSATION_ANCHOR"


class CapabilityTag(StrEnum):
    SLEEP = "SLEEP"
    FOOD_SOURCE_HOME = "FOOD_SOURCE_HOME"
    SIT = "SIT"
    EAT = "EAT"
    HYGIENE = "HYGIENE"
    RELAX = "RELAX"
    WATCH_TV = "WATCH_TV"
    ENTERTAINMENT = "ENTERTAINMENT"
    WORK = "WORK"
    CAFE_MORNING = "CAFE_MORNING"
    CAFE_EVENING = "CAFE_EVENING"
    SHOP = "SHOP"
    WORKSHOP = "WORKSHOP"
    GROCERY_SOURCE = "GROCERY_SOURCE"
    PURCHASE = "PURCHASE"
    BUY_MEAL = "BUY_MEAL"
    BUY_DRINK = "BUY_DRINK"
    REST = "REST"
    WALK_ROUTE = "WALK_ROUTE"
    SOCIAL_POSITION = "SOCIAL_POSITION"


class BehaviorId(StrEnum):
    IDLE = "idle"
    SLEEP = "sleep"
    EAT_AT_HOME = "eat_at_home"
    SHOWER = "shower"
    WATCH_TV = "watch_tv"
    RELAX_AT_HOME = "relax_at_home"
    WORK_SHIFT = "work_shift"
    TAKE_BREAK = "take_break"
    BUY_GROCERIES = "buy_groceries"
    EAT_AT_CAFE = "eat_at_cafe"
    DRINK_AT_BAR = "drink_at_bar"
    WALK_IN_PARK = "walk_in_park"
    SIT_IN_PARK = "sit_in_park"
    GREET = "greet"
    CHAT = "chat"
    JOKE = "joke"
    COMPLIMENT = "compliment"
    SHARE_EVENT = "share_event"
    INVITE_JOIN = "invite_join"
    APOLOGIZE = "apologize"
    CONFRONT = "confront"
    END_CONVERSATION = "end_conversation"


class BehaviorCategory(StrEnum):
    ROUTINE = "ROUTINE"
    WORK = "WORK"
    ECONOMIC = "ECONOMIC"
    LEISURE = "LEISURE"
    SOCIAL = "SOCIAL"


class TargetKind(StrEnum):
    NONE = "NONE"
    OBJECT_BUNDLE = "OBJECT_BUNDLE"
    AGENT = "AGENT"
    CONVERSATION = "CONVERSATION"


class ReservationMode(StrEnum):
    EXCLUSIVE = "EXCLUSIVE"
    SHARED = "SHARED"
    TRANSIENT = "TRANSIENT"


class HardEffectOperation(StrEnum):
    HOUSEHOLD_MONEY_DELTA = "HOUSEHOLD_MONEY_DELTA"
    HOUSEHOLD_FOOD_DELTA = "HOUSEHOLD_FOOD_DELTA"
    RECORD_ATTENDANCE = "RECORD_ATTENDANCE"
    PAY_SHIFT_WAGE = "PAY_SHIFT_WAGE"
    ADD_KNOWLEDGE_RECORD = "ADD_KNOWLEDGE_RECORD"
    RELEASE_CONVERSATION = "RELEASE_CONVERSATION"


class EffectTiming(StrEnum):
    ON_START = "ON_START"
    ON_COMPLETE = "ON_COMPLETE"
    CONTINUOUS = "CONTINUOUS"


class AnimationSemantic(StrEnum):
    IDLE = "IDLE"
    SLEEP = "SLEEP"
    EAT = "EAT"
    SHOWER_HIDDEN = "SHOWER_HIDDEN"
    SIT = "SIT"
    WORK_DESK = "WORK_DESK"
    WORK_STANDING = "WORK_STANDING"
    WORK_WORKSHOP = "WORK_WORKSHOP"
    DRINK = "DRINK"
    WALK = "WALK"
    TALK_NEUTRAL = "TALK_NEUTRAL"
    TALK_POSITIVE = "TALK_POSITIVE"
    TALK_NEGATIVE = "TALK_NEGATIVE"
    CARRY_GROCERY = "CARRY_GROCERY"


class EventType(StrEnum):
    MEAL_CONSUMED = "MEAL_CONSUMED"
    GROCERIES_PURCHASED = "GROCERIES_PURCHASED"
    HOUSEHOLD_FOOD_LOW = "HOUSEHOLD_FOOD_LOW"
    HOUSEHOLD_MONEY_LOW = "HOUSEHOLD_MONEY_LOW"
    NEED_CRISIS = "NEED_CRISIS"
    WORK_STARTED = "WORK_STARTED"
    WORK_COMPLETED = "WORK_COMPLETED"
    WORK_LATE = "WORK_LATE"
    WORK_MISSED = "WORK_MISSED"
    COWORKER_EXTRA_LOAD = "COWORKER_EXTRA_LOAD"
    FIRST_GREETING = "FIRST_GREETING"
    POSITIVE_INTERACTION = "POSITIVE_INTERACTION"
    AWKWARD_INTERACTION = "AWKWARD_INTERACTION"
    INVITATION_ACCEPTED = "INVITATION_ACCEPTED"
    INVITATION_REJECTED = "INVITATION_REJECTED"
    APOLOGY_ACCEPTED = "APOLOGY_ACCEPTED"
    APOLOGY_REJECTED = "APOLOGY_REJECTED"
    CONFLICT_STARTED = "CONFLICT_STARTED"
    CONFLICT_ESCALATED = "CONFLICT_ESCALATED"
    CONFLICT_REDUCED = "CONFLICT_REDUCED"
    EVENT_SHARED = "EVENT_SHARED"
    CONVERSATION_STARTED = "CONVERSATION_STARTED"
    CONVERSATION_ENDED = "CONVERSATION_ENDED"


class KnowledgeAcquisitionType(StrEnum):
    DIRECT_PARTICIPANT = "DIRECT_PARTICIPANT"
    WITNESSED = "WITNESSED"
    TOLD = "TOLD"
    PLAYER_TOLD = "PLAYER_TOLD"


class JointActionAuthority(StrEnum):
    CENTRAL_RESOLVER = "CENTRAL_RESOLVER"


class PerceptionAuthority(StrEnum):
    HIGH_LEVEL_LOCATION = "HIGH_LEVEL_LOCATION"


class EventWitnessScope(StrEnum):
    PARTICIPANTS_ONLY = "PARTICIPANTS_ONLY"
    HIGH_LEVEL_LOCATION = "HIGH_LEVEL_LOCATION"


class RoutePlanningCapability(StrEnum):
    DISABLED = "DISABLED"


class ActionPhase(StrEnum):
    CREATED = "CREATED"
    RESERVING = "RESERVING"
    TRAVELING = "TRAVELING"
    ALIGNING = "ALIGNING"
    PERFORMING = "PERFORMING"
    RESOLVING = "RESOLVING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


class ProposalResult(StrEnum):
    ACCEPTED = "ACCEPTED"
    OBJECT_SLOT_CONFLICT = "OBJECT_SLOT_CONFLICT"
    TARGET_UNAVAILABLE = "TARGET_UNAVAILABLE"
    STATE_STALE = "STATE_STALE"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    LOCATION_CLOSED = "LOCATION_CLOSED"
    SOCIAL_TARGET_COMMITTED = "SOCIAL_TARGET_COMMITTED"


class MovementFailureReason(StrEnum):
    NO_PATH = "NO_PATH"
    DESTINATION_DISABLED = "DESTINATION_DISABLED"
    SLOT_BLOCKED = "SLOT_BLOCKED"
    AGENT_DISABLED = "AGENT_DISABLED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


class SpeechAct(StrEnum):
    GREET = "GREET"
    SMALL_TALK = "SMALL_TALK"
    ASK_ABOUT_AGENT = "ASK_ABOUT_AGENT"
    ASK_ABOUT_EVENT = "ASK_ABOUT_EVENT"
    COMPLIMENT = "COMPLIMENT"
    JOKE = "JOKE"
    INVITE = "INVITE"
    APOLOGIZE = "APOLOGIZE"
    ACCUSE = "ACCUSE"
    CONFRONT = "CONFRONT"
    FAREWELL = "FAREWELL"
    UNKNOWN = "UNKNOWN"


class AssetValidationSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class MessageType(StrEnum):
    CLIENT_HELLO = "client_hello"
    SERVER_HELLO = "server_hello"
    ASSET_REGISTRY = "asset_registry"
    ASSET_REGISTRY_RESULT = "asset_registry_result"
    CLIENT_READY = "client_ready"
    WORLD_SNAPSHOT = "world_snapshot"
    SIMULATION_CLOCK_UPDATED = "simulation_clock_updated"
    ACTION_STARTED = "action_started"
    ACTION_PHASE_CHANGED = "action_phase_changed"
    ACTION_CANCELLED = "action_cancelled"
    AGENT_STATE_DELTA = "agent_state_delta"
    RELATIONSHIP_DELTA = "relationship_delta"
    WORLD_EVENT_CREATED = "world_event_created"
    DIALOGUE_LINE_READY = "dialogue_line_ready"
    DEBUG_DECISION_TRACE = "debug_decision_trace"
    MOVEMENT_ARRIVED = "movement_arrived"
    MOVEMENT_FAILED = "movement_failed"
    PRESENTATION_COMPLETED = "presentation_completed"
    PLAYER_UTTERANCE = "player_utterance"
    PLAYER_END_CONVERSATION = "player_end_conversation"
    SET_TIME_SCALE_REQUEST = "set_time_scale_request"
    PAUSE_REQUEST = "pause_request"
