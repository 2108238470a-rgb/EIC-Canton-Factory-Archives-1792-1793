"""Workbench overview route."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.knowledge.schemas import WorkbenchOverviewResponse
from app.knowledge.services import WorkbenchService

router = APIRouter(prefix="/workbench", tags=["knowledge-workbench"])


@router.get("/overview", response_model=WorkbenchOverviewResponse)
def get_overview(db: Session = Depends(get_db)) -> WorkbenchOverviewResponse:
    """Return object counts for the knowledge workbench."""
    return WorkbenchService(db).overview()
