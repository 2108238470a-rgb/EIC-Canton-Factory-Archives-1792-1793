"""Text revision model for versioning block text."""
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.block import Block
    from app.models.evidence_span import EvidenceSpan


class TextType(str, enum.Enum):
    """Type of text content."""
    OCR_RAW = "ocr_raw"
    OCR_CORRECTED = "ocr_corrected"
    MODERN_ENGLISH = "modern_english"
    TRANSLATION_ZH = "translation_zh"
    MANUAL_TRANSCRIPTION = "manual_transcription"


class TextRevision(Base):
    """
    Immutable text revision for block content.

    Stores versioned text with hash for evidence anchoring.
    """

    __tablename__ = "text_revisions"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    block_id = Column(Integer, ForeignKey("blocks.id", ondelete="CASCADE"), nullable=False, index=True)

    # Text content and type
    text_type = Column(Enum(TextType), nullable=False, comment="文本种类")
    content = Column(Text, nullable=False, comment="不可变正文")
    content_hash = Column(String(64), nullable=False, index=True, comment="内容hash")

    review_state = Column(String(32), nullable=False, default="pending", server_default="pending")

    # Versioning
    previous_revision_id = Column(Integer, ForeignKey("text_revisions.id", ondelete="SET NULL"), nullable=True)
    revision_number = Column(Integer, nullable=False, default=1, comment="版本号")

    # Authorship
    author = Column(String(255), nullable=True, comment="作者（用户或系统）")
    author_type = Column(String(50), nullable=True, comment="作者类型：human/ai/ocr")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    block = relationship("Block", back_populates="text_revisions")
    previous_revision = relationship("TextRevision", remote_side=[id], backref="next_revisions")
    evidence_spans = relationship("app.models.evidence_span.EvidenceSpan", back_populates="text_revision", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<TextRevision(id={self.id}, block_id={self.block_id}, type={self.text_type}, rev={self.revision_number})>"
