"""Task model."""
import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum, JSON
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.document import Document


class TaskType(str, enum.Enum):
    """Task type."""
    OCR = "ocr"
    OCR_CORRECTION = "ocr_correction"
    MODERN_ENGLISH = "modern_english"
    TRANSLATION_ZH = "translation_zh"
    EXPORT = "export"


class TaskStatus(str, enum.Enum):
    """Task status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(Base):
    """Task model for tracking async operations."""

    __tablename__ = "tasks"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    celery_task_id = Column(String(255), unique=True, index=True, nullable=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    page_id = Column(Integer, nullable=True)
    block_id = Column(Integer, nullable=True)
    task_type = Column(Enum(TaskType), nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING)
    progress = Column(Integer, default=0)  # 0-100
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="tasks")

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, type={self.task_type}, status={self.status})>"
