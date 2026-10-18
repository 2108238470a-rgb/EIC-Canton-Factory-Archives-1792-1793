"""Entity, mention, and identity routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.knowledge.schemas import (
    EntityCreate,
    EntityDossierResponse,
    EntityMentionCreate,
    EntityMentionResponse,
    EntityNameCreate,
    EntityNameResponse,
    EntityResponse,
    EntityUpdate,
    IdentityDecisionCreate,
    IdentityDecisionResponse,
    IdentityDecisionRevoke,
    ListResponse,
    PersonRoleCreate,
    PersonRoleResponse,
)
from app.knowledge.services import EntityService

router = APIRouter(tags=["knowledge-entities"])


@router.post("/entities", response_model=EntityResponse)
def create_entity(data: EntityCreate, db: Session = Depends(get_db)) -> EntityResponse:
    """Create a canonical entity."""
    return EntityService(db).create_entity(data)


@router.get("/entities", response_model=ListResponse[EntityResponse])
def list_entities(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: Optional[str] = None,
    db: Session = Depends(get_db),
) -> ListResponse[EntityResponse]:
    """List canonical entities."""
    items, total = EntityService(db).list_entities(page, page_size, query=q)
    return ListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/entities/{entity_id}", response_model=EntityDossierResponse)
def get_entity(entity_id: int, db: Session = Depends(get_db)) -> EntityDossierResponse:
    """Get an entity dossier with mentions and identity history."""
    return EntityService(db).dossier(entity_id)


@router.patch("/entities/{entity_id}", response_model=EntityResponse)
def update_entity(
    entity_id: int,
    data: EntityUpdate,
    db: Session = Depends(get_db),
) -> EntityResponse:
    """Update canonical entity metadata."""
    return EntityService(db).update_entity(entity_id, data)


@router.post("/entities/{entity_id}/names", response_model=EntityNameResponse)
def add_entity_name(
    entity_id: int,
    data: EntityNameCreate,
    db: Session = Depends(get_db),
) -> EntityNameResponse:
    """Add an alias or original spelling."""
    return EntityService(db).add_name(entity_id, data)


@router.post("/entities/{entity_id}/roles", response_model=PersonRoleResponse)
def add_person_role(
    entity_id: int,
    data: PersonRoleCreate,
    db: Session = Depends(get_db),
) -> PersonRoleResponse:
    """Add a time-bounded office."""
    return EntityService(db).add_role(entity_id, data)


@router.post("/mentions", response_model=EntityMentionResponse)
def create_mention(
    data: EntityMentionCreate,
    db: Session = Depends(get_db),
) -> EntityMentionResponse:
    """Create an entity mention on an evidence span."""
    return EntityService(db).create_mention(data)


@router.get("/mentions", response_model=ListResponse[EntityMentionResponse])
def list_mentions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unresolved_only: bool = False,
    entity_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> ListResponse[EntityMentionResponse]:
    """List mentions."""
    items, total = EntityService(db).list_mentions(
        page,
        page_size,
        unresolved_only=unresolved_only,
        entity_id=entity_id,
    )
    return ListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/identity-decisions", response_model=IdentityDecisionResponse)
def create_identity_decision(
    data: IdentityDecisionCreate,
    db: Session = Depends(get_db),
) -> IdentityDecisionResponse:
    """Link or unlink a mention. Previous decisions are revoked, not deleted."""
    return EntityService(db).decide_identity(data)


@router.post("/identity-decisions/{decision_id}/revoke", response_model=IdentityDecisionResponse)
def revoke_identity_decision(
    decision_id: int,
    data: IdentityDecisionRevoke,
    db: Session = Depends(get_db),
) -> IdentityDecisionResponse:
    """Revoke an identity decision."""
    return EntityService(db).revoke_decision(decision_id, data)
