"""Entity mention model for text-level entity references."""
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum, JSON, Float
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.evidence_span import EvidenceSpan
    from app.models.identity_decision import IdentityDecision


class MentionStatus(str, enum.Enum):
    """Entity mention status."""
    PENDING = "pending"
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class EntityMention(Base):
    """
    Entity mention in text with original form and honorifics.

    Links to evidence spans for anchoring to source text.
    """

    __tablename__ = "entity_mentions"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    evidence_span_id = Column(Integer, ForeignKey("evidence_spans.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True)

    # Original text form
    original_form = Column(String(500), nullable=False, index=True, comment="原文形式")
    normalized_form = Column(String(500), nullable=True, comment="规范化形式")

    # Honorifics and titles
    honorific = Column(String(100), nullable=True, comment="敬称")
    title = Column(String(200), nullable=True, comment="职衔")
    title_abbreviation = Column(String(100), nullable=True, comment="职衔缩写")

    # Identity candidates
    candidate_entity_ids = Column(JSON, nullable=True, comment="候选实体ID列表")
    candidate_notes = Column(Text, nullable=True, comment="身份候选说明")

    # Status and confidence
    status = Column(Enum(MentionStatus), default=MentionStatus.PENDING, comment="状态")
    confidence = Column(Float, nullable=True, comment="置信度")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    evidence_span = relationship("app.models.evidence_span.EvidenceSpan", back_populates="entity_mentions")
    entity = relationship("Entity", back_populates="mentions")
    identity_decisions = relationship("app.models.identity_decision.IdentityDecision", back_populates="mention", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<EntityMention(id={self.id}, form={self.original_form}, entity_id={self.entity_id})>"
