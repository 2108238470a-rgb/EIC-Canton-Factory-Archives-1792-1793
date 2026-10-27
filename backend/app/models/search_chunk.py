"""Search chunk model for RAG retrieval."""
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum, Index, JSON
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.database import Base

if TYPE_CHECKING:
    from app.models.source_unit import SourceUnit


class ChunkStatus(str, enum.Enum):
    """Search chunk indexing status."""
    PENDING = "pending"
    INDEXED = "indexed"
    INVALIDATED = "invalidated"


class SearchChunk(Base):
    """
    Search chunk for RAG retrieval.

    Stores text segments with embeddings for vector search.
    """

    __tablename__ = "search_chunks"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    source_unit_id = Column(Integer, ForeignKey("source_units.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    page_id = Column(Integer, ForeignKey("pages.id", ondelete="CASCADE"), nullable=True)
    block_id = Column(Integer, ForeignKey("blocks.id", ondelete="CASCADE"), nullable=True)

    segments = Column(JSON, nullable=True)
    search_text = Column(Text, nullable=True)
    review_state = Column(String(32), nullable=False, default="pending", server_default="pending")

    # Content
    content = Column(Text, nullable=False, comment="文书片段内容")
    content_hash = Column(String(64), nullable=False, index=True, comment="内容hash")

    # Language and type
    content_language = Column(String(10), nullable=True, comment="内容语言")
    content_type = Column(String(50), nullable=True, comment="内容类型")

    # Evidence spans mapping
    evidence_span_ids = Column(Text, nullable=True, comment="对应证据集合（逗号分隔的ID）")

    # Embedding
    embedding = Column(Vector(1024), nullable=True, comment="向量嵌入")
    embedding_model = Column(String(200), nullable=True, comment="嵌入模型")

    # Indexing status
    status = Column(Enum(ChunkStatus), default=ChunkStatus.PENDING, index=True, comment="索引状态")

    # Full-text search support (tsvector added via migration)
    # content_tsv will be added as a generated column in migration

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    indexed_at = Column(DateTime, nullable=True)

    # Relationships
    source_unit = relationship("SourceUnit", back_populates="search_chunks")

    # Indexes
    __table_args__ = (
        Index('ix_search_chunks_status_indexed', 'status', 'indexed_at'),
    )

    def __repr__(self) -> str:
        return f"<SearchChunk(id={self.id}, source_unit_id={self.source_unit_id}, status={self.status})>"
