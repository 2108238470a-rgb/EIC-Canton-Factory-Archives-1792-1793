"""Document service."""
from pathlib import Path
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Document, DocumentStatus, DocumentType
from app.schemas import DocumentCreate, DocumentUpdate, DocumentResponse, DocumentListResponse
from app.repositories import DocumentRepository
from app.utils import (
    save_upload_file,
    is_pdf,
    is_image,
    delete_document_files,
)
from app.core import logger, FileProcessingError


class DocumentService:
    """Service for document operations."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = DocumentRepository(db)

    async def upload_document(
        self,
        filename: str,
        content: bytes,
    ) -> Document:
        """
        Upload and create a new document.

        Args:
            filename: Original filename
            content: File content bytes

        Returns:
            Created document
        """
        # Validate file type
        if not (is_pdf(filename) or is_image(filename)):
            raise FileProcessingError(f"Unsupported file type: {filename}")

        # Determine file type
        file_type = DocumentType.PDF if is_pdf(filename) else DocumentType.IMAGE

        # Save file
        file_path = save_upload_file(content, filename)
        logger.info(f"Uploaded file saved: {file_path}")

        # Create document record
        doc_data = DocumentCreate(
            filename=file_path.name,
            original_filename=filename,
            file_path=str(file_path),
            file_type=file_type,
            file_size=len(content),
        )

        document = self.repo.create(doc_data)
        logger.info(f"Document created: id={document.id}, filename={filename}")

        return document

    def get_document(self, document_id: int) -> Optional[Document]:
        """Get document by ID."""
        return self.repo.get_by_id(document_id)

    def get_documents(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[DocumentStatus] = None
    ) -> Tuple[List[Document], int]:
        """
        Get documents with pagination.

        Returns:
            Tuple of (documents, total_count)
        """
        skip = (page - 1) * page_size
        documents = self.repo.get_all(skip=skip, limit=page_size, status=status)
        total = self.repo.count(status=status)
        return documents, total

    def update_document(self, document_id: int, data: DocumentUpdate) -> Optional[Document]:
        """Update document."""
        return self.repo.update(document_id, data)

    def update_status(
        self,
        document_id: int,
        status: DocumentStatus,
        error_message: Optional[str] = None
    ) -> Optional[Document]:
        """Update document status."""
        return self.repo.update_status(document_id, status, error_message)

    def delete_document(self, document_id: int) -> bool:
        """Delete document and associated files."""
        document = self.repo.get_by_id(document_id)
        if not document:
            return False

        # Delete files
        delete_document_files(document_id, document.file_path)

        # Delete database record
        return self.repo.delete(document_id)
