"""Identity decision model for entity resolution."""
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.entity_mention import EntityMention
    from app.models.entity import Entity


class DecisionStatus(str, enum.Enum):
    """Identity decision status."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class IdentityDecision(Base):
    """
    Identity decision linking a mention to an entity.

    Supports reversible entity merging and disambiguation.
    """

    __tablename__ = "identity_decisions"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    mention_id = Column(Integer, ForeignKey("entity_mentions.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)

    # Decision metadata
    basis = Column(Text, nullable=True, comment="判断依据")
    status = Column(Enum(DecisionStatus), default=DecisionStatus.PENDING, comment="决策状态")

    # Reviewer information
    reviewer = Column(String(255), nullable=True, comment="审核人")
    reviewer_type = Column(String(50), nullable=True, comment="审核人类型：human/ai")

    # Versioning for reversibility
    previous_decision_id = Column(Integer, ForeignKey("identity_decisions.id", ondelete="SET NULL"), nullable=True)

    # Notes
    notes = Column(Text, nullable=True, comment="备注")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    mention = relationship("app.models.entity_mention.EntityMention", back_populates="identity_decisions")
    entity = relationship("Entity", back_populates="identity_decisions")
    previous_decision = relationship("app.models.identity_decision.IdentityDecision", remote_side=[id], backref="next_decisions")

    def __repr__(self) -> str:
        return f"<IdentityDecision(id={self.id}, mention_id={self.mention_id}, entity_id={self.entity_id}, status={self.status})>"
