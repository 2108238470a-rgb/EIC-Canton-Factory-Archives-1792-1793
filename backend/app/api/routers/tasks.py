"""Task API routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories import TaskRepository
from app.schemas import TaskResponse
from app.core import logger

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    """Get task status and details."""
    task_repo = TaskRepository(db)
    task = task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/celery/{celery_task_id}", response_model=TaskResponse)
def get_task_by_celery_id(
    celery_task_id: str,
    db: Session = Depends(get_db),
):
    """Get task by Celery task ID."""
    task_repo = TaskRepository(db)
    task = task_repo.get_by_celery_id(celery_task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
