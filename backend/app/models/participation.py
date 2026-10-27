"""Participation model for entity-event relationships."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.event import Event


class Participation(Base):
    """
    Entity participation in an event with a specific role.

    Links entities to events with evidence-backed assertions.
    """

    __tablename__ = "participations"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)

    # Role in event
    role = Column(String(200), nullable=False, index=True, comment="角色")
    role_description = Column(Text, nullable=True, comment="角色描述")

    # Evidence and notes
    notes = Column(Text, nullable=True, comment="备注")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    event = relationship("Event", back_populates="participations")
    entity = relationship("Entity", back_populates="participations")

    def __repr__(self) -> str:
        return f"<Participation(id={self.id}, event_id={self.event_id}, entity_id={self.entity_id}, role={self.role})>"
