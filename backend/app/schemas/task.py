"""Task schemas."""
from datetime import datetime
from typing import Optional, Any, Dict, List, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.task import TaskType, TaskStatus


class TaskCreate(BaseModel):
    """Schema for task creation."""
    document_id: Optional[int] = None
    page_id: Optional[int] = None
    block_id: Optional[int] = None
    task_type: TaskType


class TaskUpdate(BaseModel):
    """Schema for task update."""
    celery_task_id: Optional[str] = None
    status: Optional[TaskStatus] = None
    progress: Optional[int] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class TaskResponse(BaseModel):
    """Schema for task response."""
    id: int
    celery_task_id: Optional[str] = None
    document_id: Optional[int] = None
    page_id: Optional[int] = None
    block_id: Optional[int] = None
    task_type: TaskType
    status: TaskStatus
    progress: int
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RunOCRRequest(BaseModel):
    """Request schema for running OCR."""
    # PaddleOCR-VL visualization images are large Base64 fields. The reader uses
    # structured boxes, so keep them off unless a caller explicitly asks for them.
    visualize: bool = False
    restructure_pages: bool = True
    merge_tables: bool = True
    relevel_titles: bool = True


PolishMode = Literal["ocr_correction", "modern_english", "translation_zh"]


class RunPolishRequest(BaseModel):
    """Request schema for running GPT polish."""

    modes: List[PolishMode] = Field(default_factory=lambda: ["ocr_correction"])

    @field_validator("modes")
    @classmethod
    def validate_modes(cls, modes: List[PolishMode]) -> List[PolishMode]:
        """Require a non-empty list without duplicate processing modes."""
        if not modes:
            raise ValueError("At least one polish mode is required")
        if len(modes) != len(set(modes)):
            raise ValueError("Polish modes cannot contain duplicates")
        return modes
