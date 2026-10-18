"""Immutable evidence span models."""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.knowledge.enums import ExtractionSource, TextVersion, sa_enum


class EvidenceSpan(Base):
    """A citable character range on a specific OCR text version.

    The excerpt is copied at creation time. Later OCR edits do not mutate
    this row; a new span (optionally with parent_span_id) must be created.
    """

    __tablename__ = "knowledge_evidence_spans"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    public_id = Column(String(36), unique=True, nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    page_id = Column(Integer, ForeignKey("pages.id", ondelete="RESTRICT"), nullable=False, index=True)
    block_id = Column(Integer, ForeignKey("blocks.id", ondelete="RESTRICT"), nullable=False, index=True)
    text_version = Column(sa_enum(TextVersion), nullable=False)
    parent_span_id = Column(
        Integer,
        ForeignKey("knowledge_evidence_spans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    char_start = Column(Integer, nullable=False)
    char_end = Column(Integer, nullable=False)
    line_start = Column(Integer, nullable=True)
    line_end = Column(Integer, nullable=True)
    excerpt = Column(Text, nullable=False)
    quality_flag = Column(String(64), nullable=True)
    ocr_risk = Column(String(64), nullable=True)
    extraction_source = Column(sa_enum(ExtractionSource), nullable=False, default=ExtractionSource.HUMAN)
    created_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    parent = relationship("app.knowledge.models.evidence.EvidenceSpan", remote_side=[id])
