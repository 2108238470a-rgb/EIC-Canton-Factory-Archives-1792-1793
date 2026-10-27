"""Evidence span model for text anchoring."""
import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum, JSON, Float
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.text_revision import TextRevision
    from app.models.page import Page
    from app.models.entity_mention import EntityMention
    from app.models.assertion_evidence import AssertionEvidence


class LocationPrecision(str, enum.Enum):
    """Evidence location precision."""
    CHARACTER = "character"
    WORD = "word"
    LINE = "line"
    BLOCK = "block"
    PAGE = "page"
    MANUAL_BBOX = "manual_bbox"


class EvidenceSpan(Base):
    """
    Evidence span anchoring text to specific locations.

    Uses Web Annotation Model approach with character offsets and bounding boxes.
    """

    __tablename__ = "evidence_spans"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    text_revision_id = Column(Integer, ForeignKey("text_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id = Column(Integer, ForeignKey("pages.id", ondelete="CASCADE"), nullable=True, index=True)

    validity = Column(String(32), nullable=False, default="current", server_default="current", index=True)
    public_id = Column(String(64), nullable=True, unique=True)

    image_snapshot_path = Column(String(512), nullable=True)

    # Character-based anchoring (Unicode code points, left-closed right-open)
    char_start = Column(Integer, nullable=True, comment="起始字符偏移")
    char_end = Column(Integer, nullable=True, comment="结束字符偏移")

    # Text selectors for robustness
    exact_text = Column(Text, nullable=True, comment="精确引句")
    prefix_text = Column(String(100), nullable=True, comment="前缀文本")
    suffix_text = Column(String(100), nullable=True, comment="后缀文本")

    # Image-based anchoring (original image coordinates)
    bbox = Column(JSON, nullable=True, comment="边界框 [x1, y1, x2, y2]")
    image_width = Column(Integer, nullable=True, comment="图像宽度")
    image_height = Column(Integer, nullable=True, comment="图像高度")
    image_version = Column(String(100), nullable=True, comment="图像版本")

    # Precision metadata
    location_precision = Column(Enum(LocationPrecision), default=LocationPrecision.BLOCK, comment="定位精度")
    confidence = Column(Float, nullable=True, comment="置信度")

    # Crop image
    crop_image_path = Column(String(512), nullable=True, comment="裁图路径")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    text_revision = relationship("TextRevision", back_populates="evidence_spans")
    page = relationship("Page", back_populates="evidence_spans")
    entity_mentions = relationship("app.models.entity_mention.EntityMention", back_populates="evidence_span")
    assertion_evidences = relationship("app.models.assertion_evidence.AssertionEvidence", back_populates="evidence_span")

    def __repr__(self) -> str:
        return f"<EvidenceSpan(id={self.id}, revision_id={self.text_revision_id}, chars={self.char_start}-{self.char_end})>"
