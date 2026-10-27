"""Assertion and review application service."""
from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.knowledge.enums import AssertionSourceType
from app.knowledge.models import Assertion, AssertionEvidence, ReviewDecision
from app.knowledge.repositories import AssertionRepository, EntityRepository, EvidenceRepository
from app.knowledge.schemas import AssertionCreate, ReviewDecisionCreate


class AssertionService:
    """Store sourced claims without collapsing contradictions."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AssertionRepository(db)
        self.entity_repo = EntityRepository(db)
        self.evidence_repo = EvidenceRepository(db)

    def create(self, data: AssertionCreate) -> Assertion:
        """Create an assertion. Inferences cannot be marked as direct evidence."""
        if not self.entity_repo.get_entity(data.subject_entity_id):
            raise HTTPException(status_code=404, detail="Subject entity not found")
        if data.object_entity_id is not None and not self.entity_repo.get_entity(data.object_entity_id):
            raise HTTPException(status_code=404, detail="Object entity not found")
        if data.is_inferred and data.source_type == AssertionSourceType.DIRECT_EVIDENCE:
            raise HTTPException(
                status_code=400,
                detail="Inferred assertions cannot use source_type=direct_evidence",
            )
        for item in data.evidence:
            if not self.evidence_repo.get_by_id(item.evidence_span_id):
                raise HTTPException(status_code=404, detail="Evidence span not found")

        assertion = Assertion(
            **data.model_dump(exclude={"evidence"}),
            evidence_links=[
                AssertionEvidence(evidence_span_id=item.evidence_span_id, stance=item.stance)
                for item in data.evidence
            ],
        )
        return self.repo.create(assertion)

    def list(
        self,
        page: int,
        page_size: int,
        subject_entity_id: Optional[int] = None,
    ) -> Tuple[List[Assertion], int]:
        """List assertions."""
        items = self.repo.list_assertions(
            skip=(page - 1) * page_size,
            limit=page_size,
            subject_entity_id=subject_entity_id,
        )
        return items, self.repo.count()

    def get(self, assertion_id: int) -> Assertion:
        """Load an assertion."""
        assertion = self.repo.get_by_id(assertion_id)
        if not assertion:
            raise HTTPException(status_code=404, detail="Assertion not found")
        return assertion

    def add_review(self, data: ReviewDecisionCreate) -> ReviewDecision:
        """Store a human review against any knowledge object."""
        return self.repo.add_review(ReviewDecision(**data.model_dump()))
