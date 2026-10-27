"""Review decision model for human review tracking."""
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    pass


class ReviewTargetType(str, enum.Enum):
    """Type of target being reviewed."""
    ENTITY_MENTION = "entity_mention"
    IDENTITY_DECISION = "identity_decision"
    EVENT_MENTION = "event_mention"
    EVENT = "event"
    ASSERTION = "assertion"
    SOURCE_UNIT = "source_unit"
    TEXT_REVISION = "text_revision"


class ReviewDecisionType(str, enum.Enum):
    """Review decision outcome."""
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"
    FLAGGED = "flagged"


class ReviewDecision(Base):
    """
    Review decision for any reviewable entity.

    Tracks human review with reasoning and versioning.
    """

    __tablename__ = "review_decisions"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)

    # Target information
    target_type = Column(Enum(ReviewTargetType), nullable=False, index=True, comment="目标类型")
    target_id = Column(Integer, nullable=False, index=True, comment="目标ID")

    # Decision
    decision = Column(Enum(ReviewDecisionType), nullable=False, comment="决策")
    reason = Column(Text, nullable=True, comment="理由")

    # Reviewer information
    reviewer = Column(String(255), nullable=False, comment="操作者")
    reviewer_role = Column(String(100), nullable=True, comment="操作者角色")

    # Versioning
    previous_decision_id = Column(Integer, ForeignKey("review_decisions.id", ondelete="SET NULL"), nullable=True)

    # Additional notes
    notes = Column(Text, nullable=True, comment="备注")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    previous_decision = relationship("app.models.review_decision.ReviewDecision", remote_side=[id], backref="next_decisions")

    def __repr__(self) -> str:
        return f"<ReviewDecision(id={self.id}, target={self.target_type}:{self.target_id}, decision={self.decision})>"
