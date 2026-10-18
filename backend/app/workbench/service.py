"""Canonical evidence, research annotations and auditable field review."""

import json
from datetime import date, datetime
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import or_, update
from app.models import *
from app.workbench.schemas import FIELDS
from app.workbench.versioning import current_revision, TEXT_FIELDS
from app.workbench.images import freeze_image


def get_or_404(db, model, id):
    obj = db.get(model, id)
    if obj is None:
        raise HTTPException(404, "记录不存在")
    return obj


def serialize(obj):
    return {
        c.name: (
            getattr(obj, c.name).value
            if hasattr(getattr(obj, c.name), "value")
            else getattr(obj, c.name)
        )
        for c in obj.__table__.columns
    }


def locator(db, evidence):
    revision = get_or_404(db, TextRevision, evidence.text_revision_id)
    block = get_or_404(db, Block, revision.block_id)
    page = get_or_404(db, Page, block.page_id)
    doc = get_or_404(db, Document, page.document_id)
    raw_revision = (
        db.query(TextRevision)
        .filter(
            TextRevision.block_id == block.id,
            TextRevision.text_type == TextType.OCR_RAW,
            TextRevision.id <= revision.id,
        )
        .order_by(TextRevision.id.desc())
        .first()
    )
    meta = db.query(ArchivalMetadata).filter_by(document_id=doc.id).first()
    return dict(
        id=evidence.id,
        public_id=evidence.public_id or f"evidence-{evidence.id}",
        revision_id=revision.id,
        text_version=revision.text_type.value,
        revision_content=revision.content,
        raw_revision_content=raw_revision.content if raw_revision else None,
        raw_revision_id=raw_revision.id if raw_revision else None,
        excerpt=evidence.exact_text,
        char_start=evidence.char_start,
        char_end=evidence.char_end,
        validity=evidence.validity,
        block_id=block.id,
        page_id=page.id,
        document_id=doc.id,
        document_title=doc.original_filename,
        page_number=page.page_number,
        original_page_label=page.original_page_label,
        folio_side=page.folio_side,
        archival_reference=meta.archival_reference if meta else None,
        bbox=evidence.bbox,
        image_width=evidence.image_width,
        image_height=evidence.image_height,
        location_precision=(
            evidence.location_precision.value
            if evidence.location_precision
            else "block"
        ),
        image_url=(
            f"/api/v2/workbench/evidence/{evidence.id}/image"
            if evidence.image_snapshot_path
            else f"/api/pages/{page.id}/image"
        ),
        image_frozen=bool(evidence.image_snapshot_path),
        viewer_path=f"/viewer/{doc.id}?page={page.page_number}&block={block.id}&evidence={evidence.id}",
    )


def create_evidence(db, data):
    block = (
        db.query(Block)
        .filter_by(id=data.block_id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if not block:
        raise HTTPException(404, "区块不存在")
    if block.retired:
        raise HTTPException(409, "区块已归档，请刷新页面")
    field = data.text_field or (
        "ocr_text_corrected" if block.ocr_text_corrected else "ocr_text_raw"
    )
    text = getattr(block, field) or ""
    if text != data.expected_text:
        raise HTTPException(409, "原文已更新，请刷新后重新选取证据")
    if not (0 <= data.char_start < data.char_end <= len(text)):
        raise HTTPException(422, "字符范围超出原文")
    revision = current_revision(db, block, field)
    span = (
        db.query(EvidenceSpan)
        .filter_by(
            text_revision_id=revision.id,
            char_start=data.char_start,
            char_end=data.char_end,
            validity="current",
        )
        .first()
    )
    if not span:
        page = get_or_404(db, Page, block.page_id)
        snapshot, image_version = freeze_image(page)
        span = EvidenceSpan(
            text_revision_id=revision.id,
            page_id=page.id,
            char_start=data.char_start,
            char_end=data.char_end,
            exact_text=text[data.char_start : data.char_end],
            prefix_text=text[max(0, data.char_start - 50) : data.char_start],
            suffix_text=text[data.char_end : data.char_end + 50],
            bbox=block.bbox,
            image_width=page.width,
            image_height=page.height,
            image_version=image_version,
            image_snapshot_path=snapshot,
            location_precision=LocationPrecision.BLOCK,
            validity="current",
            public_id=str(uuid4()),
        )
        db.add(span)
        db.flush()
    return span


def annotation_payload(db, a):
    result = serialize(a)
    result["evidence"] = [
        locator(db, e) for eid in a.evidence_ids if (e := db.get(EvidenceSpan, eid))
    ]
    result["entity_id"] = (
        db.get(EntityMention, a.mention_id).entity_id if a.mention_id else None
    )
    result["history"] = [
        serialize(h)
        for h in db.query(AnnotationReview)
        .filter_by(annotation_id=a.id)
        .order_by(AnnotationReview.id)
    ]
    meta = db.query(ArchivalMetadata).filter_by(document_id=a.document_id).first()
    result["archival_year"] = (
        str(meta.coverage_date_start.year)
        + (
            f"–{meta.coverage_date_end.year}"
            if meta.coverage_date_end
            and meta.coverage_date_end.year != meta.coverage_date_start.year
            else ""
        )
        if meta and meta.coverage_date_start
        else None
    )
    unit = db.get(SourceUnit, a.source_unit_id) if a.source_unit_id else None
    result["source_title"] = unit.title if unit else None
    return result


def create_annotation(db, data, run_id=None):
    get_or_404(db, Document, data.document_id)
    spans = [get_or_404(db, EvidenceSpan, eid) for eid in data.evidence_ids]
    if any(locator(db, e)["document_id"] != data.document_id for e in spans):
        raise HTTPException(422, "证据不属于当前文档")
    if any(e.validity != "current" for e in spans):
        raise HTTPException(409, "证据已失效或历史版本待核验，请重新建立证据")
    if data.source_unit_id:
        unit = get_or_404(db, SourceUnit, data.source_unit_id)
        if unit.archival_metadata.document_id != data.document_id:
            raise HTTPException(422, "文书不属于当前文档")
    fields = {k: v.strip() for k, v in data.fields.items() if v.strip()}
    mention = None
    if fields.get("name_form"):
        span = next((e for e in spans if fields["name_form"] in e.exact_text), None)
        if not span:
            raise HTTPException(422, "人名原文形式必须出现在证据引句中")
        mention = EntityMention(
            evidence_span_id=span.id,
            original_form=fields["name_form"],
            status=MentionStatus.CANDIDATE,
        )
        db.add(mention)
        db.flush()
    annotation = Annotation(
        document_id=data.document_id,
        source_unit_id=data.source_unit_id,
        mention_id=mention.id if mention else None,
        evidence_ids=list(dict.fromkeys(data.evidence_ids)),
        fields=fields,
        field_states={k: "pending" for k in fields},
        extraction_run_id=run_id,
    )
    db.add(annotation)
    db.flush()
    return annotation


def annotation_query(db, document_id=None, status=None, q=None, entity_id=None):
    query = db.query(Annotation)
    if document_id:
        query = query.filter_by(document_id=document_id)
    if status:
        query = query.filter_by(status=status)
    if entity_id:
        mentions = db.query(EntityMention.id).filter_by(entity_id=entity_id)
        linked_ids = [
            a.id
            for a in db.query(Annotation)
            if entity_id in (a.entity_links or {}).values()
        ]
        query = query.filter(
            or_(Annotation.mention_id.in_(mentions), Annotation.id.in_(linked_ids))
        )
    if q:
        from sqlalchemy import cast, Text

        query = query.filter(cast(Annotation.fields, Text).ilike("%" + q + "%"))
    return query


def review_annotation(db, id, data):
    a = db.query(Annotation).filter_by(id=id).with_for_update().first()
    if not a:
        raise HTTPException(404, "标注不存在")
    if a.version != data.expected_version:
        raise HTTPException(409, "记录已被修改，请刷新后重新审核")
    if data.field not in FIELDS or data.field not in a.fields:
        raise HTTPException(422, "字段不存在")
    if data.decision == "approved" and any(
        get_or_404(db, EvidenceSpan, eid).validity != "current"
        for eid in a.evidence_ids
    ):
        raise HTTPException(
            409, "证据已失效或历史版本待核验，需要重新选取证据并建立标注"
        )
    fields = dict(a.fields)
    states = dict(a.field_states)
    old = fields[data.field]
    if data.value is not None:
        fields[data.field] = data.value.strip()
    if data.decision == "approved" and not fields[data.field]:
        raise HTTPException(422, "不能批准空字段")
    if (
        data.field == "name_form"
        and fields[data.field]
        and not any(
            fields[data.field] in get_or_404(db, EvidenceSpan, eid).exact_text
            for eid in a.evidence_ids
        )
    ):
        raise HTTPException(422, "原文形式必须出现在证据中")
    evidence_current = all(
        get_or_404(db, EvidenceSpan, eid).validity == "current"
        for eid in a.evidence_ids
    )
    states[data.field] = data.decision
    # Every write increments a version; lock + comparison serializes PostgreSQL reviews.
    a.version += 1
    a.fields = fields
    a.field_states = states
    a.status = (
        "approved"
        if all(v == "approved" for v in states.values())
        else "rejected" if all(v == "rejected" for v in states.values()) else "pending"
    )
    if not evidence_current:
        a.status = "needs_validation"
    db.add(
        AnnotationReview(
            annotation_id=a.id,
            version=a.version,
            field=data.field,
            decision=data.decision,
            previous_value=old,
            value=fields[data.field],
            reason=data.reason,
            reviewer=data.reviewer,
        )
    )
    mention = db.get(EntityMention, a.mention_id) if a.mention_id else None
    if mention and data.field == "name_form":
        mention.original_form = fields[data.field]
        mention.status = (
            MentionStatus.CONFIRMED
            if data.decision == "approved"
            else (
                MentionStatus.REJECTED
                if data.decision == "rejected"
                else MentionStatus.PENDING
            )
        )
    for assertion in db.query(Assertion):
        if (assertion.extra_metadata or {}).get("annotation_id") == a.id:
            assertion.status = AssertionStatus.REJECTED
    if data.field == "person" and data.decision == "approved":
        if not mention:
            raise HTTPException(422, "确认人物前请先填写原文人名形式")
        entity = (
            get_or_404(db, Entity, data.entity_id)
            if data.entity_id
            else (
                db.get(Entity, mention.entity_id)
                if mention.entity_id and old == fields["person"]
                else None
            )
        )
        if entity and entity.entity_type != EntityType.PERSON:
            raise HTTPException(422, "所选实体不是人物")
        if not entity:
            # Same spelling is never sufficient to merge two historical identities.
            entity = Entity(
                entity_type=EntityType.PERSON,
                canonical_name=fields["person"],
                alternative_names=json.dumps(
                    [mention.original_form], ensure_ascii=False
                ),
            )
            db.add(entity)
            db.flush()
        previous = (
            db.query(IdentityDecision)
            .filter_by(mention_id=mention.id, status=DecisionStatus.APPROVED)
            .order_by(IdentityDecision.id.desc())
            .first()
        )
        if previous:
            previous.status = DecisionStatus.SUPERSEDED
        db.add(
            IdentityDecision(
                mention_id=mention.id,
                entity_id=entity.id,
                basis=data.reason,
                status=DecisionStatus.APPROVED,
                reviewer=data.reviewer,
                reviewer_type="human",
                previous_decision_id=previous.id if previous else None,
            )
        )
        mention.entity_id = entity.id
    elif data.field == "person" and mention and data.decision != "approved":
        mention.entity_id = None
        for identity in db.query(IdentityDecision).filter_by(
            mention_id=mention.id, status=DecisionStatus.APPROVED
        ):
            identity.status = DecisionStatus.SUPERSEDED
    links = dict(a.entity_links or {})
    if data.field in ("organization", "location"):
        if data.decision == "approved":
            kind = (
                EntityType.ORGANIZATION
                if data.field == "organization"
                else EntityType.PLACE
            )
            linked = (
                get_or_404(db, Entity, data.entity_id)
                if data.entity_id
                else (
                    db.get(Entity, links.get(data.field))
                    if links.get(data.field) and old == fields[data.field]
                    else None
                )
            )
            if linked and linked.entity_type != kind:
                raise HTTPException(422, "所选实体类型不匹配")
            if not linked:
                linked = Entity(entity_type=kind, canonical_name=fields[data.field])
                db.add(linked)
                db.flush()
            links[data.field] = linked.id
        else:
            links.pop(data.field, None)
        a.entity_links = links
    if data.field == "event":
        if data.decision == "approved":
            event = (
                db.get(Event, a.event_id)
                if a.event_id
                else Event(title=fields["event"], event_type="other")
            )
            event.title = fields["event"]
            event.status = EventStatus.CONFIRMED
            db.add(event)
            db.flush()
            a.event_id = event.id
        elif a.event_id:
            db.get(Event, a.event_id).status = EventStatus.DISPUTED
    if data.field in ("person", "event", "role"):
        for part in db.query(Participation).filter_by(
            notes=f"annotation:{a.public_id}"
        ):
            db.delete(part)
    if a.event_id:
        current_event = db.get(Event, a.event_id)
        current_event.location_entity_id = links.get("location")
        current_event.location_text = (
            fields.get("location") if states.get("location") == "approved" else None
        )
        try:
            parsed_date = (
                date.fromisoformat(fields.get("event_date", ""))
                if states.get("event_date") == "approved"
                else None
            )
        except ValueError:
            parsed_date = None
        current_event.date_start = parsed_date
        current_event.date_end = parsed_date
        current_event.date_precision = "day" if parsed_date else "unknown"
    # Approved descriptive fields become evidence-backed assertions; replace only
    # this annotation's prior projection, retaining every previous assertion row.
    if mention and mention.entity_id and evidence_current:
        for key, value in fields.items():
            if key in ("person", "name_form", "notes", "event"):
                continue
            for assertion in db.query(Assertion).filter_by(
                subject_entity_id=mention.entity_id, predicate=key
            ):
                if (assertion.extra_metadata or {}).get("annotation_id") == a.id:
                    assertion.status = AssertionStatus.REJECTED
            if states.get(key) == "approved":
                assertion = Assertion(
                    subject_entity_id=mention.entity_id,
                    predicate=key,
                    object_literal=value,
                    object_entity_id=links.get(key),
                    status=AssertionStatus.VERIFIED,
                    source_type=SourceType.MANUAL,
                    extra_metadata={"annotation_id": a.id, "version": a.version},
                )
                db.add(assertion)
                db.flush()
                for eid in a.evidence_ids:
                    db.add(
                        AssertionEvidence(
                            assertion_id=assertion.id,
                            evidence_span_id=eid,
                            relation=EvidenceRelation.SUPPORTS,
                        )
                    )
        if (
            a.event_id
            and states.get("person") == "approved"
            and states.get("role") == "approved"
            and states.get("event") == "approved"
        ):
            part = (
                db.query(Participation)
                .filter_by(entity_id=mention.entity_id, event_id=a.event_id)
                .first()
            )
            if not part:
                db.add(
                    Participation(
                        entity_id=mention.entity_id,
                        event_id=a.event_id,
                        role=fields["role"],
                        notes=f"annotation:{a.public_id}",
                    )
                )
    db.flush()
    return a
