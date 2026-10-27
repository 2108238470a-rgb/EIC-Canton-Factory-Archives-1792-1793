"""Event routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.knowledge.schemas import (
    EventCreate,
    EventParticipantCreate,
    EventParticipantResponse,
    EventResponse,
    ListResponse,
)
from app.knowledge.services import EventService

router = APIRouter(prefix="/events", tags=["knowledge-events"])


@router.post("", response_model=EventResponse)
def create_event(data: EventCreate, db: Session = Depends(get_db)) -> EventResponse:
    """Create an event."""
    return EventService(db).create(data)


@router.get("", response_model=ListResponse[EventResponse])
def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: Optional[str] = None,
    db: Session = Depends(get_db),
) -> ListResponse[EventResponse]:
    """List events."""
    items, total = EventService(db).list(page, page_size, query=q)
    return ListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: int, db: Session = Depends(get_db)) -> EventResponse:
    """Get one event."""
    return EventService(db).get(event_id)


@router.post("/{event_id}/participants", response_model=EventParticipantResponse)
def add_participant(
    event_id: int,
    data: EventParticipantCreate,
    db: Session = Depends(get_db),
) -> EventParticipantResponse:
    """Add a participant with an explicit role."""
    return EventService(db).add_participant(event_id, data)
