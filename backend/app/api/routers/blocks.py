"""Block API routes."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories import BlockRepository, TaskRepository, PageRepository
from app.schemas import BlockResponse, BlockUpdate, TaskResponse, RunPolishRequest
from app.schemas.task import TaskCreate
from app.models import TaskType
from app.tasks import polish_block_task, polish_page_task, polish_document_task
from app.core import logger

router = APIRouter(prefix="/blocks", tags=["blocks"])


def _validate_page_modes(request: RunPolishRequest) -> None:
    """Require strict OCR correction for page and document tasks."""
    if request.modes != ["ocr_correction"]:
        raise HTTPException(
            status_code=422,
            detail="Page and document polish support only ocr_correction mode",
        )


@router.get("/{block_id}", response_model=BlockResponse)
def get_block(
    block_id: int,
    db: Session = Depends(get_db),
):
    """Get block details."""
    block_repo = BlockRepository(db)
    block = block_repo.get_by_id(block_id)
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    return block


@router.patch("/{block_id}", response_model=BlockResponse)
def update_block(
    block_id: int,
    data: BlockUpdate,
    db: Session = Depends(get_db),
):
    """Update block fields."""
    block_repo = BlockRepository(db)
    block = block_repo.update(block_id, data)
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    return block


@router.post("/{block_id}/run-polish", response_model=TaskResponse)
def run_polish_block(
    block_id: int,
    request: RunPolishRequest = RunPolishRequest(),
    db: Session = Depends(get_db),
):
    """Run GPT polish on a single block."""
    block_repo = BlockRepository(db)
    block = block_repo.get_by_id(block_id)
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")

    if not block.ocr_text_raw:
        raise HTTPException(status_code=400, detail="Block has no OCR text")

    # Create task
    task_repo = TaskRepository(db)
    task_data = TaskCreate(
        block_id=block_id,
        page_id=block.page_id,
        task_type=TaskType.OCR_CORRECTION,
    )
    task = task_repo.create(task_data)

    # Start Celery task
    celery_task = polish_block_task.delay(
        task_id=task.id,
        block_id=block_id,
        modes=request.modes,
    )
    task_repo.set_celery_id(task.id, celery_task.id)

    return task_repo.get_by_id(task.id)


# Page-level polish endpoint
@router.post("/pages/{page_id}/run-polish", response_model=TaskResponse)
def run_polish_page(
    page_id: int,
    request: RunPolishRequest = RunPolishRequest(),
    db: Session = Depends(get_db),
):
    """Run GPT polish on all blocks in a page."""
    _validate_page_modes(request)
    page_repo = PageRepository(db)
    page = page_repo.get_by_id(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    # Create task
    task_repo = TaskRepository(db)
    task_data = TaskCreate(
        page_id=page_id,
        document_id=page.document_id,
        task_type=TaskType.OCR_CORRECTION,
    )
    task = task_repo.create(task_data)

    # Start Celery task
    celery_task = polish_page_task.delay(
        task_id=task.id,
        page_id=page_id,
        modes=request.modes,
    )
    task_repo.set_celery_id(task.id, celery_task.id)

    return task_repo.get_by_id(task.id)


# Document-level polish endpoint
@router.post("/documents/{document_id}/run-polish", response_model=TaskResponse)
def run_polish_document(
    document_id: int,
    request: RunPolishRequest = RunPolishRequest(),
    db: Session = Depends(get_db),
):
    """Run GPT polish on all blocks in a document."""
    from app.services import DocumentService

    _validate_page_modes(request)
    service = DocumentService(db)
    document = service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Create task
    task_repo = TaskRepository(db)
    task_data = TaskCreate(
        document_id=document_id,
        task_type=TaskType.OCR_CORRECTION,
    )
    task = task_repo.create(task_data)

    # Start Celery task
    celery_task = polish_document_task.delay(
        task_id=task.id,
        document_id=document_id,
        modes=request.modes,
    )
    task_repo.set_celery_id(task.id, celery_task.id)

    return task_repo.get_by_id(task.id)
