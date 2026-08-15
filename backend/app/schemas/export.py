"""Export schemas."""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel

from app.models.export import ExportFormat, ExportStatus


class ExportCreate(BaseModel):
    """Schema for export creation."""
    document_id: int
    format: ExportFormat


class ExportResponse(BaseModel):
    """Schema for export response."""
    id: int
    document_id: int
    format: ExportFormat
    status: ExportStatus
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExportListResponse(BaseModel):
    """Schema for export list response."""
    items: List[ExportResponse]
    total: int


class ExportRequest(BaseModel):
    """Request schema for creating export."""
    format: ExportFormat
    text_mode: Optional[str] = None  # "ocr_raw" or "llm_polished" (default)
