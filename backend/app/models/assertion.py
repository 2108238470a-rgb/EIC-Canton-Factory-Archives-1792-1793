"""Assertion model for structured claims."""
import enum
from datetime import datetime, date
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Date, Enum, JSON
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.assertion_evidence import AssertionEvidence


class AssertionStatus(str, enum.Enum):
    """Assertion verification status."""
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    REJECTED = "rejected"


class SourceType(str, enum.Enum):
    """Source of assertion."""
    EXTRACTED = "extracted"
    MANUAL = "manual"
    EXTERNAL = "external"
    INFERRED = "inferred"


class Assertion(Base):
    """
    Structured assertion about entities and events.

    Subject-predicate-object triples with temporal validity and evidence.
    """

    __tablename__ = "assertions"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)

    # Subject-predicate-object structure
    subject_entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    predicate = Column(String(200), nullable=False, index=True, comment="谓词")

    # Object can be an entity or a literal value
    object_entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=True, index=True)
    object_literal = Column(Text, nullable=True, comment="字面值宾语")
    object_type = Column(String(50), nullable=True, comment="宾语类型")

    # Temporal validity
    valid_from = Column(Date, nullable=True, comment="有效起始时间")
    valid_to = Column(Date, nullable=True, comment="有效结束时间")
    temporal_precision = Column(String(50), nullable=True, comment="时间精度")

    # Source and status
    source_type = Column(Enum(SourceType), default=SourceType.EXTRACTED, comment="来源类型")
    status = Column(Enum(AssertionStatus), default=AssertionStatus.CANDIDATE, comment="验证状态")

    # Additional metadata
    confidence = Column(String(50), nullable=True, comment="置信度")
    extra_metadata = Column(JSON, nullable=True, comment="附加元数据")
    notes = Column(Text, nullable=True, comment="备注")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subject_entity = relationship("Entity", foreign_keys=[subject_entity_id], back_populates="assertions_as_subject")
    object_entity = relationship("Entity", foreign_keys=[object_entity_id], back_populates="assertions_as_object")
    evidences = relationship("app.models.assertion_evidence.AssertionEvidence", back_populates="assertion", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Assertion(id={self.id}, subject={self.subject_entity_id}, predicate={self.predicate})>"
