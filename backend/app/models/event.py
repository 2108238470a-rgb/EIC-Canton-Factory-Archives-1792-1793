"""Event model for cross-source aligned events."""
import enum
from datetime import datetime, date
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, String, DateTime, Text, Date, Enum, Index
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.event_mention import EventMention
    from app.models.participation import Participation
    from app.models.event_relation import EventRelation


class EventStatus(str, enum.Enum):
    """Event confirmation status."""
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"


class Event(Base):
    """
    Historical event aligned across multiple sources.

    Represents a unique occurrence with participants and relationships.
    """

    __tablename__ = "events"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)

    # Event identification
    event_type = Column(String(100), nullable=False, index=True, comment="事件类型")
    title = Column(String(500), nullable=False, comment="事件标题")
    summary = Column(Text, nullable=True, comment="事件摘要")

    # Date information
    date_start = Column(Date, nullable=True, index=True, comment="起始日期")
    date_end = Column(Date, nullable=True, comment="结束日期")
    date_precision = Column(String(50), nullable=True, comment="日期精度")

    # Location
    location_text = Column(String(500), nullable=True, comment="地点文本")
    location_entity_id = Column(Integer, nullable=True, comment="规范地点ID")

    # Status
    status = Column(Enum(EventStatus), default=EventStatus.CANDIDATE, comment="确认状态")
    confidence = Column(String(50), nullable=True, comment="置信度")

    # Description
    description = Column(Text, nullable=True, comment="详细描述")
    notes = Column(Text, nullable=True, comment="备注")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    mentions = relationship("app.models.event_mention.EventMention", back_populates="event")
    participations = relationship("Participation", back_populates="event", cascade="all, delete-orphan")
    relations_as_source = relationship("EventRelation", foreign_keys="EventRelation.source_event_id", back_populates="source_event")
    relations_as_target = relationship("EventRelation", foreign_keys="EventRelation.target_event_id", back_populates="target_event")

    # Indexes
    __table_args__ = (
        Index('ix_events_type_date', 'event_type', 'date_start'),
    )

    def __repr__(self) -> str:
        return f"<Event(id={self.id}, type={self.event_type}, title={self.title})>"
