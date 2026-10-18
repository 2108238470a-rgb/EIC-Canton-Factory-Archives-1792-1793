"""Event schemas."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.knowledge.enums import EventType, ExtractionSource, ParticipantRole
from app.knowledge.schemas.common import ORMModel


class EventCreate(BaseModel):
    """Create a historical event."""

    event_type: EventType
    title: str = Field(..., min_length=1, max_length=512)
    summary: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    date_uncertainty_note: Optional[str] = None
    place_entity_id: Optional[int] = None
    extraction_source: ExtractionSource = ExtractionSource.HUMAN
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    created_by: Optional[str] = None
    evidence_span_id: Optional[int] = None
    trigger_text: Optional[str] = None


class EventParticipantCreate(BaseModel):
    """Add a participant with an explicit role."""

    entity_id: int
    role: ParticipantRole
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    evidence_span_id: Optional[int] = None


class EventParticipantResponse(ORMModel):
    """Stored participant."""

    id: int
    event_id: int
    entity_id: int
    role: ParticipantRole
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    evidence_span_id: Optional[int] = None
    created_at: datetime


class EventMentionResponse(ORMModel):
    """Stored event mention."""

    id: int
    event_id: int
    evidence_span_id: int
    trigger_text: Optional[str] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    created_at: datetime


class EventResponse(ORMModel):
    """Event with participants and mentions."""

    id: int
    event_type: EventType
    title: str
    summary: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    date_uncertainty_note: Optional[str] = None
    place_entity_id: Optional[int] = None
    extraction_source: ExtractionSource
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    participants: List[EventParticipantResponse] = []
    mentions: List[EventMentionResponse] = []
