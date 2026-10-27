"""Historical assertions, evidence links, and review decisions."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.knowledge.enums import (
    AssertionSourceType,
    Certainty,
    EvidenceStance,
    PredicateType,
    ReviewDecisionType,
    sa_enum,
)


class Assertion(Base):
    """A sourced historical claim. Contradictory claims may coexist."""

    __tablename__ = "knowledge_assertions"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    subject_entity_id = Column(
        Integer,
        ForeignKey("knowledge_entities.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    predicate = Column(sa_enum(PredicateType), nullable=False, index=True)
    object_entity_id = Column(
        Integer,
        ForeignKey("knowledge_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    object_literal = Column(Text, nullable=True)
    original_predicate_text = Column(Text, nullable=True)
    source_type = Column(sa_enum(AssertionSourceType), nullable=False)
    certainty = Column(sa_enum(Certainty), nullable=False, default=Certainty.UNCERTAIN)
    is_inferred = Column(Boolean, nullable=False, default=False)
    model_name = Column(String(128), nullable=True)
    model_version = Column(String(64), nullable=True)
    created_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    evidence_links = relationship(
        "app.knowledge.models.assertion.AssertionEvidence",
        back_populates="assertion",
        cascade="all, delete-orphan",
    )


class AssertionEvidence(Base):
    """Link from an assertion to an evidence span with a stance."""

    __tablename__ = "knowledge_assertion_evidence"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    assertion_id = Column(
        Integer,
        ForeignKey("knowledge_assertions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_span_id = Column(
        Integer,
        ForeignKey("knowledge_evidence_spans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    stance = Column(sa_enum(EvidenceStance), nullable=False, default=EvidenceStance.SUPPORTS)
    created_at = Column(DateTime, default=datetime.utcnow)

    assertion = relationship("app.knowledge.models.assertion.Assertion", back_populates="evidence_links")
    evidence_span = relationship("app.knowledge.models.evidence.EvidenceSpan")


class ReviewDecision(Base):
    """Human confirmation, rejection, or hold for any knowledge object."""

    __tablename__ = "knowledge_review_decisions"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    target_type = Column(String(64), nullable=False, index=True)
    target_id = Column(Integer, nullable=False, index=True)
    decision = Column(sa_enum(ReviewDecisionType), nullable=False)
    rationale = Column(Text, nullable=True)
    reviewer = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
