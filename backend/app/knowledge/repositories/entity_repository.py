"""Entity, mention, and identity persistence."""
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.knowledge.models import CanonicalEntity, EntityMention, EntityName, IdentityDecision, PersonRole


class EntityRepository:
    """Repository for canonical entities and identity judgements."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_entity(self, entity: CanonicalEntity, canonical_name: EntityName) -> CanonicalEntity:
        """Persist an entity and its seed canonical name.

        Args:
            entity: Canonical entity row.
            canonical_name: Matching name row to insert in the same transaction.

        Returns:
            Persisted entity with names loaded.
        """
        self.db.add(entity)
        self.db.flush()
        canonical_name.entity_id = entity.id
        self.db.add(canonical_name)
        self.db.commit()
        loaded = self.get_entity(entity.id)
        if loaded is None:
            raise RuntimeError("Failed to reload canonical entity after insert")
        return loaded

    def add_name(self, name: EntityName) -> EntityName:
        """Persist an additional name."""
        self.db.add(name)
        self.db.commit()
        self.db.refresh(name)
        return name

    def get_entity(self, entity_id: int) -> Optional[CanonicalEntity]:
        """Load entity with names and roles."""
        return (
            self.db.query(CanonicalEntity)
            .options(joinedload(CanonicalEntity.names), joinedload(CanonicalEntity.roles))
            .filter(CanonicalEntity.id == entity_id)
            .first()
        )

    def list_entities(self, skip: int = 0, limit: int = 20, query: Optional[str] = None) -> List[CanonicalEntity]:
        """List or search entities by name."""
        q = self.db.query(CanonicalEntity).options(joinedload(CanonicalEntity.names))
        if query:
            pattern = f"%{query}%"
            q = q.outerjoin(EntityName).filter(
                or_(
                    CanonicalEntity.canonical_name.ilike(pattern),
                    EntityName.name.ilike(pattern),
                )
            ).distinct()
        return q.order_by(CanonicalEntity.canonical_name).offset(skip).limit(limit).all()

    def count_entities(self) -> int:
        """Count canonical entities."""
        return self.db.query(CanonicalEntity).count()

    def update_entity(self, entity: CanonicalEntity) -> CanonicalEntity:
        """Commit entity attribute changes."""
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def create_mention(self, mention: EntityMention) -> EntityMention:
        """Persist a mention."""
        self.db.add(mention)
        self.db.commit()
        self.db.refresh(mention)
        return mention

    def get_mention(self, mention_id: int) -> Optional[EntityMention]:
        """Load a mention."""
        return self.db.query(EntityMention).filter(EntityMention.id == mention_id).first()

    def list_mentions(
        self,
        skip: int = 0,
        limit: int = 20,
        unresolved_only: bool = False,
        entity_id: Optional[int] = None,
    ) -> List[EntityMention]:
        """List mentions, optionally unresolved or for one entity."""
        q = self.db.query(EntityMention)
        if unresolved_only:
            q = q.filter(EntityMention.current_entity_id.is_(None))
        if entity_id is not None:
            q = q.filter(EntityMention.current_entity_id == entity_id)
        return q.order_by(EntityMention.created_at.desc()).offset(skip).limit(limit).all()

    def count_mentions(self, unresolved_only: bool = False) -> int:
        """Count mentions."""
        q = self.db.query(EntityMention)
        if unresolved_only:
            q = q.filter(EntityMention.current_entity_id.is_(None))
        return q.count()

    def active_decision_for_mention(self, mention_id: int) -> Optional[IdentityDecision]:
        """Return the current non-revoked decision for a mention."""
        return (
            self.db.query(IdentityDecision)
            .filter(
                IdentityDecision.mention_id == mention_id,
                IdentityDecision.is_revoked.is_(False),
            )
            .order_by(IdentityDecision.created_at.desc())
            .first()
        )

    def list_decisions_for_entity(self, entity_id: int) -> List[IdentityDecision]:
        """List identity decisions that reference an entity."""
        return (
            self.db.query(IdentityDecision)
            .filter(IdentityDecision.entity_id == entity_id)
            .order_by(IdentityDecision.created_at.desc())
            .all()
        )

    def add_decision(self, decision: IdentityDecision) -> IdentityDecision:
        """Persist an identity decision."""
        self.db.add(decision)
        self.db.commit()
        self.db.refresh(decision)
        return decision

    def add_role(self, role: PersonRole) -> PersonRole:
        """Persist a person role."""
        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)
        return role

    def search_mentions(self, query: str, limit: int = 20) -> List[EntityMention]:
        """Search mention surface forms."""
        return (
            self.db.query(EntityMention)
            .filter(EntityMention.mention_text.ilike(f"%{query}%"))
            .order_by(EntityMention.created_at.desc())
            .limit(limit)
            .all()
        )
