"""Event relation model for inter-event relationships."""
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.event import Event


class EventRelationType(str, enum.Enum):
    """Type of relationship between events."""
    REPLY_TO = "reply_to"
    FOLLOWS = "follows"
    SAME_EVENT_CANDIDATE = "same_event_candidate"
    CAUSES = "causes"
    PART_OF = "part_of"
    RELATED_TO = "related_to"


class EventRelation(Base):
    """
    Relationship between two events.

    Supports reply chains, causal links, and event merging candidates.
    """

    __tablename__ = "event_relations"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    source_event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    target_event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)

    # Relationship type
    relation_type = Column(Enum(EventRelationType), nullable=False, index=True, comment="关系类型")
    description = Column(Text, nullable=True, comment="关系描述")

    # Confidence
    confidence = Column(String(50), nullable=True, comment="置信度")
    notes = Column(Text, nullable=True, comment="备注")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    source_event = relationship("Event", foreign_keys=[source_event_id], back_populates="relations_as_source")
    target_event = relationship("Event", foreign_keys=[target_event_id], back_populates="relations_as_target")

    def __repr__(self) -> str:
        return f"<EventRelation(id={self.id}, type={self.relation_type}, {self.source_event_id}->{self.target_event_id})>"
