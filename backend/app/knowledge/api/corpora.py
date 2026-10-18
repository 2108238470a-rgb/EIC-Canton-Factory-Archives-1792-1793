"""Corpus routes."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.knowledge.schemas import (
    CorpusCreate,
    CorpusDocumentAttach,
    CorpusDocumentRecordResponse,
    CorpusResponse,
    CorpusUpdate,
    ListResponse,
)
from app.knowledge.services import CorpusService

router = APIRouter(prefix="/corpora", tags=["knowledge-corpora"])


@router.post("", response_model=CorpusResponse)
def create_corpus(data: CorpusCreate, db: Session = Depends(get_db)) -> CorpusResponse:
    """Create a corpus."""
    return CorpusService(db).create(data)


@router.get("", response_model=ListResponse[CorpusResponse])
def list_corpora(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ListResponse[CorpusResponse]:
    """List corpora."""
    items, total = CorpusService(db).list(page, page_size)
    return ListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{corpus_id}", response_model=CorpusResponse)
def get_corpus(corpus_id: int, db: Session = Depends(get_db)) -> CorpusResponse:
    """Get one corpus."""
    return CorpusService(db).get(corpus_id)


@router.patch("/{corpus_id}", response_model=CorpusResponse)
def update_corpus(
    corpus_id: int,
    data: CorpusUpdate,
    db: Session = Depends(get_db),
) -> CorpusResponse:
    """Update corpus metadata."""
    return CorpusService(db).update(corpus_id, data)


@router.post("/{corpus_id}/documents", response_model=CorpusDocumentRecordResponse)
def attach_document(
    corpus_id: int,
    data: CorpusDocumentAttach,
    db: Session = Depends(get_db),
) -> CorpusDocumentRecordResponse:
    """Attach an existing OCR document to a corpus."""
    return CorpusService(db).attach_document(corpus_id, data)
