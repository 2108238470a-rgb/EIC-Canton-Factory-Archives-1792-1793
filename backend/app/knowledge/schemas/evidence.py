"""Evidence span schemas."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.knowledge.enums import ExtractionSource, TextVersion
from app.knowledge.schemas.common import ORMModel


class EvidenceSpanCreate(BaseModel):
    """Create an immutable span from an existing OCR block."""

    block_id: int
    text_version: TextVersion = TextVersion.OCR_RAW
    char_start: Optional[int] = Field(None, ge=0)
    char_end: Optional[int] = Field(None, ge=0)
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    parent_span_id: Optional[int] = None
    quality_flag: Optional[str] = None
    ocr_risk: Optional[str] = None
    extraction_source: ExtractionSource = ExtractionSource.HUMAN
    created_by: Optional[str] = None


class EvidenceSpanResponse(ORMModel):
    """Stored evidence span."""

    id: int
    public_id: str
    document_id: int
    page_id: int
    block_id: int
    text_version: TextVersion
    parent_span_id: Optional[int] = None
    char_start: int
    char_end: int
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    excerpt: str
    quality_flag: Optional[str] = None
    ocr_risk: Optional[str] = None
    extraction_source: ExtractionSource
    created_by: Optional[str] = None
    created_at: datetime


class EvidenceLocatorResponse(BaseModel):
    """Locator that sends a researcher back to the OCR viewer."""

    evidence_span: EvidenceSpanResponse
    page_number: Optional[int] = None
    bbox: Optional[List[float]] = None
    image_path: Optional[str] = None
    viewer_path: str
