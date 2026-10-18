"""RAG routes: index management, hybrid search, and grounded Q&A."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, defer

from app.api.deps import get_db
from app.models import (
    Document,
    DocumentType,
    Block,
    Page,
    SearchChunk,
    ChunkStatus,
    TextRevision,
    EvidenceSpan,
    CorpusMembership,
)
from app.rag.indexer import block_text, SKIP_LABELS, segments_valid
from app.rag.indexer import RagIndexer
from app.rag.qa import RagAnswerService
from app.rag.retriever import HybridRetriever
from app.rag.schemas import (
    AnswerResponseSchema,
    IndexJobSchema,
    IndexRequestSchema,
    IndexStatusSchema,
    QuestionRequestSchema,
    SearchRequestSchema,
    SearchResponseSchema,
)
from app.tasks.celery_app import celery_app
from app.tasks.rag_tasks import build_rag_index_task

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get("/status", response_model=IndexStatusSchema)
def get_index_status(
    document_id: Optional[int] = None, db: Session = Depends(get_db)
) -> IndexStatusSchema:
    """Report how many OCR blocks are indexed."""
    return RagIndexer(db).status(document_id)


@router.get("/documents")
def index_documents(db: Session = Depends(get_db)):
    """PDF inventory based on actual current OCR text, including partial OCR."""
    docs = (
        db.query(Document)
        .filter(Document.file_type == DocumentType.PDF, Document.archived_at.is_(None))
        .order_by(Document.id.desc())
        .all()
    )
    blocks = (
        db.query(Block, Page.document_id, Page.id)
        .join(Page)
        .filter(Block.retired.is_(False))
        .all()
    )
    coverage = {}
    for block, doc_id, page_id in blocks:
        if block.block_label not in SKIP_LABELS and block_text(block):
            entry = coverage.setdefault(doc_id, {"blocks": set(), "pages": set()})
            entry["blocks"].add(block.id)
            entry["pages"].add(page_id)
    indexed = {}
    chunks = (
        db.query(SearchChunk)
        .options(defer(SearchChunk.embedding))
        .filter(SearchChunk.status == ChunkStatus.INDEXED)
        .all()
    )
    # Hold references in the identity map so validity checks do not issue one
    # database query per segment. Catalog reads never create text revisions.
    revision_ids = {p["revision_id"] for c in chunks for p in c.segments}
    evidence_ids = {
        p["evidence_id"] for c in chunks for p in c.segments if p.get("evidence_id")
    }
    revisions = (
        db.query(TextRevision).filter(TextRevision.id.in_(revision_ids)).all()
        if revision_ids
        else []
    )
    evidence = (
        db.query(EvidenceSpan).filter(EvidenceSpan.id.in_(evidence_ids)).all()
        if evidence_ids
        else []
    )
    for chunk in chunks:
        if segments_valid(db, chunk):
            indexed.setdefault(chunk.document_id, set()).update(
                p["block_id"] for p in chunk.segments
            )
    memberships = {m.document_id: m.corpus_id for m in db.query(CorpusMembership)}
    return {
        "items": [
            dict(
                corpus_id=memberships.get(d.id),
                id=d.id,
                title=d.original_filename,
                page_count=d.page_count,
                ocr_pages=len(coverage[d.id]["pages"]),
                eligible=len(coverage[d.id]["blocks"]),
                indexed=len(coverage[d.id]["blocks"] & indexed.get(d.id, set())),
                status=d.status.value,
            )
            for d in docs
            if d.id in coverage
        ]
    }


@router.post("/index", response_model=IndexJobSchema, status_code=202)
def start_indexing(
    data: IndexRequestSchema, db: Session = Depends(get_db)
) -> IndexJobSchema:
    """Queue a background job that embeds new or changed blocks."""
    ids = list(
        dict.fromkeys(
            data.document_ids or ([data.document_id] if data.document_id else [])
        )
    )
    if not ids or any(i <= 0 for i in ids):
        raise HTTPException(422, "请勾选需要更新索引的 PDF")
    eligible = {
        doc_id
        for block, doc_id in db.query(Block, Page.document_id)
        .join(Page)
        .join(Document)
        .filter(
            Document.id.in_(ids),
            Document.archived_at.is_(None),
            Document.file_type == DocumentType.PDF,
            Block.retired.is_(False),
        )
        if block.block_label not in SKIP_LABELS and block_text(block)
    }
    if not set(ids).issubset(eligible):
        raise HTTPException(
            422, "所选文件不存在、不是 PDF 或尚无可索引的 OCR 文本，请刷新列表"
        )
    try:
        result = build_rag_index_task.delay(document_ids=ids)
    except Exception:
        raise HTTPException(503, "索引任务队列不可用，请稍后重试")
    return IndexJobSchema(task_id=result.id, state=result.state)


@router.get("/index/{task_id}", response_model=IndexJobSchema)
def get_indexing_job(task_id: str) -> IndexJobSchema:
    """Poll an indexing job."""
    result = celery_app.AsyncResult(task_id)
    info: Optional[Dict[str, Any]] = None
    if isinstance(result.info, dict):
        info = result.info
    elif result.failed():
        info = {"error": str(result.info)[:300]}
    return IndexJobSchema(task_id=task_id, state=result.state, info=info)


@router.post("/search", response_model=SearchResponseSchema)
async def search(
    data: SearchRequestSchema, db: Session = Depends(get_db)
) -> SearchResponseSchema:
    """Hybrid vector + keyword search over OCR blocks."""
    retriever = HybridRetriever(db)
    hits = await retriever.search(
        data.query, data.top_k, scope=data, retrieval=data.retrieval
    )
    return SearchResponseSchema(
        query=data.query,
        items=hits,
        warnings=retriever.warnings,
        scope=data.model_dump(mode="json"),
        returned=len(hits),
    )


@router.post("/questions", response_model=AnswerResponseSchema)
async def ask_question(
    data: QuestionRequestSchema, db: Session = Depends(get_db)
) -> AnswerResponseSchema:
    """Answer a question using only retrieved archive passages, with citations."""
    return await RagAnswerService(db).answer(
        data.question,
        data.top_k,
        scope=data,
        selected_ids=data.selected_chunk_ids or None,
        retrieval=data.retrieval,
        history=[turn.model_dump() for turn in data.history],
    )
