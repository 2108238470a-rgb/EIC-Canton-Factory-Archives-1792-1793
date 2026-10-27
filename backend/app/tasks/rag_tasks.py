"""Celery tasks for the RAG index."""

import asyncio
from typing import Dict, Optional

from app.database import SessionLocal
from app.rag.indexer import RagIndexer
from app.tasks.celery_app import celery_app


@celery_app.task(bind=True, name="tasks.build_rag_index")
def build_rag_index_task(
    self, document_id: Optional[int] = None, document_ids: Optional[list[int]] = None
) -> Dict[str, int]:
    """Embed new or changed OCR blocks, reporting progress as task state."""
    db = SessionLocal()

    def report(done: int, total: int) -> None:
        self.update_state(state="PROGRESS", meta={"done": done, "total": total})

    try:
        # Old queued single-document/all-document jobs retain their original contract.
        if document_ids is None:
            return asyncio.run(RagIndexer(db).index(document_id, report))
        totals = {"indexed": 0, "total": 0, "vector_failed": 0}
        ids = list(dict.fromkeys(document_ids))
        for position, selected_id in enumerate(ids):

            def document_report(done, total):
                self.update_state(
                    state="PROGRESS",
                    meta={
                        "done": done,
                        "total": total,
                        "document_id": selected_id,
                        "documents_done": position,
                        "documents_total": len(ids),
                    },
                )

            result = asyncio.run(RagIndexer(db).index(selected_id, document_report))
            for key in totals:
                totals[key] += result.get(key, 0)
        return {**totals, "documents_done": len(ids), "documents_total": len(ids)}
    finally:
        db.close()
