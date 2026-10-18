"""Processing coverage from persisted text and active tasks, never inferred from OCR status."""

from sqlalchemy import func, case, or_
from app.models import Block, Page, Task, TaskType, TaskStatus


def processing_summaries(db, ids):
    if not ids:
        return {}
    text = func.coalesce(Block.ocr_text_corrected, Block.ocr_text_raw, "")
    rows = (
        db.query(
            Page.document_id,
            func.count(Block.id),
            func.sum(
                case(
                    (
                        func.length(
                            func.trim(func.coalesce(Block.ocr_text_corrected, ""))
                        )
                        > 0,
                        1,
                    ),
                    else_=0,
                )
            ),
        )
        .join(Block, Block.page_id == Page.id)
        .filter(
            Page.document_id.in_(ids),
            Block.retired.is_(False),
            func.length(func.trim(text)) > 0,
            or_(
                Block.block_label.is_(None),
                Block.block_label.notin_(
                    ["number", "image", "header_image", "footer_image", "chart"]
                ),
            ),
        )
        .group_by(Page.document_id)
        .all()
    )
    result = {
        i: {"text_blocks": 0, "polished_blocks": 0, "polish_status": "not_started"}
        for i in ids
    }
    for doc_id, total, done in rows:
        result[doc_id] = {
            "text_blocks": total,
            "polished_blocks": int(done or 0),
            "polish_status": (
                "completed"
                if total and done == total
                else "partial" if done else "not_started"
            ),
        }
    seen = set()
    for task in (
        db.query(Task)
        .filter(Task.document_id.in_(ids), Task.task_type == TaskType.OCR_CORRECTION)
        .order_by(Task.id.desc())
    ):
        if task.document_id in seen:
            continue
        seen.add(task.document_id)
        state = result[task.document_id]
        if task.status in (TaskStatus.RUNNING, TaskStatus.PENDING):
            state["polish_status"] = (
                "running" if task.status == TaskStatus.RUNNING else "pending"
            )
        elif (
            task.status == TaskStatus.COMPLETED
            and any(
                page.get("held_for_review", 0)
                for page in (task.result or {}).get("pages", [])
            )
            and state["polish_status"] != "completed"
        ):
            state["polish_status"] = "needs_review"
        elif task.status == TaskStatus.FAILED and state["polish_status"] != "completed":
            state["polish_status"] = "failed"
    return result
