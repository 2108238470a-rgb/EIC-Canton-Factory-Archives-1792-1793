"""Knowledge API v2 router."""
from fastapi import APIRouter

from app.knowledge.api.assertions import router as assertions_router
from app.knowledge.api.corpora import router as corpora_router
from app.knowledge.api.entities import router as entities_router
from app.knowledge.api.events import router as events_router
from app.knowledge.api.evidence import router as evidence_router
from app.knowledge.api.workbench import router as workbench_router

knowledge_router = APIRouter()
knowledge_router.include_router(workbench_router)
knowledge_router.include_router(corpora_router)
knowledge_router.include_router(evidence_router)
knowledge_router.include_router(entities_router)
knowledge_router.include_router(events_router)
knowledge_router.include_router(assertions_router)

__all__ = ["knowledge_router"]
