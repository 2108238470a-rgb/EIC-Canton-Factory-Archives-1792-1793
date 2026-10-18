"""Enumerations for the historical knowledge module."""
from enum import Enum

from sqlalchemy import Enum as SAEnum


class TextVersion(str, Enum):
    """Immutable text layer copied into an evidence span."""

    OCR_RAW = "ocr_raw"
    OCR_AUTO_CORRECTED = "ocr_auto_corrected"
    OCR_HUMAN_CORRECTED = "ocr_human_corrected"
    MODERN_ENGLISH = "modern_english"
    TRANSLATION_ZH = "translation_zh"


class EntityType(str, Enum):
    """Canonical entity kind."""

    PERSON = "person"
    ORGANIZATION = "organization"
    PLACE = "place"
    ROLE = "role"
    OTHER = "other"


class MentionType(str, Enum):
    """Surface mention kind in running text."""

    PERSON = "person"
    ORGANIZATION = "organization"
    PLACE = "place"
    ROLE = "role"
    OTHER = "other"


class NameType(str, Enum):
    """How a name string relates to a canonical entity."""

    CANONICAL = "canonical"
    ALIAS = "alias"
    ORIGINAL_SPELLING = "original_spelling"
    TITLE = "title"


class IdentityDecisionType(str, Enum):
    """Decision that links or unlinks a mention and an entity."""

    LINK = "link"
    UNLINK = "unlink"
    UNCERTAIN = "uncertain"


class DisambiguationStatus(str, Enum):
    """Researcher-facing status of a canonical entity."""

    UNRESOLVED = "unresolved"
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    SPLIT_REQUIRED = "split_required"


class ExtractionSource(str, Enum):
    """Provenance of an automatic or manual record."""

    HUMAN = "human"
    MODEL = "model"
    RULE = "rule"


class EventType(str, Enum):
    """Coarse historical event classes for Canton consultations."""

    CONSULTATION = "consultation"
    REQUEST = "request"
    INSTRUCTION = "instruction"
    REPORT = "report"
    APPOINTMENT = "appointment"
    VOYAGE = "voyage"
    TRADE = "trade"
    CONFLICT = "conflict"
    CORRESPONDENCE = "correspondence"
    RESOLUTION = "resolution"
    OTHER = "other"


class ParticipantRole(str, Enum):
    """Role of an entity in an event. Mention is not the same as agency."""

    SPEAKER = "speaker"
    REPORTER = "reporter"
    ADDRESSEE = "addressee"
    DECISION_MAKER = "decision_maker"
    DISCUSSED = "discussed"
    INTERMEDIARY = "intermediary"
    ACTOR = "actor"
    OTHER = "other"


class PredicateType(str, Enum):
    """Normalized relation predicates. Original wording is stored separately."""

    APPOINTED_TO_ROLE = "appointed_to_role"
    HELD_ROLE = "held_role"
    COMMUNICATION_PARTICIPATION = "communication_participation"
    DIRECTED_ACTION = "directed_action"
    EVENT_PARTICIPATION = "event_participation"
    REPRESENTED_ORG = "represented_org"
    OTHER = "other"


class AssertionSourceType(str, Enum):
    """Whether an assertion is evidenced, inferred, extracted, or human."""

    DIRECT_EVIDENCE = "direct_evidence"
    RULE_INFERENCE = "rule_inference"
    MODEL_EXTRACTION = "model_extraction"
    HUMAN = "human"


class EvidenceStance(str, Enum):
    """How an evidence span relates to an assertion."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    MENTIONS_ONLY = "mentions_only"


class ReviewDecisionType(str, Enum):
    """Human review outcome for a knowledge object."""

    CONFIRM = "confirm"
    REJECT = "reject"
    NEEDS_VERIFICATION = "needs_verification"


class Certainty(str, Enum):
    """Explicit uncertainty. Do not coerce into a single date or fact."""

    CERTAIN = "certain"
    PROBABLE = "probable"
    POSSIBLE = "possible"
    UNCERTAIN = "uncertain"


class RoleTenureType(str, Enum):
    """How a person occupied an office."""

    SUBSTANTIVE = "substantive"
    ACTING = "acting"
    DEPUTY = "deputy"
    NOMINATED = "nominated"


def sa_enum(enum_cls: type[Enum], length: int = 64) -> SAEnum:
    """Return a portable SQLAlchemy enum column type.

    Args:
        enum_cls: Python enum class whose `.value` strings are persisted.
        length: VARCHAR length when `native_enum` is disabled.

    Returns:
        SQLAlchemy Enum type that stores values, not member names.
    """
    return SAEnum(
        enum_cls,
        values_callable=lambda members: [item.value for item in members],
        native_enum=False,
        validate_strings=True,
        length=length,
    )
