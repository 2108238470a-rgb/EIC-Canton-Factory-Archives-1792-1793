"""Entity mention, canonical entity, and identity decision models."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.knowledge.enums import (
    DisambiguationStatus,
    EntityType,
    ExtractionSource,
    IdentityDecisionType,
    MentionType,
    NameType,
    RoleTenureType,
    sa_enum,
)


class CanonicalEntity(Base):
    """A researcher-current historical subject, distinct from any mention."""

    __tablename__ = "knowledge_entities"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(sa_enum(EntityType), nullable=False, index=True)
    canonical_name = Column(String(512), nullable=False, index=True)
    notes = Column(Text, nullable=True)
    external_id = Column(String(255), nullable=True)
    activity_start = Column(String(64), nullable=True)
    activity_end = Column(String(64), nullable=True)
    place_note = Column(String(255), nullable=True)
    disambiguation_status = Column(
        sa_enum(DisambiguationStatus),
        nullable=False,
        default=DisambiguationStatus.UNRESOLVED,
    )
    is_inferred = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    names = relationship("EntityName", back_populates="entity", cascade="all, delete-orphan")
    roles = relationship(
        "PersonRole",
        back_populates="person",
        foreign_keys="PersonRole.person_entity_id",
        cascade="all, delete-orphan",
    )


class EntityName(Base):
    """One attested or normalized name for a canonical entity."""

    __tablename__ = "knowledge_entity_names"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(Integer, ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(512), nullable=False, index=True)
    name_type = Column(sa_enum(NameType), nullable=False, default=NameType.ALIAS)
    language = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    entity = relationship("CanonicalEntity", back_populates="names")


class EntityMention(Base):
    """One occurrence of a name in an evidence span."""

    __tablename__ = "knowledge_entity_mentions"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    evidence_span_id = Column(
        Integer,
        ForeignKey("knowledge_evidence_spans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    mention_text = Column(String(512), nullable=False)
    mention_type = Column(sa_enum(MentionType), nullable=False, index=True)
    char_start = Column(Integer, nullable=False)
    char_end = Column(Integer, nullable=False)
    current_entity_id = Column(
        Integer,
        ForeignKey("knowledge_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    extraction_source = Column(sa_enum(ExtractionSource), nullable=False, default=ExtractionSource.HUMAN)
    model_name = Column(String(128), nullable=True)
    model_version = Column(String(64), nullable=True)
    created_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    evidence_span = relationship("app.knowledge.models.evidence.EvidenceSpan")
    current_entity = relationship("CanonicalEntity")
    identity_decisions = relationship("app.knowledge.models.entity.IdentityDecision", back_populates="mention")


class IdentityDecision(Base):
    """Auditable link, unlink, or uncertain judgement. Merges are reversible."""

    __tablename__ = "knowledge_identity_decisions"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    mention_id = Column(
        Integer,
        ForeignKey("knowledge_entity_mentions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id = Column(
        Integer,
        ForeignKey("knowledge_entities.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    decision = Column(sa_enum(IdentityDecisionType), nullable=False)
    rationale = Column(Text, nullable=True)
    decided_by = Column(String(128), nullable=True)
    is_revoked = Column(Boolean, nullable=False, default=False)
    revoked_at = Column(DateTime, nullable=True)
    revoked_reason = Column(Text, nullable=True)
    previous_decision_id = Column(
        Integer,
        ForeignKey("knowledge_identity_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    mention = relationship("app.knowledge.models.entity.EntityMention", back_populates="identity_decisions")
    entity = relationship("CanonicalEntity")


class PersonRole(Base):
    """Time-bounded office of a person in an organization."""

    __tablename__ = "knowledge_person_roles"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    person_entity_id = Column(
        Integer,
        ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_entity_id = Column(
        Integer,
        ForeignKey("knowledge_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role_title = Column(String(255), nullable=False)
    tenure_type = Column(sa_enum(RoleTenureType), nullable=False, default=RoleTenureType.SUBSTANTIVE)
    start_date = Column(String(64), nullable=True)
    end_date = Column(String(64), nullable=True)
    evidence_span_id = Column(
        Integer,
        ForeignKey("knowledge_evidence_spans.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    person = relationship("CanonicalEntity", foreign_keys=[person_entity_id], back_populates="roles")
    organization = relationship("CanonicalEntity", foreign_keys=[organization_entity_id])
