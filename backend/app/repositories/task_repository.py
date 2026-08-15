"""Task repository."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Task, TaskType, TaskStatus
from app.schemas import TaskCreate, TaskUpdate


class TaskRepository:
    """Repository for task operations."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, data: TaskCreate) -> Task:
        """Create a new task."""
        task = Task(**data.model_dump())
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def get_by_id(self, task_id: int) -> Optional[Task]:
        """Get task by ID."""
        return self.db.query(Task).filter(Task.id == task_id).first()

    def get_by_celery_id(self, celery_task_id: str) -> Optional[Task]:
        """Get task by Celery task ID."""
        return self.db.query(Task).filter(Task.celery_task_id == celery_task_id).first()

    def get_by_document(self, document_id: int, task_type: Optional[TaskType] = None) -> List[Task]:
        """Get tasks for a document."""
        query = self.db.query(Task).filter(Task.document_id == document_id)
        if task_type:
            query = query.filter(Task.task_type == task_type)
        return query.order_by(Task.created_at.desc()).all()

    def get_latest_by_document(self, document_id: int, task_type: TaskType) -> Optional[Task]:
        """Get latest task for a document by type."""
        return (
            self.db.query(Task)
            .filter(Task.document_id == document_id, Task.task_type == task_type)
            .order_by(Task.created_at.desc())
            .first()
        )

    def update(self, task_id: int, data: TaskUpdate) -> Optional[Task]:
        """Update task."""
        task = self.get_by_id(task_id)
        if not task:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(task, field, value)

        self.db.commit()
        self.db.refresh(task)
        return task

    def update_status(
        self,
        task_id: int,
        status: TaskStatus,
        progress: Optional[int] = None,
        error_message: Optional[str] = None,
        result: Optional[dict] = None
    ) -> Optional[Task]:
        """Update task status."""
        task = self.get_by_id(task_id)
        if not task:
            return None

        task.status = status
        if progress is not None:
            task.progress = progress
        if error_message:
            task.error_message = error_message
        if result:
            task.result = result

        if status == TaskStatus.RUNNING and not task.started_at:
            task.started_at = datetime.utcnow()
        elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            task.completed_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(task)
        return task

    def set_celery_id(self, task_id: int, celery_task_id: str) -> Optional[Task]:
        """Set Celery task ID."""
        task = self.get_by_id(task_id)
        if not task:
            return None

        task.celery_task_id = celery_task_id
        self.db.commit()
        self.db.refresh(task)
        return task
