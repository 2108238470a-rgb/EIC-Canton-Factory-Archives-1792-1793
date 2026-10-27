"""Page API routes."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path

from app.api.deps import get_db
from app.repositories import PageRepository, BlockRepository
from app.schemas import PageResponse, PageDetailResponse
from app.core import logger

router = APIRouter(prefix="/pages", tags=["pages"])


@router.get("/{page_id}", response_model=PageDetailResponse)
def get_page(
    page_id: int,
    db: Session = Depends(get_db),
):
    """Get page details with blocks."""
    page_repo = PageRepository(db)
    page = page_repo.get_by_id(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return {
        **PageResponse.model_validate(page).model_dump(),
        "blocks": BlockRepository(db).get_by_page(page.id),
    }


@router.get("/{page_id}/blocks")
def get_page_blocks(
    page_id: int,
    db: Session = Depends(get_db),
):
    """Get all blocks for a page."""
    page_repo = PageRepository(db)
    page = page_repo.get_by_id(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    block_repo = BlockRepository(db)
    blocks = block_repo.get_by_page(page_id)
    return {"items": blocks, "total": len(blocks)}


@router.get("/{page_id}/image")
def get_page_image(
    page_id: int,
    db: Session = Depends(get_db),
):
    """Get page image file."""
    page_repo = PageRepository(db)
    page = page_repo.get_by_id(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    if not page.image_path:
        raise HTTPException(status_code=404, detail="Page image not found")

    image_path = Path(page.image_path)
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Page image file not found")

    return FileResponse(
        path=str(image_path),
        media_type="image/png",
        filename=image_path.name,
    )


@router.get("/{page_id}/visualization")
def get_page_visualization(
    page_id: int,
    db: Session = Depends(get_db),
):
    """Get page visualization image."""
    page_repo = PageRepository(db)
    page = page_repo.get_by_id(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    if not page.visualization_path:
        raise HTTPException(status_code=404, detail="Visualization not found")

    vis_path = Path(page.visualization_path)
    if not vis_path.exists():
        raise HTTPException(status_code=404, detail="Visualization file not found")

    return FileResponse(
        path=str(vis_path),
        media_type="image/png",
        filename=vis_path.name,
    )
