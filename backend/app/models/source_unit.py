"""Source unit model for document segments."""
import enum
from datetime import datetime, date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Date, Enum
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.archival_metadata import ArchivalMetadata
    from app.models.source_unit_span import SourceUnitSpan
    from app.models.event_mention import EventMention


class SourceUnitType(str, enum.Enum):
    """Type of source unit."""
    LETTER_INCOMING = "letter_incoming"
    LETTER_OUTGOING = "letter_outgoing"
    DIARY_ENTRY = "diary_entry"
    MEETING_MINUTES = "meeting_minutes"
    REPORT = "report"
    ATTACHMENT = "attachment"
    TITLE = "title"
    OTHER = "other"


class SegmentationStatus(str, enum.Enum):
    """Segmentation review status."""
    PENDING = "pending"
    APPROVED = "approved"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


class DatePrecision(str, enum.Enum):
    """Date precision level."""
    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    APPROXIMATE = "approximate"
    UNKNOWN = "unknown"


class SourceUnit(Base):
    """
    Source unit representing a document segment (letter, diary entry, etc.).

    A source unit can span multiple blocks and pages.
    """

    __tablename__ = "source_units"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    archival_metadata_id = Column(Integer, ForeignKey("archival_metadata.id", ondelete="CASCADE"), nullable=False, index=True)

    # Type and identification
    unit_type = Column(Enum(SourceUnitType), nullable=False, comment="文书类型")
    title = Column(String(500), nullable=True, comment="标题")
    sequence_number = Column(Integer, nullable=True, comment="序号")

    # Date information
    original_date_text = Column(String(255), nullable=True, comment="原文日期")
    normalized_date_start = Column(Date, nullable=True, index=True, comment="规范起始日期")
    normalized_date_end = Column(Date, nullable=True, comment="规范结束日期")
    date_precision = Column(Enum(DatePrecision), default=DatePrecision.UNKNOWN, comment="日期精度")
    date_basis = Column(Text, nullable=True, comment="日期依据")

    # Segmentation review
    segmentation_status = Column(Enum(SegmentationStatus), default=SegmentationStatus.PENDING, comment="分段审核状态")
    segmentation_notes = Column(Text, nullable=True, comment="分段说明")

    # Content summary
    summary = Column(Text, nullable=True, comment="内容摘要")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    archival_metadata = relationship("ArchivalMetadata", back_populates="source_units")
    spans = relationship("SourceUnitSpan", back_populates="source_unit", cascade="all, delete-orphan", order_by="SourceUnitSpan.reading_order")
    event_mentions = relationship("app.models.event_mention.EventMention", back_populates="source_unit", cascade="all, delete-orphan")
    search_chunks = relationship("SearchChunk", back_populates="source_unit", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<SourceUnit(id={self.id}, type={self.unit_type}, title={self.title})>"
