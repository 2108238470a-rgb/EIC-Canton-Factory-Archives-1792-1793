"""Evidence span routes."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.knowledge.schemas import (
    EvidenceLocatorResponse,
    EvidenceSpanCreate,
    EvidenceSpanResponse,
    ListResponse,
)
from app.knowledge.services import EvidenceService

router = APIRouter(prefix="/evidence-spans", tags=["knowledge-evidence"])


@router.post("", response_model=EvidenceSpanResponse)
def create_evidence_span(
    data: EvidenceSpanCreate,
    db: Session = Depends(get_db),
) -> EvidenceSpanResponse:
    """Copy a block text layer into an immutable evidence span."""
    return EvidenceService(db).create_from_block(data)


@router.get("", response_model=ListResponse[EvidenceSpanResponse])
def list_evidence_spans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ListResponse[EvidenceSpanResponse]:
    """List recent evidence spans."""
    items, total = EvidenceService(db).list_recent(page, page_size)
    return ListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{span_id}", response_model=EvidenceSpanResponse)
def get_evidence_span(span_id: int, db: Session = Depends(get_db)) -> EvidenceSpanResponse:
    """Get one evidence span."""
    return EvidenceService(db).get(span_id)


@router.get("/{span_id}/locator", response_model=EvidenceLocatorResponse)
def get_evidence_locator(
    span_id: int,
    db: Session = Depends(get_db),
) -> EvidenceLocatorResponse:
    """Return a viewer path back to the originating page and block."""
    return EvidenceService(db).locator(span_id)
