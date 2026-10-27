"""Entity model for persons, organizations, and places."""
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, String, DateTime, Text, Enum, Index
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.entity_mention import EntityMention
    from app.models.identity_decision import IdentityDecision
    from app.models.participation import Participation
    from app.models.assertion import Assertion


class EntityType(str, enum.Enum):
    """Type of entity."""
    OTHER = "other"
    ROLE = "role"
    PERSON = "person"
    ORGANIZATION = "organization"
    PLACE = "place"
    SHIP = "ship"  # Phase 2
    COMMODITY = "commodity"  # Phase 2


class Entity(Base):
    """
    Entity representing a real-world person, organization, or place.

    Uses stable IDs and canonical names for identity resolution.
    """

    __tablename__ = "entities"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)

    # Core identification
    entity_type = Column(Enum(EntityType, native_enum=False), nullable=False, index=True, comment="实体类型")
    canonical_name = Column(String(500), nullable=False, index=True, comment="规范名称")
    canonical_name_zh = Column(String(500), nullable=True, comment="中文规范名称")

    # Alternative names and identifiers
    alternative_names = Column(Text, nullable=True, comment="备选名称（JSON数组）")
    external_id = Column(String(255), nullable=True, index=True, comment="外部标识符")

    # Description
    description = Column(Text, nullable=True, comment="描述")
    notes = Column(Text, nullable=True, comment="备注")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    mentions = relationship("app.models.entity_mention.EntityMention", back_populates="entity")
    identity_decisions = relationship("app.models.identity_decision.IdentityDecision", back_populates="entity")
    participations = relationship("Participation", back_populates="entity")
    assertions_as_subject = relationship(
        "app.models.assertion.Assertion",
        foreign_keys="app.models.assertion.Assertion.subject_entity_id",
        back_populates="subject_entity",
    )
    assertions_as_object = relationship(
        "app.models.assertion.Assertion",
        foreign_keys="app.models.assertion.Assertion.object_entity_id",
        back_populates="object_entity",
    )

    # Indexes
    __table_args__ = (
        Index('ix_entities_type_canonical_name', 'entity_type', 'canonical_name'),
    )

    def __repr__(self) -> str:
        return f"<Entity(id={self.id}, type={self.entity_type}, name={self.canonical_name})>"
