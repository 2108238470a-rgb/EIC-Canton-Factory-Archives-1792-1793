"""Event application service."""
from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.knowledge.models import EventMention, EventParticipant, HistoricalEvent
from app.knowledge.repositories import EntityRepository, EventRepository, EvidenceRepository
from app.knowledge.schemas import EventCreate, EventParticipantCreate


class EventService:
    """Create events and attach participants with explicit roles."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = EventRepository(db)
        self.entity_repo = EntityRepository(db)
        self.evidence_repo = EvidenceRepository(db)

    def create(self, data: EventCreate) -> HistoricalEvent:
        """Create an event and optional trigger mention."""
        if data.place_entity_id is not None and not self.entity_repo.get_entity(data.place_entity_id):
            raise HTTPException(status_code=404, detail="Place entity not found")
        payload = data.model_dump(exclude={"evidence_span_id", "trigger_text"})
        event = HistoricalEvent(**payload)
        event = self.repo.create(event)
        if data.evidence_span_id is not None:
            span = self.evidence_repo.get_by_id(data.evidence_span_id)
            if not span:
                raise HTTPException(status_code=404, detail="Evidence span not found")
            self.repo.add_mention(
                EventMention(
                    event_id=event.id,
                    evidence_span_id=span.id,
                    trigger_text=data.trigger_text,
                )
            )
        loaded = self.repo.get_by_id(event.id)
        if loaded is None:
            raise HTTPException(status_code=500, detail="Failed to reload event")
        return loaded

    def list(self, page: int, page_size: int, query: Optional[str] = None) -> Tuple[List[HistoricalEvent], int]:
        """List events."""
        items = self.repo.list_events(skip=(page - 1) * page_size, limit=page_size, query=query)
        return items, self.repo.count()

    def get(self, event_id: int) -> HistoricalEvent:
        """Load an event."""
        event = self.repo.get_by_id(event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        return event

    def add_participant(self, event_id: int, data: EventParticipantCreate) -> EventParticipant:
        """Attach a participant. Being mentioned is not the same as acting."""
        self.get(event_id)
        if not self.entity_repo.get_entity(data.entity_id):
            raise HTTPException(status_code=404, detail="Entity not found")
        if data.evidence_span_id is not None and not self.evidence_repo.get_by_id(data.evidence_span_id):
            raise HTTPException(status_code=404, detail="Evidence span not found")
        return self.repo.add_participant(EventParticipant(event_id=event_id, **data.model_dump()))
