"""Public canonical workflow API. Legacy routes are read adapters only."""

import csv
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.services.document_progress import processing_summaries
from app.models import *
from app.workbench.schemas import *
from app.workbench.service import *
from app.workbench.extraction import request_run
from app.workbench.versioning import current_revision, invalidate_search

router = APIRouter(prefix="/workbench", tags=["research-workbench"])


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    counts = {
        name: db.query(model).count()
        for name, model in [
            ("entities", Entity),
            ("events", Event),
            ("evidence_spans", EvidenceSpan),
            ("mentions", EntityMention),
            ("assertions", Assertion),
            ("corpora", ResearchCorpus),
            ("corpus_documents", CorpusMembership),
        ]
    }
    counts["unresolved_mentions"] = (
        db.query(EntityMention).filter(EntityMention.entity_id.is_(None)).count()
    )
    counts["pending"] = (
        db.query(Annotation)
        .filter(Annotation.status.in_(["pending", "needs_validation"]))
        .count()
    )
    counts["annotations"] = db.query(Annotation).count()
    counts["documents"] = (
        db.query(Document).filter(Document.archived_at.is_(None)).count()
    )
    counts["pages"] = int(
        db.query(func.sum(Document.page_count))
        .filter(Document.archived_at.is_(None))
        .scalar()
        or 0
    )
    counts["ocr_pages"] = (
        db.query(Page.id)
        .join(Document)
        .join(Block)
        .filter(
            Document.archived_at.is_(None),
            Block.retired.is_(False),
            func.length(func.trim(func.coalesce(Block.ocr_text_raw, ""))) > 0,
        )
        .distinct()
        .count()
    )
    recent = (
        db.query(Document)
        .filter(Document.archived_at.is_(None))
        .order_by(Document.id.desc())
        .limit(5)
        .all()
    )
    summaries = processing_summaries(db, [d.id for d in recent])
    counts["recent_documents"] = [
        {**serialize(d), "processing_summary": summaries[d.id]} for d in recent
    ]
    counts["tasks"] = [
        serialize(t) for t in db.query(Task).order_by(Task.id.desc()).limit(6)
    ]
    counts["extractions"] = [
        serialize(r)
        for r in db.query(ExtractionRun)
        .filter(ExtractionRun.schema_version != "document-insights-v1")
        .order_by(ExtractionRun.id.desc())
        .limit(6)
    ]
    return counts


@router.get("/corpora")
def corpora(db: Session = Depends(get_db)):
    return {
        "items": [
            serialize(c) for c in db.query(ResearchCorpus).order_by(ResearchCorpus.id)
        ]
    }


@router.get("/documents/{document_id}/metadata")
def metadata(document_id: int, db: Session = Depends(get_db)):
    get_or_404(db, Document, document_id)
    meta = db.query(ArchivalMetadata).filter_by(document_id=document_id).first()
    membership = db.query(CorpusMembership).filter_by(document_id=document_id).first()
    return {
        **(serialize(meta) if meta else {"document_id": document_id}),
        "corpus_id": membership.corpus_id if membership else None,
    }


class MetadataInput(BaseModel):
    repository: str | None = None
    archival_reference: str | None = None
    collection_name: str | None = None
    coverage_date_start: date | None = None
    coverage_date_end: date | None = None
    notes: str | None = None


@router.put("/documents/{document_id}/metadata")
def save_metadata(document_id: int, data: MetadataInput, db: Session = Depends(get_db)):
    get_or_404(db, Document, document_id)
    if (
        data.coverage_date_start
        and data.coverage_date_end
        and data.coverage_date_start > data.coverage_date_end
    ):
        raise HTTPException(422, "日期范围无效")
    meta = db.query(ArchivalMetadata).filter_by(
        document_id=document_id
    ).first() or ArchivalMetadata(document_id=document_id)
    for k, v in data.model_dump().items():
        setattr(meta, k, v)
    db.add(meta)
    db.commit()
    return serialize(meta)


class PageLabelInput(BaseModel):
    original_page_label: str | None = Field(None, max_length=100)
    folio_side: Literal["recto", "verso", ""] = ""


@router.put("/pages/{page_id}/label")
def page_label(page_id: int, data: PageLabelInput, db: Session = Depends(get_db)):
    page = get_or_404(db, Page, page_id)
    page.original_page_label = data.original_page_label
    page.folio_side = data.folio_side or None
    db.commit()
    return serialize(page)


@router.get("/blocks/{block_id}/revisions")
def revisions(block_id: int, db: Session = Depends(get_db)):
    block = get_or_404(db, Block, block_id)
    current_revision(db, block)
    db.commit()
    return {
        "items": [
            serialize(r)
            for r in db.query(TextRevision)
            .filter_by(block_id=block_id)
            .order_by(TextRevision.id.desc())
        ]
    }


@router.post("/evidence", status_code=201)
def new_evidence(data: EvidenceCreate, db: Session = Depends(get_db)):
    span = create_evidence(db, data)
    db.commit()
    return locator(db, span)


@router.get("/evidence/{evidence_id}")
def evidence(evidence_id: int, db: Session = Depends(get_db)):
    return locator(db, get_or_404(db, EvidenceSpan, evidence_id))


@router.post("/annotations", status_code=201)
def new_annotation(data: AnnotationCreate, db: Session = Depends(get_db)):
    a = create_annotation(db, data)
    db.commit()
    return annotation_payload(db, a)


@router.get("/annotations")
def annotations(
    document_id: int | None = None,
    status: (
        Literal["pending", "approved", "rejected", "needs_validation"] | None
    ) = None,
    q: str | None = None,
    entity_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = annotation_query(db, document_id, status, q, entity_id)
    return {
        "items": [
            annotation_payload(db, a)
            for a in query.order_by(Annotation.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ],
        "total": query.count(),
        "page": page,
        "page_size": page_size,
    }


@router.get("/annotations/{id}")
def annotation(id: int, db: Session = Depends(get_db)):
    return annotation_payload(db, get_or_404(db, Annotation, id))


@router.post("/annotations/{id}/reviews")
def review(id: int, data: ReviewRequest, db: Session = Depends(get_db)):
    a = review_annotation(db, id, data)
    db.commit()
    return annotation_payload(db, a)


@router.post("/annotations/{id}/identity")
def identity(id: int, data: IdentityRequest, db: Session = Depends(get_db)):
    a = get_or_404(db, Annotation, id)
    if not a.mention_id or "person" not in a.fields:
        raise HTTPException(422, "此标注没有人物提及")
    review_data = ReviewRequest(
        expected_version=data.annotation_version,
        field="person",
        decision="approved" if data.entity_id else "pending",
        entity_id=data.entity_id,
        reason=data.reason,
    )
    a = review_annotation(db, id, review_data)
    db.commit()
    return annotation_payload(db, a)


@router.get("/documents/{document_id}/source-units")
def source_units(document_id: int, db: Session = Depends(get_db)):
    items = (
        db.query(SourceUnit)
        .join(ArchivalMetadata)
        .filter(ArchivalMetadata.document_id == document_id)
        .order_by(SourceUnit.id)
        .all()
    )
    return {
        "items": [
            dict(**serialize(u), spans=[serialize(s) for s in u.spans]) for u in items
        ]
    }


@router.post("/documents/{document_id}/source-units", status_code=201)
def new_source_unit(
    document_id: int, data: SourceUnitCreate, db: Session = Depends(get_db)
):
    get_or_404(db, Document, document_id)
    if (
        data.normalized_date_start
        and data.normalized_date_end
        and data.normalized_date_start > data.normalized_date_end
    ):
        raise HTTPException(422, "日期范围无效")
    meta = db.query(ArchivalMetadata).filter_by(document_id=document_id).first()
    if not meta:
        meta = ArchivalMetadata(document_id=document_id)
        db.add(meta)
        db.flush()
    values = data.model_dump(exclude={"spans"})
    values["unit_type"] = SourceUnitType(data.unit_type)
    values["date_precision"] = DatePrecision(data.date_precision)
    unit = SourceUnit(archival_metadata_id=meta.id, **values)
    db.add(unit)
    db.flush()
    for order, part in enumerate(data.spans):
        revision = get_or_404(db, TextRevision, part.revision_id)
        block = get_or_404(db, Block, part.block_id)
        if (
            revision.block_id != block.id
            or db.get(Page, block.page_id).document_id != document_id
            or block.retired
        ):
            raise HTTPException(422, "文书范围包含无效区块")
        if not 0 <= part.char_start < part.char_end <= len(revision.content):
            raise HTTPException(422, "文书字符范围无效")
        if current_revision(db, block).id != revision.id:
            raise HTTPException(409, "文书引用的原文已更新")
        db.add(
            SourceUnitSpan(
                source_unit_id=unit.id,
                block_id=block.id,
                revision_id=revision.id,
                reading_order=order,
                char_start=part.char_start,
                char_end=part.char_end,
            )
        )
        invalidate_search(db, block.id)
    db.commit()
    return serialize(unit)


class SegmentReview(BaseModel):
    approved: bool
    expected_updated_at: datetime


@router.post("/source-units/{id}/review")
def review_source_unit(id: int, data: SegmentReview, db: Session = Depends(get_db)):
    unit = db.query(SourceUnit).filter_by(id=id).with_for_update().first()
    if not unit:
        raise HTTPException(404, "文书不存在")
    if unit.updated_at != data.expected_updated_at:
        raise HTTPException(409, "文书审核状态已更新，请刷新后重新核对")
    unit.updated_at = datetime.utcnow()
    for part in unit.spans:
        block = get_or_404(db, Block, part.block_id)
        if (
            block.retired
            or not part.revision_id
            or current_revision(db, block).id != part.revision_id
        ):
            raise HTTPException(409, "文书原文已更新，需要重新分段")
        invalidate_search(db, block.id)
    unit.segmentation_status = (
        SegmentationStatus.APPROVED
        if data.approved
        else SegmentationStatus.NEEDS_REVIEW
    )
    db.add(
        ReviewDecision(
            target_type=ReviewTargetType.SOURCE_UNIT,
            target_id=unit.id,
            decision=(
                ReviewDecisionType.APPROVED
                if data.approved
                else ReviewDecisionType.NEEDS_REVISION
            ),
            reviewer="研究者",
        )
    )
    db.commit()
    return serialize(unit)


@router.post("/documents/{document_id}/extractions", status_code=202)
def start_extraction(
    document_id: int, data: ExtractionRequest, db: Session = Depends(get_db)
):
    from app.tasks.knowledge_tasks import extract_knowledge_task

    get_or_404(db, Document, document_id)
    run, created = request_run(db, document_id, data)
    db.commit()
    if created:
        try:
            extract_knowledge_task.delay(run.id)
        except Exception:
            run.status = ExtractionStatus.FAILED
            run.error_message = "任务队列不可用，请稍后重试"
            db.commit()
            raise HTTPException(503, "任务队列不可用；抽取批次已保存，可以重试")
    return serialize(run)


@router.get("/extractions/{id}")
def extraction(id: int, db: Session = Depends(get_db)):
    return serialize(get_or_404(db, ExtractionRun, id))


@router.post("/extractions/{id}/retry", status_code=202)
def retry_extraction(id: int, db: Session = Depends(get_db)):
    from app.tasks.knowledge_tasks import extract_knowledge_task

    run = db.query(ExtractionRun).filter_by(id=id).with_for_update().first()
    if not run:
        raise HTTPException(404, "批次不存在")
    if run.status != ExtractionStatus.FAILED:
        raise HTTPException(409, "只有失败批次可以重试")
    run.status = ExtractionStatus.PENDING
    run.error_message = None
    db.commit()
    try:
        extract_knowledge_task.delay(run.id)
    except Exception:
        run.status = ExtractionStatus.FAILED
        run.error_message = "任务队列不可用"
        db.commit()
        raise HTTPException(503, "任务队列不可用")
    return serialize(run)


@router.get("/entities")
def entities(
    q: str | None = None,
    entity_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Entity)
    if q:
        query = query.filter(
            or_(
                Entity.canonical_name.ilike("%" + q + "%"),
                Entity.alternative_names.ilike("%" + q + "%"),
            )
        )
    if entity_type:
        try:
            query = query.filter(Entity.entity_type == EntityType(entity_type))
        except ValueError:
            raise HTTPException(422, "未知实体类型")
    return {
        "items": [
            dict(
                **serialize(e),
                names=[
                    {"id": i, "name": n, "name_type": "alias"}
                    for i, n in enumerate(json.loads(e.alternative_names or "[]"))
                ],
                disambiguation_status="confirmed" if e.mentions else "unresolved",
                is_inferred=False,
            )
            for e in query.order_by(Entity.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ],
        "total": query.count(),
        "page": page,
        "page_size": page_size,
    }


class EntityInput(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=500)
    entity_type: EntityType = EntityType.PERSON
    notes: str | None = None


@router.post("/entities", status_code=201)
def new_entity(data: EntityInput, db: Session = Depends(get_db)):
    e = Entity(**data.model_dump())
    db.add(e)
    db.commit()
    return dict(
        **serialize(e), names=[], disambiguation_status="unresolved", is_inferred=False
    )


@router.get("/entities/{id}")
def entity(id: int, db: Session = Depends(get_db)):
    e = get_or_404(db, Entity, id)
    rows = annotation_query(db, entity_id=id).order_by(Annotation.id.desc()).all()
    assertions = db.query(Assertion).filter_by(subject_entity_id=id).all()
    legacy_roles = [
        m.payload
        for m in db.query(LegacyMapping).filter_by(
            source_table="knowledge_person_roles"
        )
        if any(
            x.old_id == m.payload.get("person_entity_id") and x.new_id == id
            for x in db.query(LegacyMapping).filter_by(
                source_table="knowledge_entities"
            )
        )
    ]
    return dict(
        **serialize(e),
        names=json.loads(e.alternative_names or "[]"),
        annotations=[annotation_payload(db, a) for a in rows],
        assertions=[
            dict(
                **serialize(a),
                object_name=a.object_entity.canonical_name if a.object_entity else None,
                evidence=[locator(db, ae.evidence_span) for ae in a.evidences],
            )
            for a in assertions
        ],
        identity_decisions=[serialize(d) for d in e.identity_decisions],
        events=[serialize(p.event) for p in e.participations],
        legacy_roles=legacy_roles,
    )


@router.get("/events")
def events(
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Event)
    if q:
        query = query.filter(Event.title.ilike("%" + q + "%"))
    return {
        "items": [
            dict(
                **serialize(e),
                start_date=e.date_start,
                end_date=e.date_end,
                participants=[serialize(p) for p in e.participations],
            )
            for e in query.order_by(Event.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ],
        "total": query.count(),
        "page": page,
        "page_size": page_size,
    }


@router.get("/events/{id}")
def event_detail(id: int, db: Session = Depends(get_db)):
    e = get_or_404(db, Event, id)
    return dict(
        **serialize(e),
        participants=[
            dict(**serialize(p), entity_name=p.entity.canonical_name)
            for p in e.participations
        ],
        annotations=[
            annotation_payload(db, a)
            for a in db.query(Annotation).filter_by(event_id=id)
        ],
        mentions=[serialize(m) for m in e.mentions],
        relations=[serialize(r) for r in e.relations_as_source],
    )


EXPORT_COLUMNS = [
    "标注序号",
    "档案年份",
    "档案页码",
    "文书日期",
    "人名",
    "人名形式",
    "敬称或称号",
    "国籍",
    "职业",
    "人物所属机构",
    "事件",
    "地点",
    "相关事件",
    "证据位置（可贴图）",
    "需要复核",
    "备注",
]


@router.get("/exports")
def export_annotations(
    format: Literal["csv", "json", "zip"] = "csv",
    document_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    entity_id: int | None = None,
    db: Session = Depends(get_db),
):
    if db.bind.dialect.name == "postgresql":
        db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    records = [
        annotation_payload(db, a)
        for a in annotation_query(db, document_id, status, q, entity_id).order_by(
            Annotation.id
        )
    ]
    rows = []
    for a in records:
        f = a["fields"]
        ev = a["evidence"]
        rows.append(
            [
                a["public_id"],
                a["archival_year"] or "",
                "; ".join(
                    f"PDF {e['page_number']} / 原档 {e['original_page_label'] or '未录入'} {e['folio_side'] or ''}"
                    for e in ev
                ),
                f.get("document_date", ""),
                f.get("person", ""),
                f.get("name_form", ""),
                f.get("honorific", ""),
                f.get("nationality", ""),
                f.get("occupation", ""),
                f.get("organization", ""),
                f.get("event", ""),
                f.get("location", ""),
                f.get("related_event", ""),
                "; ".join(f"/api/v2/workbench/evidence/{e['id']}" for e in ev),
                str(a["status"] != "approved").lower(),
                f.get("notes", ""),
            ]
        )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(EXPORT_COLUMNS)
    # Neutralize formulas when opened by spreadsheet software, preserving JSON originals.
    writer.writerows(
        [
            [
                (
                    "'" + v
                    if isinstance(v, str)
                    and v.startswith(("=", "+", "-", "@", "\t", "\r"))
                    else v
                )
                for v in row
            ]
            for row in rows
        ]
    )
    csv_data = output.getvalue().encode("utf-8-sig")
    snapshot = {
        "created_at": datetime.utcnow().isoformat() + "Z",
        "filters": {
            "document_id": document_id,
            "status": status,
            "q": q,
            "entity_id": entity_id,
        },
        "count": len(records),
        "annotations": records,
    }
    json_data = json.dumps(snapshot, ensure_ascii=False, default=str, indent=2).encode()
    if format == "json":
        body = json_data
        mime = "application/json"
    elif format == "csv":
        body = csv_data
        mime = "text/csv; charset=utf-8"
    else:
        from PIL import Image
        from app.config import settings

        manifest = []
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("annotations.csv", csv_data)
            archive.writestr("annotations.json", json_data)
            seen = set()
            for a in records:
                for e in a["evidence"]:
                    if e["id"] in seen:
                        continue
                    seen.add(e["id"])
                    entry = dict(e, crop_path=None)
                    page = db.get(Page, e["page_id"])
                    span = db.get(EvidenceSpan, e["id"])
                    path = Path(span.image_snapshot_path or page.image_path or "")
                    try:
                        if e["validity"] != "current" and not span.image_snapshot_path:
                            raise ValueError("历史证据不裁取当前图像")
                        if not path.is_file() or not e["bbox"]:
                            raise ValueError("原图或坐标不可用")
                        with Image.open(path) as image:
                            crop = image.crop(tuple(e["bbox"]))
                            png = io.BytesIO()
                            crop.save(png, format="PNG")
                        entry["crop_path"] = f"evidence/{e['public_id']}.png"
                        archive.writestr(entry["crop_path"], png.getvalue())
                    except (OSError, ValueError) as exc:
                        entry["crop_error"] = str(exc)
                    manifest.append(entry)
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {"snapshot": snapshot["created_at"], "evidence": manifest},
                    ensure_ascii=False,
                    default=str,
                    indent=2,
                ),
            )
        body = buf.getvalue()
        mime = "application/zip"
    return Response(
        body,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="annotations.{format}"'},
    )


class TextReviewInput(BaseModel):
    text_field: Literal[
        "ocr_text_raw", "ocr_text_corrected", "modern_english", "translation_zh"
    ]
    expected_text: str
    approved: bool = True


@router.post("/blocks/{block_id}/text-review")
def text_review(block_id: int, data: TextReviewInput, db: Session = Depends(get_db)):
    block = db.query(Block).filter_by(id=block_id).with_for_update().first()
    if not block or block.retired:
        raise HTTPException(404, "区块不存在或已归档")
    if (getattr(block, data.text_field) or "") != data.expected_text:
        raise HTTPException(409, "原文已更新，请重新核对")
    revision = current_revision(db, block, data.text_field)
    revision.review_state = "approved" if data.approved else "pending"
    for chunk in db.query(SearchChunk).filter(
        SearchChunk.status != ChunkStatus.INVALIDATED
    ):
        if any(p["revision_id"] == revision.id for p in (chunk.segments or [])):
            chunk.status = ChunkStatus.INVALIDATED
    db.add(
        ReviewDecision(
            target_type=ReviewTargetType.TEXT_REVISION,
            target_id=revision.id,
            decision=(
                ReviewDecisionType.APPROVED
                if data.approved
                else ReviewDecisionType.NEEDS_REVISION
            ),
            reviewer="研究者",
        )
    )
    db.commit()
    return serialize(revision)


@router.get("/evidence/{evidence_id}/image")
def evidence_image(evidence_id: int, db: Session = Depends(get_db)):
    from app.config import settings

    span = get_or_404(db, EvidenceSpan, evidence_id)
    if not span.image_snapshot_path:
        raise HTTPException(404, "此历史证据未保存独立图像版本")
    path = Path(span.image_snapshot_path).resolve()
    if (
        not path.is_relative_to(
            settings.get_storage_path() / "results" / "evidence-images"
        )
        or not path.is_file()
    ):
        raise HTTPException(404, "证据图像不可用")
    return FileResponse(path)


class CorpusInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


@router.post("/corpora", status_code=201)
def create_corpus(data: CorpusInput, db: Session = Depends(get_db)):
    corpus = ResearchCorpus(
        name=data.name, metadata_json={"description": data.description}
    )
    db.add(corpus)
    db.commit()
    return serialize(corpus)


class CorpusAttach(BaseModel):
    document_id: int


@router.post("/corpora/{id}/documents")
def corpus_attach(id: int, data: CorpusAttach, db: Session = Depends(get_db)):
    get_or_404(db, ResearchCorpus, id)
    get_or_404(db, Document, data.document_id)
    membership = (
        db.query(CorpusMembership).filter_by(document_id=data.document_id).first()
    )
    if membership and membership.corpus_id != id:
        raise HTTPException(409, "文档已属于另一集合，请先核对馆藏归属")
    if not membership:
        membership = CorpusMembership(corpus_id=id, document_id=data.document_id)
        db.add(membership)
    db.commit()
    return serialize(membership)


class ManualCorrectionInput(BaseModel):
    expected_raw_text: str
    expected_corrected_text: str | None = None
    corrected_text: str = Field(min_length=1)


@router.post("/blocks/{block_id}/correction")
def manual_correction(
    block_id: int, data: ManualCorrectionInput, db: Session = Depends(get_db)
):
    from app.schemas import BlockResponse

    block = (
        db.query(Block)
        .filter_by(id=block_id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if not block or block.retired:
        raise HTTPException(404, "当前区块不存在或已归档")
    if (
        (block.ocr_text_raw or "") != data.expected_raw_text
        or block.ocr_text_corrected != data.expected_corrected_text
    ):
        raise HTTPException(409, "原文或校文已更新，请刷新后重新校订")
    block.ocr_text_corrected = data.corrected_text
    block.ocr_correction_source_text = block.ocr_text_raw
    db.info["text_author"] = "研究者"
    db.info["text_author_type"] = "human"
    try:
        db.commit()
    finally:
        db.info.pop("text_author", None)
        db.info.pop("text_author_type", None)
    return BlockResponse.model_validate(block)


@router.get("/blocks/{block_id}/correction-quality")
def correction_quality(block_id: int, db: Session = Depends(get_db)):
    from sqlalchemy import or_
    from app.services.correction_quality import ocr_warnings
    from app.workbench.versioning import digest

    block = get_or_404(db, Block, block_id)
    page = get_or_404(db, Page, block.page_id)
    tasks = (
        db.query(Task)
        .filter(
            or_(
                Task.block_id == block_id,
                Task.page_id == page.id,
                Task.document_id == page.document_id,
            )
        )
        .order_by(Task.id.desc())
        .limit(50)
    )
    report = None
    for task in tasks:
        result = task.result or {}
        candidates = [result.get("quality_report", {})] + [
            p.get("quality_reports", {}).get(
                str(block_id), p.get("quality_reports", {}).get(block_id, {})
            )
            for p in result.get("pages", [])
        ]
        candidates += [result.get("quality_reports", {}).get(str(block_id), {})]
        for candidate in candidates:
            if candidate and candidate.get("source_hash") == digest(
                block.ocr_text_raw or ""
            ):
                report = candidate
                break
        if report:
            break
    return {
        "block_id": block_id,
        "ocr_warnings": ocr_warnings(block.ocr_text_raw or ""),
        "report": report,
    }
