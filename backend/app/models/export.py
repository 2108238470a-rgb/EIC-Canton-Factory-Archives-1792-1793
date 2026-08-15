"""Export model."""
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.document import Document


class ExportFormat(str, enum.Enum):
    """Export format."""
    JSON = "json"
    MARKDOWN = "markdown"
    TXT = "txt"
    DOCX = "docx"  # Reserved
    PDF = "pdf"    # Reserved


class ExportStatus(str, enum.Enum):
    """Export status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Export(Base):
    """Export model for tracking document exports."""

    __tablename__ = "exports"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    format = Column(Enum(ExportFormat), nullable=False)
    status = Column(Enum(ExportStatus), default=ExportStatus.PENDING)
    file_path = Column(String(512), nullable=True)
    file_size = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="exports")

    def __repr__(self) -> str:
        return f"<Export(id={self.id}, document_id={self.document_id}, format={self.format})>"
