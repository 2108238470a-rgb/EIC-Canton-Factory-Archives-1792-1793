"""Archival metadata model."""
import enum
from datetime import datetime, date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Date, Enum
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.source_unit import SourceUnit


class CompletenessStatus(str, enum.Enum):
    """Archival document completeness status."""
    COMPLETE = "complete"
    PARTIAL = "partial"
    FRAGMENTED = "fragmented"
    UNKNOWN = "unknown"


class ArchivalMetadata(Base):
    """
    Archival metadata for historical documents.

    Stores repository information, archival reference numbers, and date coverage.
    """

    __tablename__ = "archival_metadata"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Repository and reference
    repository = Column(String(255), nullable=True, comment="档案馆藏机构")
    archival_reference = Column(String(255), nullable=True, index=True, comment="档号")
    collection_name = Column(String(500), nullable=True, comment="卷名")

    # Date coverage
    coverage_date_start = Column(Date, nullable=True, comment="覆盖起始日期")
    coverage_date_end = Column(Date, nullable=True, comment="覆盖结束日期")
    date_precision = Column(String(50), nullable=True, comment="日期精度：year/month/day")

    # Completeness
    completeness_status = Column(Enum(CompletenessStatus), default=CompletenessStatus.UNKNOWN, comment="完整性状态")
    completeness_notes = Column(Text, nullable=True, comment="完整性说明")

    # Additional metadata
    original_language = Column(String(50), nullable=True, comment="原始语言")
    notes = Column(Text, nullable=True, comment="备注")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="archival_metadata")
    source_units = relationship("SourceUnit", back_populates="archival_metadata", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ArchivalMetadata(id={self.id}, document_id={self.document_id}, reference={self.archival_reference})>"
