"""Event and participation models."""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.knowledge.enums import EventType, ExtractionSource, ParticipantRole, sa_enum


class HistoricalEvent(Base):
    """A situated historical happening, not a static triple."""

    __tablename__ = "knowledge_events"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(sa_enum(EventType), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    summary = Column(Text, nullable=True)
    start_date = Column(String(64), nullable=True)
    end_date = Column(String(64), nullable=True)
    date_uncertainty_note = Column(Text, nullable=True)
    place_entity_id = Column(
        Integer,
        ForeignKey("knowledge_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    extraction_source = Column(sa_enum(ExtractionSource), nullable=False, default=ExtractionSource.HUMAN)
    model_name = Column(String(128), nullable=True)
    model_version = Column(String(64), nullable=True)
    created_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    participants = relationship(
        "EventParticipant",
        back_populates="event",
        cascade="all, delete-orphan",
    )
    mentions = relationship(
        "app.knowledge.models.event.EventMention",
        back_populates="event",
        cascade="all, delete-orphan",
    )


class EventMention(Base):
    """A trigger span that refers to an event in text."""

    __tablename__ = "knowledge_event_mentions"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("knowledge_events.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_span_id = Column(
        Integer,
        ForeignKey("knowledge_evidence_spans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    trigger_text = Column(String(512), nullable=True)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    event = relationship("HistoricalEvent", back_populates="mentions")
    evidence_span = relationship("app.knowledge.models.evidence.EvidenceSpan")


class EventParticipant(Base):
    """An entity's role in an event, with optional validity interval."""

    __tablename__ = "knowledge_event_participants"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("knowledge_events.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(Integer, ForeignKey("knowledge_entities.id", ondelete="RESTRICT"), nullable=False, index=True)
    role = Column(sa_enum(ParticipantRole), nullable=False)
    valid_from = Column(String(64), nullable=True)
    valid_to = Column(String(64), nullable=True)
    evidence_span_id = Column(
        Integer,
        ForeignKey("knowledge_evidence_spans.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    event = relationship("HistoricalEvent", back_populates="participants")
    entity = relationship("CanonicalEntity")
