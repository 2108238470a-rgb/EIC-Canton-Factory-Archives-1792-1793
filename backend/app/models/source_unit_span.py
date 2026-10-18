"""Source unit span model for block-level mapping."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.source_unit import SourceUnit
    from app.models.block import Block


class SourceUnitSpan(Base):
    """
    Maps source units to blocks with character ranges.

    Allows source units to span multiple blocks and pages.
    """

    __tablename__ = "source_unit_spans"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    source_unit_id = Column(Integer, ForeignKey("source_units.id", ondelete="CASCADE"), nullable=False, index=True)
    block_id = Column(Integer, ForeignKey("blocks.id", ondelete="CASCADE"), nullable=False, index=True)

    revision_id = Column(Integer, ForeignKey("text_revisions.id"), nullable=True)

    # Reading order and position
    reading_order = Column(Integer, nullable=False, comment="阅读顺序")
    char_start = Column(Integer, nullable=True, comment="起始字符偏移（Unicode码点）")
    char_end = Column(Integer, nullable=True, comment="结束字符偏移（Unicode码点）")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    source_unit = relationship("SourceUnit", back_populates="spans")
    block = relationship("Block", back_populates="source_unit_spans")

    def __repr__(self) -> str:
        return f"<SourceUnitSpan(id={self.id}, source_unit_id={self.source_unit_id}, block_id={self.block_id})>"
