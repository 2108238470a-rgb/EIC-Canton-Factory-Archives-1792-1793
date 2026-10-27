"""Assertion evidence model linking assertions to evidence spans."""
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.assertion import Assertion
    from app.models.evidence_span import EvidenceSpan


class EvidenceRelation(str, enum.Enum):
    """How evidence relates to assertion."""
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    MENTIONS = "mentions"
    UNCERTAIN = "uncertain"


class AssertionEvidence(Base):
    """
    Links assertions to evidence spans with relation type.

    Multiple evidence spans can support or contradict an assertion.
    """

    __tablename__ = "assertion_evidences"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    assertion_id = Column(Integer, ForeignKey("assertions.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_span_id = Column(Integer, ForeignKey("evidence_spans.id", ondelete="CASCADE"), nullable=False, index=True)

    # Relation type
    relation = Column(Enum(EvidenceRelation), nullable=False, default=EvidenceRelation.SUPPORTS, comment="关系类型")

    # Notes
    notes = Column(Text, nullable=True, comment="备注")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    assertion = relationship("app.models.assertion.Assertion", back_populates="evidences")
    evidence_span = relationship("app.models.evidence_span.EvidenceSpan", back_populates="assertion_evidences")

    def __repr__(self) -> str:
        return f"<AssertionEvidence(id={self.id}, assertion_id={self.assertion_id}, relation={self.relation})>"
