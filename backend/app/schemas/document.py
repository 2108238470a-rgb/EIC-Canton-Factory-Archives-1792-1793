"""Document schemas."""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field

from app.models.document import DocumentStatus, DocumentType


class DocumentBase(BaseModel):
    """Base document schema."""

    filename: str
    original_filename: str


class DocumentCreate(BaseModel):
    """Schema for document creation (internal use)."""

    filename: str
    original_filename: str
    file_path: str
    file_type: DocumentType
    file_size: int


class DocumentUpdate(BaseModel):
    """Schema for document update."""

    status: Optional[DocumentStatus] = None
    page_count: Optional[int] = None
    full_markdown: Optional[str] = None
    error_message: Optional[str] = None


class DocumentResponse(BaseModel):
    """Schema for document response."""

    id: int
    archived_at: Optional[datetime] = None
    processing_summary: dict = Field(default_factory=dict)
    filename: str
    original_filename: str
    file_type: DocumentType
    file_size: int
    page_count: int
    full_markdown: Optional[str] = None
    status: DocumentStatus
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Schema for document list response."""

    items: List[DocumentResponse]
    total: int
    page: int
    page_size: int


class DocumentDetailResponse(DocumentResponse):
    """Schema for document detail response with pages."""

    pages: List["PageBriefResponse"] = []

    class Config:
        from_attributes = True


# Import here to avoid circular imports
from app.schemas.page import PageBriefResponse

DocumentDetailResponse.model_rebuild()
