"""Corpus persistence."""
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.knowledge.models import Corpus, CorpusDocumentRecord
from app.knowledge.schemas import CorpusCreate, CorpusDocumentAttach, CorpusUpdate


class CorpusRepository:
    """Repository for corpora and bibliographic overlays."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, data: CorpusCreate) -> Corpus:
        """Insert a corpus.

        Args:
            data: Corpus fields.

        Returns:
            Persisted corpus.
        """
        corpus = Corpus(**data.model_dump())
        self.db.add(corpus)
        self.db.commit()
        self.db.refresh(corpus)
        return corpus

    def get_by_id(self, corpus_id: int) -> Optional[Corpus]:
        """Load a corpus with documents."""
        return (
            self.db.query(Corpus)
            .options(joinedload(Corpus.documents))
            .filter(Corpus.id == corpus_id)
            .first()
        )

    def get_all(self, skip: int = 0, limit: int = 20) -> List[Corpus]:
        """List corpora."""
        return (
            self.db.query(Corpus)
            .options(joinedload(Corpus.documents))
            .order_by(Corpus.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count(self) -> int:
        """Count corpora."""
        return self.db.query(Corpus).count()

    def update(self, corpus_id: int, data: CorpusUpdate) -> Optional[Corpus]:
        """Patch corpus fields."""
        corpus = self.get_by_id(corpus_id)
        if not corpus:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(corpus, field, value)
        self.db.commit()
        return self.get_by_id(corpus_id)

    def get_document_record(self, document_id: int) -> Optional[CorpusDocumentRecord]:
        """Find the bibliographic overlay for an OCR document."""
        return (
            self.db.query(CorpusDocumentRecord)
            .filter(CorpusDocumentRecord.document_id == document_id)
            .first()
        )

    def attach_document(self, corpus_id: int, data: CorpusDocumentAttach) -> CorpusDocumentRecord:
        """Attach an OCR document to a corpus.

        Args:
            corpus_id: Target corpus.
            data: OCR document ID and bibliographic fields.

        Returns:
            New overlay row.
        """
        record = CorpusDocumentRecord(corpus_id=corpus_id, **data.model_dump())
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def count_documents(self) -> int:
        """Count bibliographic overlays."""
        return self.db.query(CorpusDocumentRecord).count()
