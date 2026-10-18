"""Entity, mention, and identity application service."""
from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.knowledge.enums import IdentityDecisionType, NameType
from app.knowledge.models import CanonicalEntity, EntityMention, EntityName, IdentityDecision, PersonRole
from app.knowledge.repositories import EntityRepository, EvidenceRepository
from app.knowledge.schemas import (
    EntityCreate,
    EntityDossierResponse,
    EntityMentionCreate,
    EntityMentionResponse,
    EntityNameCreate,
    EntityResponse,
    EntityUpdate,
    IdentityDecisionCreate,
    IdentityDecisionResponse,
    IdentityDecisionRevoke,
    PersonRoleCreate,
    PersonRoleResponse,
)


class EntityService:
    """Manage mentions, canonical entities, and reversible identity decisions."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = EntityRepository(db)
        self.evidence_repo = EvidenceRepository(db)

    def create_entity(self, data: EntityCreate) -> CanonicalEntity:
        """Create a canonical entity and seed its canonical name."""
        entity = CanonicalEntity(**data.model_dump())
        name = EntityName(name=data.canonical_name, name_type=NameType.CANONICAL)
        return self.repo.create_entity(entity, name)

    def list_entities(self, page: int, page_size: int, query: Optional[str] = None) -> Tuple[List[CanonicalEntity], int]:
        """List entities."""
        items = self.repo.list_entities(skip=(page - 1) * page_size, limit=page_size, query=query)
        return items, self.repo.count_entities()

    def get_entity(self, entity_id: int) -> CanonicalEntity:
        """Load an entity."""
        entity = self.repo.get_entity(entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        return entity

    def update_entity(self, entity_id: int, data: EntityUpdate) -> CanonicalEntity:
        """Patch an entity."""
        entity = self.get_entity(entity_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(entity, field, value)
        return self.repo.update_entity(entity)

    def add_name(self, entity_id: int, data: EntityNameCreate) -> EntityName:
        """Add a name variant."""
        self.get_entity(entity_id)
        return self.repo.add_name(EntityName(entity_id=entity_id, **data.model_dump()))

    def create_mention(self, data: EntityMentionCreate) -> EntityMention:
        """Create a mention whose offsets lie inside an evidence span."""
        span = self.evidence_repo.get_by_id(data.evidence_span_id)
        if not span:
            raise HTTPException(status_code=404, detail="Evidence span not found")
        excerpt_len = len(span.excerpt)
        if data.char_start >= data.char_end or data.char_end > excerpt_len:
            raise HTTPException(
                status_code=400,
                detail="Mention offsets must lie inside the evidence excerpt",
            )
        excerpt_slice = span.excerpt[data.char_start:data.char_end]
        if excerpt_slice != data.mention_text:
            raise HTTPException(
                status_code=400,
                detail="mention_text must equal the evidence excerpt slice",
            )
        mention = EntityMention(**data.model_dump())
        return self.repo.create_mention(mention)

    def list_mentions(
        self,
        page: int,
        page_size: int,
        unresolved_only: bool = False,
        entity_id: Optional[int] = None,
    ) -> Tuple[List[EntityMention], int]:
        """List mentions."""
        items = self.repo.list_mentions(
            skip=(page - 1) * page_size,
            limit=page_size,
            unresolved_only=unresolved_only,
            entity_id=entity_id,
        )
        return items, self.repo.count_mentions(unresolved_only=unresolved_only)

    def decide_identity(self, data: IdentityDecisionCreate) -> IdentityDecision:
        """Record a link/unlink/uncertain decision and update the mention cache.

        Args:
            data: Decision payload.

        Returns:
            New identity decision. Previous active decisions are revoked, not deleted.
        """
        mention = self.repo.get_mention(data.mention_id)
        if not mention:
            raise HTTPException(status_code=404, detail="Mention not found")
        if data.decision in {IdentityDecisionType.LINK, IdentityDecisionType.UNCERTAIN}:
            if data.entity_id is None:
                raise HTTPException(status_code=400, detail="entity_id is required for link/uncertain decisions")
            if not self.repo.get_entity(data.entity_id):
                raise HTTPException(status_code=404, detail="Entity not found")
        if data.decision == IdentityDecisionType.UNLINK and data.entity_id is None:
            data = data.model_copy(update={"entity_id": mention.current_entity_id})

        previous = self.repo.active_decision_for_mention(mention.id)
        if previous:
            previous.is_revoked = True
            previous.revoked_at = datetime.utcnow()
            previous.revoked_reason = "superseded_by_new_decision"

        decision = IdentityDecision(
            mention_id=mention.id,
            entity_id=data.entity_id,
            decision=data.decision,
            rationale=data.rationale,
            decided_by=data.decided_by,
            previous_decision_id=previous.id if previous else None,
        )
        if data.decision == IdentityDecisionType.LINK:
            mention.current_entity_id = data.entity_id
        elif data.decision == IdentityDecisionType.UNLINK:
            mention.current_entity_id = None
        return self.repo.add_decision(decision)

    def revoke_decision(self, decision_id: int, data: IdentityDecisionRevoke) -> IdentityDecision:
        """Revoke a decision and restore the mention cache from remaining history."""
        decision = (
            self.db.query(IdentityDecision).filter(IdentityDecision.id == decision_id).first()
        )
        if not decision:
            raise HTTPException(status_code=404, detail="Identity decision not found")
        if decision.is_revoked:
            raise HTTPException(status_code=409, detail="Identity decision already revoked")
        decision.is_revoked = True
        decision.revoked_at = datetime.utcnow()
        decision.revoked_reason = data.reason
        self.db.flush()
        mention = self.repo.get_mention(decision.mention_id)
        if mention:
            remaining = self.repo.active_decision_for_mention(mention.id)
            if remaining and remaining.decision == IdentityDecisionType.LINK:
                mention.current_entity_id = remaining.entity_id
            else:
                mention.current_entity_id = None
        self.db.commit()
        self.db.refresh(decision)
        return decision

    def add_role(self, entity_id: int, data: PersonRoleCreate) -> PersonRole:
        """Add a time-bounded office to a person entity."""
        entity = self.get_entity(entity_id)
        if data.organization_entity_id is not None and not self.repo.get_entity(data.organization_entity_id):
            raise HTTPException(status_code=404, detail="Organization entity not found")
        if data.evidence_span_id is not None and not self.evidence_repo.get_by_id(data.evidence_span_id):
            raise HTTPException(status_code=404, detail="Evidence span not found")
        role = PersonRole(person_entity_id=entity.id, **data.model_dump())
        return self.repo.add_role(role)

    def dossier(self, entity_id: int) -> EntityDossierResponse:
        """Assemble the entity workbench page."""
        entity = self.get_entity(entity_id)
        mentions, _ = self.list_mentions(page=1, page_size=100, entity_id=entity_id)
        decisions = self.repo.list_decisions_for_entity(entity_id)
        base = EntityResponse.model_validate(entity)
        return EntityDossierResponse(
            **base.model_dump(),
            mentions=[EntityMentionResponse.model_validate(item) for item in mentions],
            roles=[PersonRoleResponse.model_validate(item) for item in entity.roles],
            identity_decisions=[
                IdentityDecisionResponse.model_validate(item) for item in decisions
            ],
        )
