"""Page schemas."""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class PageBase(BaseModel):
    """Base page schema."""
    page_number: int


class PageCreate(BaseModel):
    """Schema for page creation."""
    document_id: int
    page_number: int
    image_path: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class PageUpdate(BaseModel):
    """Schema for page update."""
    image_path: Optional[str] = None
    visualization_path: Optional[str] = None
    markdown_content: Optional[str] = None
    pruned_result_path: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class PageBriefResponse(BaseModel):
    """Brief page response for document list."""
    id: int
    page_number: int
    image_path: Optional[str] = None
    markdown_content: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None

    class Config:
        from_attributes = True


class PageResponse(BaseModel):
    """Schema for page response."""
    id: int
    document_id: int
    page_number: int
    image_path: Optional[str] = None
    visualization_path: Optional[str] = None
    markdown_content: Optional[str] = None
    pruned_result_path: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PageDetailResponse(PageResponse):
    """Schema for page response with blocks."""
    blocks: List["BlockResponse"] = []

    class Config:
        from_attributes = True


# Import here to avoid circular imports
from app.schemas.block import BlockResponse
PageDetailResponse.model_rebuild()
