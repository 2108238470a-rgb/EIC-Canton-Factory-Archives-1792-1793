"""Independent research queue task; never starts or modifies OCR."""

import asyncio
from app.tasks.celery_app import celery_app
from app.database import SessionLocal


@celery_app.task(name="insights.analyze", acks_late=True)
def analyze_document(run_id):
    from app.insights.service import analyze

    with SessionLocal() as db:
        result = asyncio.run(analyze(db, run_id, max_batches=1))
        if result and result.get("continue"):
            try:
                analyze_document.delay(run_id)
            except Exception:
                from app.models import ExtractionRun, ExtractionStatus

                run = db.get(ExtractionRun, run_id)
                if run.status == ExtractionStatus.PENDING:
                    run.status = ExtractionStatus.FAILED
                    run.error_message = (
                        "下一批任务入队失败；已完成结果保留，请恢复队列后继续。"
                    )
                    db.commit()
                raise
