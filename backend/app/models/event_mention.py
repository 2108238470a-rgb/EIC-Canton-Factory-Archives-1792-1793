"""Event mention model for source-level event narratives."""
import enum
from datetime import datetime, date
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Date, Enum
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.source_unit import SourceUnit
    from app.models.event import Event


class EventMentionStatus(str, enum.Enum):
    """Event mention status."""
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    MERGED = "merged"
    REJECTED = "rejected"


class EventMention(Base):
    """
    Event mention as narrated in a specific source.

    Multiple mentions may refer to the same historical event.
    """

    __tablename__ = "event_mentions"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    source_unit_id = Column(Integer, ForeignKey("source_units.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True)

    # Event description
    event_type = Column(String(100), nullable=True, index=True, comment="事件类型")
    summary = Column(Text, nullable=False, comment="事件摘要")

    # Date information
    mentioned_date_text = Column(String(255), nullable=True, comment="提及的日期文本")
    mentioned_date_start = Column(Date, nullable=True, comment="提及的起始日期")
    mentioned_date_end = Column(Date, nullable=True, comment="提及的结束日期")
    date_precision = Column(String(50), nullable=True, comment="日期精度")

    # Location
    location_text = Column(String(500), nullable=True, comment="地点文本")

    # Status
    status = Column(Enum(EventMentionStatus), default=EventMentionStatus.CANDIDATE, comment="状态")
    notes = Column(Text, nullable=True, comment="备注")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    source_unit = relationship("SourceUnit", back_populates="event_mentions")
    event = relationship("Event", back_populates="mentions")

    def __repr__(self) -> str:
        return f"<EventMention(id={self.id}, type={self.event_type}, summary={self.summary[:50]})>"
