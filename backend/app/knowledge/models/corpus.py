"""Corpus and bibliographic overlay models."""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class Corpus(Base):
    """A bounded historical collection used as an analysis universe."""

    __tablename__ = "knowledge_corpora"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    date_start = Column(String(64), nullable=True)
    date_end = Column(String(64), nullable=True)
    source_institution = Column(String(255), nullable=True)
    citation = Column(Text, nullable=True)
    completeness_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    documents = relationship(
        "CorpusDocumentRecord",
        back_populates="corpus",
        cascade="all, delete-orphan",
    )


class CorpusDocumentRecord(Base):
    """Bibliographic record linking one OCR document into a corpus.

    Completeness and missing-page notes live here so archival bias is not
    mistaken for historical activity.
    """

    __tablename__ = "knowledge_corpus_documents"
    __allow_unmapped__ = True
    __table_args__ = (
        UniqueConstraint("document_id", name="uq_knowledge_corpus_document"),
    )

    id = Column(Integer, primary_key=True, index=True)
    corpus_id = Column(Integer, ForeignKey("knowledge_corpora.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    canonical_title = Column(String(512), nullable=True)
    volume = Column(String(128), nullable=True)
    archive_id = Column(String(255), nullable=True)
    source_institution = Column(String(255), nullable=True)
    language = Column(String(64), nullable=True)
    document_type = Column(String(128), nullable=True)
    compiler = Column(String(255), nullable=True)
    edition = Column(String(128), nullable=True)
    date_start = Column(String(64), nullable=True)
    date_end = Column(String(64), nullable=True)
    is_complete = Column(Integer, nullable=True)
    missing_pages_note = Column(Text, nullable=True)
    duplicate_pages_note = Column(Text, nullable=True)
    page_mapping_note = Column(Text, nullable=True)
    rights_status = Column(String(128), nullable=True)
    citation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    corpus = relationship("Corpus", back_populates="documents")
