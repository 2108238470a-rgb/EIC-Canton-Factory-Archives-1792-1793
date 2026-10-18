"""Corpus schemas."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.knowledge.schemas.common import ORMModel


class CorpusCreate(BaseModel):
    """Payload for creating a corpus."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    source_institution: Optional[str] = None
    citation: Optional[str] = None
    completeness_note: Optional[str] = None


class CorpusUpdate(BaseModel):
    """Partial corpus update."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    source_institution: Optional[str] = None
    citation: Optional[str] = None
    completeness_note: Optional[str] = None


class CorpusDocumentAttach(BaseModel):
    """Attach an existing OCR document to a corpus with bibliography."""

    document_id: int
    canonical_title: Optional[str] = None
    volume: Optional[str] = None
    archive_id: Optional[str] = None
    source_institution: Optional[str] = None
    language: Optional[str] = None
    document_type: Optional[str] = None
    compiler: Optional[str] = None
    edition: Optional[str] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    is_complete: Optional[int] = None
    missing_pages_note: Optional[str] = None
    duplicate_pages_note: Optional[str] = None
    page_mapping_note: Optional[str] = None
    rights_status: Optional[str] = None
    citation: Optional[str] = None


class CorpusDocumentRecordResponse(ORMModel):
    """Bibliographic overlay for one OCR document."""

    id: int
    corpus_id: int
    document_id: int
    canonical_title: Optional[str] = None
    volume: Optional[str] = None
    archive_id: Optional[str] = None
    source_institution: Optional[str] = None
    language: Optional[str] = None
    document_type: Optional[str] = None
    compiler: Optional[str] = None
    edition: Optional[str] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    is_complete: Optional[int] = None
    missing_pages_note: Optional[str] = None
    duplicate_pages_note: Optional[str] = None
    page_mapping_note: Optional[str] = None
    rights_status: Optional[str] = None
    citation: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CorpusResponse(ORMModel):
    """Corpus with attached documents."""

    id: int
    name: str
    description: Optional[str] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    source_institution: Optional[str] = None
    citation: Optional[str] = None
    completeness_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    documents: List[CorpusDocumentRecordResponse] = []
