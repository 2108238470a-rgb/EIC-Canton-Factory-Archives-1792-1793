"""Research views and migration provenance over the canonical knowledge model."""

from datetime import datetime
from uuid import uuid4
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    JSON,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from app.database import Base


class Annotation(Base):
    __tablename__ = "annotations"
    id = Column(Integer, primary_key=True)
    public_id = Column(
        String(64), default=lambda: str(uuid4()), unique=True, nullable=False
    )
    document_id = Column(
        Integer, ForeignKey("documents.id"), nullable=False, index=True
    )
    source_unit_id = Column(Integer, ForeignKey("source_units.id"), nullable=True)
    mention_id = Column(Integer, ForeignKey("entity_mentions.id"), nullable=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=True)
    evidence_ids = Column(JSON, nullable=False, default=list)
    fields = Column(JSON, nullable=False, default=dict)
    field_states = Column(JSON, nullable=False, default=dict)
    entity_links = Column(JSON, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default="pending", index=True)
    version = Column(Integer, nullable=False, default=1)
    extraction_run_id = Column(Integer, ForeignKey("extraction_runs.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AnnotationReview(Base):
    __tablename__ = "annotation_reviews"
    id = Column(Integer, primary_key=True)
    annotation_id = Column(
        Integer, ForeignKey("annotations.id"), nullable=False, index=True
    )
    version = Column(Integer, nullable=False)
    field = Column(String(100), nullable=False)
    decision = Column(String(32), nullable=False)
    previous_value = Column(JSON, nullable=True)
    value = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)
    reviewer = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class LegacyMapping(Base):
    __tablename__ = "legacy_knowledge_map"
    __table_args__ = (UniqueConstraint("source_table", "old_id"),)
    id = Column(Integer, primary_key=True)
    source_table = Column(String(100), nullable=False)
    old_id = Column(Integer, nullable=False)
    target_table = Column(String(100), nullable=True)
    new_id = Column(Integer, nullable=True)
    payload = Column(JSON, nullable=False)


class ResearchCorpus(Base):
    __tablename__ = "research_corpora"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    metadata_json = Column(JSON, default=dict)


class CorpusMembership(Base):
    __tablename__ = "corpus_memberships"
    __table_args__ = (UniqueConstraint("document_id"),)
    id = Column(Integer, primary_key=True)
    corpus_id = Column(Integer, ForeignKey("research_corpora.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    metadata_json = Column(JSON, default=dict)


class ExtractionLease(Base):
    """One durable idempotency key for each requested extraction batch."""

    __tablename__ = "extraction_leases"
    key = Column(String(64), primary_key=True)
    run_id = Column(
        Integer, ForeignKey("extraction_runs.id"), nullable=False, unique=True
    )
