"""ORM models for the knowledge module.

Importing this package registers tables on the shared SQLAlchemy Base.
"""

from app.knowledge.models.assertion import Assertion, AssertionEvidence, ReviewDecision
from app.knowledge.models.corpus import Corpus, CorpusDocumentRecord
from app.knowledge.models.entity import (
    CanonicalEntity,
    EntityMention,
    EntityName,
    IdentityDecision,
    PersonRole,
)
from app.knowledge.models.event import EventMention, EventParticipant, HistoricalEvent
from app.knowledge.models.evidence import EvidenceSpan

__all__ = [
    "Assertion",
    "AssertionEvidence",
    "CanonicalEntity",
    "Corpus",
    "CorpusDocumentRecord",
    "EntityMention",
    "EntityName",
    "EventMention",
    "EventParticipant",
    "EvidenceSpan",
    "HistoricalEvent",
    "IdentityDecision",
    "PersonRole",
    "ReviewDecision",
]
