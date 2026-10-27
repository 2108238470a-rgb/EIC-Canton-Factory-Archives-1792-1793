"""Capture every ORM block text change, including Celery writes, in its transaction."""

import hashlib
from uuid import uuid4
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session
from app.models import (
    Block,
    TextRevision,
    TextType,
    EvidenceSpan,
    SearchChunk,
    ChunkStatus,
    Annotation,
)

TEXT_FIELDS = {
    "ocr_text_raw": TextType.OCR_RAW,
    "ocr_text_corrected": TextType.OCR_CORRECTED,
    "modern_english": TextType.MODERN_ENGLISH,
    "translation_zh": TextType.TRANSLATION_ZH,
}


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def current_revision(db, block, field=None):
    field = field or (
        "ocr_text_corrected"
        if block.ocr_text_corrected
        and block.ocr_correction_source_text == block.ocr_text_raw
        else "ocr_text_raw"
    )
    text = getattr(block, field) or ""
    revision = (
        db.query(TextRevision)
        .filter_by(block_id=block.id, text_type=TEXT_FIELDS[field])
        .order_by(TextRevision.id.desc())
        .first()
    )
    if revision is None or revision.content != text:
        revision = TextRevision(
            block_id=block.id,
            text_type=TEXT_FIELDS[field],
            content=text,
            content_hash=digest(text),
            previous_revision_id=revision.id if revision else None,
            revision_number=(revision.revision_number + 1) if revision else 1,
            author="system",
            author_type="snapshot",
            review_state=(
                "approved" if block.review_status.value == "approved" else "pending"
            ),
        )
        db.add(revision)
        db.flush()
    return revision


def invalidate(db, block_id, text_type=None):
    revisions = db.query(TextRevision.id).filter_by(block_id=block_id)
    if text_type:
        revisions = revisions.filter(TextRevision.text_type == text_type)
    spans = (
        db.query(EvidenceSpan)
        .filter(EvidenceSpan.text_revision_id.in_(revisions))
        .all()
    )
    span_ids = {e.id for e in spans}
    for span in spans:
        span.validity = "stale"
    # A block may participate in cross-page chunks; inspect their complete segment mapping.
    for chunk in db.query(SearchChunk).filter(
        SearchChunk.status != ChunkStatus.INVALIDATED
    ):
        if chunk.block_id == block_id or any(
            s["block_id"] == block_id for s in (chunk.segments or [])
        ):
            chunk.status = ChunkStatus.INVALIDATED
    if span_ids:
        from app.models import (
            Assertion,
            AssertionEvidence,
            AssertionStatus,
            SourceUnitSpan,
            SourceUnit,
            SegmentationStatus,
            Event,
            EventStatus,
            Participation,
        )

        for assertion in (
            db.query(Assertion)
            .join(AssertionEvidence)
            .filter(
                AssertionEvidence.evidence_span_id.in_(span_ids),
                Assertion.status == AssertionStatus.VERIFIED,
            )
        ):
            assertion.status = AssertionStatus.DISPUTED
        for part in db.query(SourceUnitSpan).filter_by(block_id=block_id):
            unit = db.get(SourceUnit, part.source_unit_id)
            if unit:
                unit.segmentation_status = SegmentationStatus.NEEDS_REVIEW
        for annotation in db.query(Annotation).filter(Annotation.status != "rejected"):
            if span_ids.intersection(annotation.evidence_ids):
                annotation.status = "needs_validation"
                if annotation.event_id:
                    db.get(Event, annotation.event_id).status = EventStatus.DISPUTED
                for participation in db.query(Participation).filter_by(
                    notes=f"annotation:{annotation.public_id}"
                ):
                    db.delete(participation)
                annotation.version += 1


@event.listens_for(Session, "before_flush")
def snapshot_changes(db, flush_context, instances):
    for block in list(db.new):
        if isinstance(block, Block):
            for field, text_type in TEXT_FIELDS.items():
                text = getattr(block, field)
                if text:
                    db.add(
                        TextRevision(
                            block=block,
                            text_type=text_type,
                            content=text,
                            content_hash=digest(text),
                            revision_number=1,
                            author="system",
                            author_type="ocr",
                            review_state="pending",
                        )
                    )
    for revision in list(db.dirty):
        if isinstance(revision, TextRevision) and inspect(revision).persistent:
            if any(
                inspect(revision).attrs[field].history.has_changes()
                for field in ("content", "content_hash", "text_type", "block_id")
            ):
                raise ValueError(
                    "Text revisions are immutable; create a new revision instead"
                )
    for block in list(db.dirty):
        if not isinstance(block, Block):
            continue
        state = inspect(block)
        retired = state.attrs.retired.history.has_changes() and block.retired
        changed = [
            field for field in TEXT_FIELDS if state.attrs[field].history.has_changes()
        ]
        if retired:
            invalidate(db, block.id)
        for field in changed:
            old = state.attrs[field].history.deleted
            if not old:
                old = [
                    db.connection()
                    .execute(select(getattr(Block, field)).where(Block.id == block.id))
                    .scalar()
                ]
            previous = (
                db.query(TextRevision)
                .filter_by(block_id=block.id, text_type=TEXT_FIELDS[field])
                .order_by(TextRevision.id.desc())
                .first()
            )
            if previous is None and old[0] is not None:
                previous = TextRevision(
                    block_id=block.id,
                    text_type=TEXT_FIELDS[field],
                    content=old[0],
                    content_hash=digest(old[0]),
                    revision_number=1,
                    author="system",
                    author_type="snapshot",
                    review_state="pending",
                )
                db.add(previous)
            if previous and previous.content == (getattr(block, field) or ""):
                continue
            if field in ("ocr_text_raw", "ocr_text_corrected"):
                invalidate(db, block.id)
                for old_revision in db.query(TextRevision).filter_by(block_id=block.id):
                    old_revision.review_state = "pending"
            else:
                invalidate(db, block.id, TEXT_FIELDS[field])
            revision = TextRevision(
                block_id=block.id,
                text_type=TEXT_FIELDS[field],
                content=getattr(block, field) or "",
                content_hash=digest(getattr(block, field) or ""),
                revision_number=(previous.revision_number + 1) if previous else 1,
                author=db.info.get("text_author", "system"),
                author_type=db.info.get("text_author_type", "update"),
                review_state="pending",
            )
            if previous:
                revision.previous_revision = previous
            db.add(revision)
            if field in ("ocr_text_raw", "ocr_text_corrected"):
                from app.models import ReviewStatus

                block.review_status = ReviewStatus.NEEDS_REVIEW
        if state.attrs.review_status.history.has_changes() and not changed:
            for revision in db.query(TextRevision).filter_by(block_id=block.id):
                if revision.content == (
                    getattr(
                        block,
                        next(
                            k for k, v in TEXT_FIELDS.items() if v == revision.text_type
                        ),
                    )
                    or ""
                ):
                    revision.review_state = (
                        "approved"
                        if block.review_status.value == "approved"
                        else "pending"
                    )
            invalidate_chunks = db.query(SearchChunk).filter(
                SearchChunk.status != ChunkStatus.INVALIDATED
            )
            for chunk in invalidate_chunks:
                if chunk.block_id == block.id or any(
                    s["block_id"] == block.id for s in (chunk.segments or [])
                ):
                    chunk.status = ChunkStatus.INVALIDATED


def invalidate_search(db, block_id):
    for chunk in db.query(SearchChunk).filter(
        SearchChunk.status != ChunkStatus.INVALIDATED
    ):
        if chunk.block_id == block_id or any(
            p["block_id"] == block_id for p in (chunk.segments or [])
        ):
            chunk.status = ChunkStatus.INVALIDATED
