"""Page model."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.block import Block


class Page(Base):
    """Page model representing a single page in a document."""

    __tablename__ = "pages"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    original_page_label = Column(String(100), nullable=True)
    folio_side = Column(String(16), nullable=True)
    image_path = Column(String(512), nullable=True)
    visualization_path = Column(String(512), nullable=True)
    markdown_content = Column(Text, nullable=True)
    pruned_result_path = Column(String(512), nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="pages")
    blocks = relationship("Block", back_populates="page", cascade="all, delete-orphan")
    evidence_spans = relationship("app.models.evidence_span.EvidenceSpan", back_populates="page", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Page(id={self.id}, document_id={self.document_id}, page_number={self.page_number})>"