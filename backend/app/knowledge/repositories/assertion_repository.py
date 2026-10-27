"""Assertion and review persistence."""
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.knowledge.models import Assertion, ReviewDecision


class AssertionRepository:
    """Repository for assertions and review decisions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, assertion: Assertion) -> Assertion:
        """Persist an assertion with evidence links."""
        self.db.add(assertion)
        self.db.commit()
        loaded = self.get_by_id(assertion.id)
        if loaded is None:
            raise RuntimeError("Failed to reload assertion after insert")
        return loaded

    def get_by_id(self, assertion_id: int) -> Optional[Assertion]:
        """Load an assertion with evidence links."""
        return (
            self.db.query(Assertion)
            .options(joinedload(Assertion.evidence_links))
            .filter(Assertion.id == assertion_id)
            .first()
        )

    def list_assertions(
        self,
        skip: int = 0,
        limit: int = 20,
        subject_entity_id: Optional[int] = None,
    ) -> List[Assertion]:
        """List assertions, optionally filtered by subject."""
        q = self.db.query(Assertion).options(joinedload(Assertion.evidence_links))
        if subject_entity_id is not None:
            q = q.filter(Assertion.subject_entity_id == subject_entity_id)
        return q.order_by(Assertion.created_at.desc()).offset(skip).limit(limit).all()

    def count(self) -> int:
        """Count assertions."""
        return self.db.query(Assertion).count()

    def add_review(self, review: ReviewDecision) -> ReviewDecision:
        """Persist a review decision."""
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)
        return review
