"""Tasks module exports."""
from app.tasks.celery_app import celery_app
from app.tasks.ocr_tasks import run_ocr_task, run_ocr_page_task
from app.tasks.gpt_tasks import polish_block_task, polish_page_task, polish_document_task

__all__ = [
    "celery_app",
    "run_ocr_task",
    "run_ocr_page_task",
    "polish_block_task",
    "polish_page_task",
    "polish_document_task",
]
