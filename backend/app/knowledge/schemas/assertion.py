"""Assertion and review schemas."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.knowledge.enums import (
    AssertionSourceType,
    Certainty,
    EvidenceStance,
    PredicateType,
    ReviewDecisionType,
)
from app.knowledge.schemas.common import ORMModel


class AssertionEvidenceCreate(BaseModel):
    """Attach evidence to an assertion."""

    evidence_span_id: int
    stance: EvidenceStance = EvidenceStance.SUPPORTS


class AssertionCreate(BaseModel):
    """Create a sourced historical assertion."""

    subject_entity_id: int
    predicate: PredicateType
    object_entity_id: Optional[int] = None
    object_literal: Optional[str] = None
    original_predicate_text: Optional[str] = None
    source_type: AssertionSourceType
    certainty: Certainty = Certainty.UNCERTAIN
    is_inferred: bool = False
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    created_by: Optional[str] = None
    evidence: List[AssertionEvidenceCreate] = Field(default_factory=list)


class AssertionEvidenceResponse(ORMModel):
    """Stored assertion-evidence link."""

    id: int
    assertion_id: int
    evidence_span_id: int
    stance: EvidenceStance
    created_at: datetime


class AssertionResponse(ORMModel):
    """Stored assertion."""

    id: int
    subject_entity_id: int
    predicate: PredicateType
    object_entity_id: Optional[int] = None
    object_literal: Optional[str] = None
    original_predicate_text: Optional[str] = None
    source_type: AssertionSourceType
    certainty: Certainty
    is_inferred: bool
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    evidence_links: List[AssertionEvidenceResponse] = []


class ReviewDecisionCreate(BaseModel):
    """Record a human review on any knowledge object."""

    target_type: str = Field(..., min_length=1, max_length=64)
    target_id: int
    decision: ReviewDecisionType
    rationale: Optional[str] = None
    reviewer: Optional[str] = None


class ReviewDecisionResponse(ORMModel):
    """Stored review."""

    id: int
    target_type: str
    target_id: int
    decision: ReviewDecisionType
    rationale: Optional[str] = None
    reviewer: Optional[str] = None
    created_at: datetime


class WorkbenchOverviewResponse(BaseModel):
    """Counts for the knowledge workbench home."""

    corpora: int
    corpus_documents: int
    evidence_spans: int
    mentions: int
    unresolved_mentions: int
    entities: int
    events: int
    assertions: int
