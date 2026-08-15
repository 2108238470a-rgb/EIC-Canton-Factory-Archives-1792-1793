"""Export API routes."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path

from app.api.deps import get_db
from app.services import DocumentService, ExportService
from app.schemas import ExportResponse, ExportListResponse, ExportRequest
from app.core import logger

router = APIRouter(prefix="/exports", tags=["exports"])


@router.post("/documents/{document_id}/export", response_model=ExportResponse)
def create_export(
    document_id: int,
    request: ExportRequest,
    db: Session = Depends(get_db),
):
    """Create a new export for a document."""
    doc_service = DocumentService(db)
    document = doc_service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    export_service = ExportService(db)
    try:
        export = export_service.export_document(
            document_id, request.format, text_mode=request.text_mode
        )
        return export
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{document_id}/exports", response_model=ExportListResponse)
def list_exports(
    document_id: int,
    db: Session = Depends(get_db),
):
    """List all exports for a document."""
    doc_service = DocumentService(db)
    document = doc_service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    export_service = ExportService(db)
    exports = export_service.get_exports(document_id)
    return ExportListResponse(items=exports, total=len(exports))


@router.get("/{export_id}/download")
def download_export(
    export_id: int,
    db: Session = Depends(get_db),
):
    """Download an export file."""
    from app.models import Export, ExportStatus

    export = db.query(Export).filter(Export.id == export_id).first()
    if not export:
        raise HTTPException(status_code=404, detail="Export not found")

    if export.status != ExportStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Export not ready")

    if not export.file_path:
        raise HTTPException(status_code=404, detail="Export file not found")

    file_path = Path(export.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Export file not found")

    # Determine media type
    media_types = {
        ".json": "application/json",
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    media_type = media_types.get(file_path.suffix, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_path.name,
    )
