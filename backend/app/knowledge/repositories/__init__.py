"""Knowledge repositories."""

from app.knowledge.repositories.assertion_repository import AssertionRepository
from app.knowledge.repositories.corpus_repository import CorpusRepository
from app.knowledge.repositories.entity_repository import EntityRepository
from app.knowledge.repositories.event_repository import EventRepository
from app.knowledge.repositories.evidence_repository import EvidenceRepository

__all__ = [
    "AssertionRepository",
    "CorpusRepository",
    "EntityRepository",
    "EventRepository",
    "EvidenceRepository",
]
