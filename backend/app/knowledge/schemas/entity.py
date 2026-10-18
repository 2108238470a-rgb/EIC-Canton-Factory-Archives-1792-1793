"""Entity, mention, and identity schemas."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.knowledge.enums import (
    DisambiguationStatus,
    EntityType,
    ExtractionSource,
    IdentityDecisionType,
    MentionType,
    NameType,
    RoleTenureType,
)
from app.knowledge.schemas.common import ORMModel


class EntityCreate(BaseModel):
    """Create a canonical entity."""

    entity_type: EntityType
    canonical_name: str = Field(..., min_length=1, max_length=512)
    notes: Optional[str] = None
    external_id: Optional[str] = None
    activity_start: Optional[str] = None
    activity_end: Optional[str] = None
    place_note: Optional[str] = None
    disambiguation_status: DisambiguationStatus = DisambiguationStatus.UNRESOLVED
    is_inferred: bool = False


class EntityUpdate(BaseModel):
    """Partial canonical entity update."""

    canonical_name: Optional[str] = Field(None, min_length=1, max_length=512)
    notes: Optional[str] = None
    external_id: Optional[str] = None
    activity_start: Optional[str] = None
    activity_end: Optional[str] = None
    place_note: Optional[str] = None
    disambiguation_status: Optional[DisambiguationStatus] = None
    is_inferred: Optional[bool] = None


class EntityNameCreate(BaseModel):
    """Add an attested or normalized name."""

    name: str = Field(..., min_length=1, max_length=512)
    name_type: NameType = NameType.ALIAS
    language: Optional[str] = None


class EntityNameResponse(ORMModel):
    """Stored entity name."""

    id: int
    entity_id: int
    name: str
    name_type: NameType
    language: Optional[str] = None
    created_at: datetime


class EntityMentionCreate(BaseModel):
    """Record a name occurrence on an evidence span."""

    evidence_span_id: int
    mention_text: str = Field(..., min_length=1, max_length=512)
    mention_type: MentionType
    char_start: int = Field(..., ge=0)
    char_end: int = Field(..., ge=0)
    extraction_source: ExtractionSource = ExtractionSource.HUMAN
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    created_by: Optional[str] = None


class EntityMentionResponse(ORMModel):
    """Stored mention."""

    id: int
    evidence_span_id: int
    mention_text: str
    mention_type: MentionType
    char_start: int
    char_end: int
    current_entity_id: Optional[int] = None
    extraction_source: ExtractionSource
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime


class IdentityDecisionCreate(BaseModel):
    """Link, unlink, or mark a mention as uncertain."""

    mention_id: int
    entity_id: Optional[int] = None
    decision: IdentityDecisionType
    rationale: Optional[str] = None
    decided_by: Optional[str] = None


class IdentityDecisionRevoke(BaseModel):
    """Revoke a previous identity decision."""

    reason: Optional[str] = None
    decided_by: Optional[str] = None


class IdentityDecisionResponse(ORMModel):
    """Stored identity decision."""

    id: int
    mention_id: int
    entity_id: Optional[int] = None
    decision: IdentityDecisionType
    rationale: Optional[str] = None
    decided_by: Optional[str] = None
    is_revoked: bool
    revoked_at: Optional[datetime] = None
    revoked_reason: Optional[str] = None
    previous_decision_id: Optional[int] = None
    created_at: datetime


class PersonRoleCreate(BaseModel):
    """Time-bounded office."""

    organization_entity_id: Optional[int] = None
    role_title: str = Field(..., min_length=1, max_length=255)
    tenure_type: RoleTenureType = RoleTenureType.SUBSTANTIVE
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    evidence_span_id: Optional[int] = None


class PersonRoleResponse(ORMModel):
    """Stored person role."""

    id: int
    person_entity_id: int
    organization_entity_id: Optional[int] = None
    role_title: str
    tenure_type: RoleTenureType
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    evidence_span_id: Optional[int] = None
    created_at: datetime


class EntityResponse(ORMModel):
    """Canonical entity with names."""

    id: int
    entity_type: EntityType
    canonical_name: str
    notes: Optional[str] = None
    external_id: Optional[str] = None
    activity_start: Optional[str] = None
    activity_end: Optional[str] = None
    place_note: Optional[str] = None
    disambiguation_status: DisambiguationStatus
    is_inferred: bool
    created_at: datetime
    updated_at: datetime
    names: List[EntityNameResponse] = []


class EntityDossierResponse(EntityResponse):
    """Entity page payload for the workbench."""

    mentions: List[EntityMentionResponse] = []
    roles: List[PersonRoleResponse] = []
    identity_decisions: List[IdentityDecisionResponse] = []
