"""Workbench aggregation service."""
from sqlalchemy.orm import Session

from app.knowledge.repositories import (
    AssertionRepository,
    CorpusRepository,
    EntityRepository,
    EventRepository,
    EvidenceRepository,
)
from app.knowledge.schemas import WorkbenchOverviewResponse


class WorkbenchService:
    """Counts and search entry points for the knowledge workbench."""

    def __init__(self, db: Session) -> None:
        self.corpus_repo = CorpusRepository(db)
        self.evidence_repo = EvidenceRepository(db)
        self.entity_repo = EntityRepository(db)
        self.event_repo = EventRepository(db)
        self.assertion_repo = AssertionRepository(db)

    def overview(self) -> WorkbenchOverviewResponse:
        """Return object counts for the workbench home."""
        return WorkbenchOverviewResponse(
            corpora=self.corpus_repo.count(),
            corpus_documents=self.corpus_repo.count_documents(),
            evidence_spans=self.evidence_repo.count(),
            mentions=self.entity_repo.count_mentions(),
            unresolved_mentions=self.entity_repo.count_mentions(unresolved_only=True),
            entities=self.entity_repo.count_entities(),
            events=self.event_repo.count(),
            assertions=self.assertion_repo.count(),
        )
