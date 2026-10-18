"""Durable extraction task; retried batches never overwrite human decisions."""

import asyncio
from datetime import datetime
from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import ExtractionRun, ExtractionStatus


@celery_app.task(name="knowledge.extract", acks_late=True)
def extract_knowledge_task(run_id):
    from app.workbench.extraction import extract_run

    with SessionLocal() as db:
        try:
            return asyncio.run(extract_run(db, run_id))
        except Exception as exc:
            db.rollback()
            run = (
                db.query(ExtractionRun)
                .filter_by(id=run_id)
                .with_for_update()
                .populate_existing()
                .first()
            )
            if run and run.status != ExtractionStatus.COMPLETED:
                run.status = ExtractionStatus.FAILED
                run.error_message = str(exc)[:1000]
                run.completed_at = datetime.utcnow()
                db.commit()
            raise
