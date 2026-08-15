"""Block schemas."""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field

from app.models.block import ReviewStatus


class BlockBase(BaseModel):
    """Base block schema."""
    block_index: int
    block_label: Optional[str] = None
    bbox: List[float] = Field(..., description="Bounding box [x1, y1, x2, y2]")


class BlockCreate(BaseModel):
    """Schema for block creation."""
    page_id: int
    block_index: int
    block_label: Optional[str] = None
    bbox: List[float]
    confidence: Optional[float] = None
    ocr_text_raw: Optional[str] = None


class BlockUpdate(BaseModel):
    """Schema for block update."""
    block_label: Optional[str] = None
    ocr_text_raw: Optional[str] = None
    ocr_text_corrected: Optional[str] = None
    modern_english: Optional[str] = None
    translation_zh: Optional[str] = None
    review_status: Optional[ReviewStatus] = None


class BlockResponse(BaseModel):
    """Schema for block response."""
    id: int
    page_id: int
    block_index: int
    block_label: Optional[str] = None
    bbox: List[float]
    confidence: Optional[float] = None
    ocr_text_raw: Optional[str] = None
    ocr_text_corrected: Optional[str] = None
    modern_english: Optional[str] = None
    translation_zh: Optional[str] = None
    review_status: ReviewStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BlockListResponse(BaseModel):
    """Schema for block list response."""
    items: List[BlockResponse]
    total: int
