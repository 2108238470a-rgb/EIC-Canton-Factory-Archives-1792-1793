"""Event persistence."""
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.knowledge.models import EventMention, EventParticipant, HistoricalEvent


class EventRepository:
    """Repository for events, mentions, and participants."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, event: HistoricalEvent) -> HistoricalEvent:
        """Persist an event."""
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def get_by_id(self, event_id: int) -> Optional[HistoricalEvent]:
        """Load an event with participants and mentions."""
        return (
            self.db.query(HistoricalEvent)
            .options(
                joinedload(HistoricalEvent.participants),
                joinedload(HistoricalEvent.mentions),
            )
            .filter(HistoricalEvent.id == event_id)
            .first()
        )

    def list_events(self, skip: int = 0, limit: int = 20, query: Optional[str] = None) -> List[HistoricalEvent]:
        """List events."""
        q = self.db.query(HistoricalEvent).options(joinedload(HistoricalEvent.participants))
        if query:
            q = q.filter(HistoricalEvent.title.ilike(f"%{query}%"))
        return q.order_by(HistoricalEvent.created_at.desc()).offset(skip).limit(limit).all()

    def count(self) -> int:
        """Count events."""
        return self.db.query(HistoricalEvent).count()

    def add_participant(self, participant: EventParticipant) -> EventParticipant:
        """Persist a participant."""
        self.db.add(participant)
        self.db.commit()
        self.db.refresh(participant)
        return participant

    def add_mention(self, mention: EventMention) -> EventMention:
        """Persist an event mention."""
        self.db.add(mention)
        self.db.commit()
        self.db.refresh(mention)
        return mention

    def list_for_entity(self, entity_id: int) -> List[HistoricalEvent]:
        """Events where the entity participates."""
        return (
            self.db.query(HistoricalEvent)
            .join(EventParticipant)
            .filter(EventParticipant.entity_id == entity_id)
            .order_by(HistoricalEvent.start_date.asc().nullslast(), HistoricalEvent.id.asc())
            .all()
        )
