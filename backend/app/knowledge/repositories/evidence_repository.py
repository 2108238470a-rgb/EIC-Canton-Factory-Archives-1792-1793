"""Evidence span persistence."""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.knowledge.models import EvidenceSpan


class EvidenceRepository:
    """Repository for immutable evidence spans."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, span: EvidenceSpan) -> EvidenceSpan:
        """Persist a new span."""
        self.db.add(span)
        self.db.commit()
        self.db.refresh(span)
        return span

    def get_by_id(self, span_id: int) -> Optional[EvidenceSpan]:
        """Load by integer ID."""
        return self.db.query(EvidenceSpan).filter(EvidenceSpan.id == span_id).first()

    def get_by_public_id(self, public_id: str) -> Optional[EvidenceSpan]:
        """Load by stable public identifier."""
        return self.db.query(EvidenceSpan).filter(EvidenceSpan.public_id == public_id).first()

    def list_by_block(self, block_id: int) -> List[EvidenceSpan]:
        """List spans for one OCR block."""
        return (
            self.db.query(EvidenceSpan)
            .filter(EvidenceSpan.block_id == block_id)
            .order_by(EvidenceSpan.created_at.desc())
            .all()
        )

    def list_recent(self, skip: int = 0, limit: int = 20) -> List[EvidenceSpan]:
        """List recent spans."""
        return (
            self.db.query(EvidenceSpan)
            .order_by(EvidenceSpan.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count(self) -> int:
        """Count spans."""
        return self.db.query(EvidenceSpan).count()
