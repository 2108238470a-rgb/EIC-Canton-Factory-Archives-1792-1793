"""Document repository."""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Document, DocumentStatus
from app.schemas import DocumentCreate, DocumentUpdate


class DocumentRepository:
    """Repository for document operations."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, data: DocumentCreate) -> Document:
        """Create a new document."""
        document = Document(**data.model_dump())
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def get_by_id(self, document_id: int) -> Optional[Document]:
        """Get document by ID."""
        return self.db.query(Document).filter(Document.id == document_id).first()

    def get_all(
        self,
        skip: int = 0,
        limit: int = 20,
        status: Optional[DocumentStatus] = None
    ) -> List[Document]:
        """Get all documents with pagination."""
        query = self.db.query(Document)
        if status:
            query = query.filter(Document.status == status)
        return query.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()

    def count(self, status: Optional[DocumentStatus] = None) -> int:
        """Count documents."""
        query = self.db.query(Document)
        if status:
            query = query.filter(Document.status == status)
        return query.count()

    def update(self, document_id: int, data: DocumentUpdate) -> Optional[Document]:
        """Update document."""
        document = self.get_by_id(document_id)
        if not document:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(document, field, value)

        self.db.commit()
        self.db.refresh(document)
        return document

    def delete(self, document_id: int) -> bool:
        """Delete document."""
        document = self.get_by_id(document_id)
        if not document:
            return False

        self.db.delete(document)
        self.db.commit()
        return True

    def update_status(self, document_id: int, status: DocumentStatus, error_message: Optional[str] = None) -> Optional[Document]:
        """Update document status."""
        document = self.get_by_id(document_id)
        if not document:
            return None

        document.status = status
        if error_message:
            document.error_message = error_message

        self.db.commit()
        self.db.refresh(document)
        return document
