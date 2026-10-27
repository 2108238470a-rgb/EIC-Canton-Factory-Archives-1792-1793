"""Corpus application service."""
from typing import List, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Document
from app.knowledge.models import Corpus, CorpusDocumentRecord
from app.knowledge.repositories import CorpusRepository
from app.knowledge.schemas import CorpusCreate, CorpusDocumentAttach, CorpusUpdate


class CorpusService:
    """Create corpora and attach existing OCR documents."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = CorpusRepository(db)

    def create(self, data: CorpusCreate) -> Corpus:
        """Create a corpus."""
        return self.repo.create(data)

    def list(self, page: int, page_size: int) -> Tuple[List[Corpus], int]:
        """List corpora with totals."""
        items = self.repo.get_all(skip=(page - 1) * page_size, limit=page_size)
        return items, self.repo.count()

    def get(self, corpus_id: int) -> Corpus:
        """Get a corpus or raise 404."""
        corpus = self.repo.get_by_id(corpus_id)
        if not corpus:
            raise HTTPException(status_code=404, detail="Corpus not found")
        return corpus

    def update(self, corpus_id: int, data: CorpusUpdate) -> Corpus:
        """Update a corpus."""
        corpus = self.repo.update(corpus_id, data)
        if not corpus:
            raise HTTPException(status_code=404, detail="Corpus not found")
        return corpus

    def attach_document(self, corpus_id: int, data: CorpusDocumentAttach) -> CorpusDocumentRecord:
        """Attach an OCR document that is not already in a corpus.

        Args:
            corpus_id: Target corpus.
            data: OCR document ID and bibliography.

        Returns:
            Bibliographic overlay.

        Raises:
            HTTPException: If the corpus, document, or uniqueness check fails.
        """
        self.get(corpus_id)
        document = self.db.query(Document).filter(Document.id == data.document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="OCR document not found")
        existing = self.repo.get_document_record(data.document_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Document {data.document_id} is already attached to corpus {existing.corpus_id}",
            )
        if not data.canonical_title:
            data = data.model_copy(update={"canonical_title": document.original_filename})
        return self.repo.attach_document(corpus_id, data)
