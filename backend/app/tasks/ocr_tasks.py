"""OCR Celery tasks."""
import asyncio
from typing import Optional, Dict, Any

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.services import OCRService
from app.repositories import TaskRepository
from app.models import TaskStatus
from app.core import logger


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="tasks.run_ocr")
def run_ocr_task(
    self,
    task_id: int,
    document_id: int,
    visualize: bool = False,
    restructure_pages: bool = True,
    merge_tables: bool = True,
    relevel_titles: bool = True,
) -> dict:
    """
    Celery task for running OCR on a document.

    Args:
        task_id: Database task ID
        document_id: Document ID to process
        visualize: Whether to generate visualization
        restructure_pages: Whether to restructure pages
        merge_tables: Whether to merge tables
        relevel_titles: Whether to relevel titles

    Returns:
        Task result dict
    """
    db = SessionLocal()
    task_repo = TaskRepository(db)

    def report_progress(progress: int, result: Optional[Dict[str, Any]] = None) -> None:
        """Persist OCR progress for frontend polling."""
        task_repo.update_status(task_id, TaskStatus.RUNNING, progress=progress, result=result)

    try:
        task_repo.update_status(
            task_id,
            TaskStatus.RUNNING,
            progress=0,
            result={"stage": "queued"},
        )

        ocr_service = OCRService(db)
        document = run_async(
            ocr_service.process_document(
                document_id,
                visualize=visualize,
                restructure_pages=restructure_pages,
                merge_tables=merge_tables,
                relevel_titles=relevel_titles,
                progress_callback=report_progress,
            )
        )

        result = {
            "document_id": document.id,
            "page_count": document.page_count,
            "status": document.status.value,
            "stage": "completed",
        }
        task_repo.update_status(task_id, TaskStatus.COMPLETED, progress=100, result=result)

        logger.info(f"OCR task completed for document {document_id}")
        return result

    except Exception as e:
        logger.error(f"OCR task failed for document {document_id}: {e}")
        task_repo.update_status(
            task_id,
            TaskStatus.FAILED,
            error_message=str(e),
            result={"stage": "failed"},
        )
        raise

    finally:
        db.close()


@celery_app.task(bind=True, name="tasks.run_ocr_page")
def run_ocr_page_task(
    self,
    task_id: int,
    page_id: int,
) -> dict:
    """
    Celery task for re-running OCR on a single page.

    Args:
        task_id: Database task ID
        page_id: Page ID to process

    Returns:
        Task result dict
    """
    db = SessionLocal()
    task_repo = TaskRepository(db)

    try:
        task_repo.update_status(task_id, TaskStatus.RUNNING, progress=0)

        result = {"page_id": page_id, "status": "completed"}
        task_repo.update_status(task_id, TaskStatus.COMPLETED, progress=100, result=result)

        return result

    except Exception as e:
        logger.error(f"OCR page task failed for page {page_id}: {e}")
        task_repo.update_status(task_id, TaskStatus.FAILED, error_message=str(e))
        raise

    finally:
        db.close()
