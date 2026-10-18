"""Assertion and review routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.knowledge.schemas import (
    AssertionCreate,
    AssertionResponse,
    ListResponse,
    ReviewDecisionCreate,
    ReviewDecisionResponse,
)
from app.knowledge.services import AssertionService

router = APIRouter(tags=["knowledge-assertions"])


@router.post("/assertions", response_model=AssertionResponse)
def create_assertion(data: AssertionCreate, db: Session = Depends(get_db)) -> AssertionResponse:
    """Create a sourced historical assertion."""
    return AssertionService(db).create(data)


@router.get("/assertions", response_model=ListResponse[AssertionResponse])
def list_assertions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    subject_entity_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> ListResponse[AssertionResponse]:
    """List assertions."""
    items, total = AssertionService(db).list(page, page_size, subject_entity_id=subject_entity_id)
    return ListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/assertions/{assertion_id}", response_model=AssertionResponse)
def get_assertion(assertion_id: int, db: Session = Depends(get_db)) -> AssertionResponse:
    """Get one assertion."""
    return AssertionService(db).get(assertion_id)


@router.post("/reviews", response_model=ReviewDecisionResponse)
def create_review(
    data: ReviewDecisionCreate,
    db: Session = Depends(get_db),
) -> ReviewDecisionResponse:
    """Record a human review decision."""
    return AssertionService(db).add_review(data)
