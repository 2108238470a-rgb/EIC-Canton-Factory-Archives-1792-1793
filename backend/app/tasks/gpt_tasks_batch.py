"""Compatibility for queued batch jobs; use the canonical per-page correction pipeline."""

from app.tasks.celery_app import celery_app
from app.tasks.gpt_tasks import polish_document_task


@celery_app.task(bind=True, name="tasks.polish_document_batch")
def polish_document_batch_task(self, task_id: int, document_id: int, modes: list[str]):
    return polish_document_task.run(
        task_id=task_id, document_id=document_id, modes=modes
    )
