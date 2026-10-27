"""Translate legacy request shapes into canonical, evidence-checked writes."""

import json
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import func, text
from pydantic import ValidationError
from app.models import *
from app.knowledge import schemas as old
from app.workbench.schemas import EvidenceCreate, AnnotationCreate, ReviewRequest
from app.workbench.service import (
    create_evidence,
    create_annotation,
    review_annotation,
    get_or_404,
)
from app.workbench.legacy import iso


def resolve(db, table, id):
    if id is None:
        return None
    mapping = db.query(LegacyMapping).filter_by(source_table=table, old_id=id).first()
    if not mapping or not mapping.new_id:
        raise HTTPException(404, "旧记录不存在或尚无可操作的规范记录")
    return mapping.new_id


def remember(db, table, obj, payload):
    # Compatibility IDs have their own namespace, separate from canonical IDs.
    if db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {"name": table}
        )
    id = (
        db.query(func.max(LegacyMapping.old_id)).filter_by(source_table=table).scalar()
        or 0
    ) + 1
    now = datetime.utcnow().isoformat()
    payload = {
        **payload,
        "id": id,
        "created_at": now,
        "updated_at": now,
        "_canonical_write": True,
    }
    mapping = LegacyMapping(
        source_table=table,
        old_id=id,
        target_table=obj.__tablename__,
        new_id=obj.id,
        payload=payload,
    )
    db.add(mapping)
    db.flush()
    return payload


def write_legacy(db, resource, id, action, body, method):
    def checked(schema):
        try:
            return schema.model_validate(body)
        except ValidationError as exc:
            raise HTTPException(422, exc.errors(include_context=False))

    def mapped(table):
        mapping = (
            db.query(LegacyMapping)
            .filter_by(source_table=table, old_id=id)
            .with_for_update()
            .first()
        )
        if not mapping or not mapping.new_id:
            raise HTTPException(404, "旧记录不存在")
        return mapping

    response = None
    if resource == "entities" and id is None:
        data = checked(old.EntityCreate)
        payload = data.model_dump(mode="json")
        obj = Entity(
            entity_type=EntityType(data.entity_type.value),
            canonical_name=data.canonical_name,
            notes=data.notes,
            external_id=data.external_id,
            alternative_names="[]",
        )
        db.add(obj)
        db.flush()
        response = remember(
            db,
            "knowledge_entities",
            obj,
            {**payload, "names": [], "is_inferred": data.is_inferred},
        )
    elif resource == "entities" and action is None and method == "PATCH":
        data = checked(old.EntityUpdate)
        mapping = mapped("knowledge_entities")
        obj = get_or_404(db, Entity, mapping.new_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            if key in ("canonical_name", "notes", "external_id"):
                setattr(obj, key, value)
        mapping.payload = {
            **mapping.payload,
            **data.model_dump(mode="json", exclude_unset=True),
        }
        response = mapping.payload
    elif resource == "entities" and action == "names":
        data = checked(old.EntityNameCreate)
        obj = get_or_404(db, Entity, resolve(db, "knowledge_entities", id))
        aliases = json.loads(obj.alternative_names or "[]")
        if data.name not in aliases:
            aliases.append(data.name)
        obj.alternative_names = json.dumps(aliases, ensure_ascii=False)
        response = remember(
            db,
            "knowledge_entity_names",
            obj,
            {**data.model_dump(mode="json"), "entity_id": id},
        )
    elif resource == "evidence-spans" and id is None:
        data = checked(old.EvidenceSpanCreate)
        block = get_or_404(db, Block, data.block_id)
        field = {
            "ocr_raw": "ocr_text_raw",
            "ocr_auto_corrected": "ocr_text_corrected",
            "ocr_human_corrected": "ocr_text_corrected",
            "modern_english": "modern_english",
            "translation_zh": "translation_zh",
        }[data.text_version.value]
        source = getattr(block, field) or ""
        span = create_evidence(
            db,
            EvidenceCreate(
                block_id=block.id,
                text_field=field,
                expected_text=source,
                char_start=data.char_start or 0,
                char_end=data.char_end if data.char_end is not None else len(source),
            ),
        )
        page = get_or_404(db, Page, block.page_id)
        response = remember(
            db,
            "knowledge_evidence_spans",
            span,
            {
                **data.model_dump(mode="json"),
                "document_id": page.document_id,
                "page_id": page.id,
                "public_id": span.public_id,
                "excerpt": span.exact_text,
                "char_start": span.char_start,
                "char_end": span.char_end,
            },
        )
    elif resource == "mentions" and id is None:
        data = checked(old.EntityMentionCreate)
        evidence_id = resolve(db, "knowledge_evidence_spans", data.evidence_span_id)
        span = get_or_404(db, EvidenceSpan, evidence_id)
        if (
            not 0 <= data.char_start < data.char_end <= len(span.exact_text)
            or span.exact_text[data.char_start : data.char_end] != data.mention_text
        ):
            raise HTTPException(422, "人物提及不匹配证据引句")
        revision = get_or_404(db, TextRevision, span.text_revision_id)
        page = get_or_404(db, Page, get_or_404(db, Block, revision.block_id).page_id)
        a = create_annotation(
            db,
            AnnotationCreate(
                document_id=page.document_id,
                evidence_ids=[evidence_id],
                fields={"name_form": data.mention_text},
            ),
        )
        mention = get_or_404(db, EntityMention, a.mention_id)
        response = remember(
            db,
            "knowledge_entity_mentions",
            mention,
            {**data.model_dump(mode="json"), "current_entity_id": None},
        )
    elif resource == "identity-decisions" and id is None:
        data = checked(old.IdentityDecisionCreate)
        mention = get_or_404(
            db, EntityMention, resolve(db, "knowledge_entity_mentions", data.mention_id)
        )
        a = (
            db.query(Annotation)
            .filter_by(mention_id=mention.id)
            .with_for_update()
            .first()
        )
        if not a:
            raise HTTPException(409, "请先为提及建立研究标注")
        entity_id = resolve(db, "knowledge_entities", data.entity_id)
        if data.decision.value in ("link", "uncertain") and entity_id is None:
            raise HTTPException(422, "缺少规范人物")
        if data.decision.value == "uncertain":
            mention.candidate_entity_ids = list(
                set((mention.candidate_entity_ids or []) + [entity_id])
            )
            identity = IdentityDecision(
                mention_id=mention.id,
                entity_id=entity_id,
                status=DecisionStatus.PENDING,
                basis=data.rationale,
                reviewer=data.decided_by,
            )
            db.add(identity)
            db.flush()
        else:
            if entity_id:
                entity = get_or_404(db, Entity, entity_id)
                a.fields = {**a.fields, "person": entity.canonical_name}
                a.field_states = {**a.field_states, "person": "pending"}
            elif "person" not in a.fields:
                raise HTTPException(409, "此提及尚未建立人物身份")
            review_annotation(
                db,
                a.id,
                ReviewRequest(
                    expected_version=body.get("expected_version", a.version),
                    field="person",
                    decision="approved" if data.decision.value == "link" else "pending",
                    entity_id=entity_id,
                    reason=data.rationale or "",
                    reviewer=data.decided_by or "研究者",
                ),
            )
            identity = (
                db.query(IdentityDecision)
                .filter_by(mention_id=mention.id)
                .order_by(IdentityDecision.id.desc())
                .first()
            )
            if identity is None:
                raise HTTPException(409, "没有可撤销的身份判断")
        response = remember(
            db,
            "knowledge_identity_decisions",
            identity,
            {**data.model_dump(mode="json"), "is_revoked": False},
        )
    elif resource == "identity-decisions" and action == "revoke":
        data = checked(old.IdentityDecisionRevoke)
        mapping = mapped("knowledge_identity_decisions")
        identity = get_or_404(db, IdentityDecision, mapping.new_id)
        if identity.status == DecisionStatus.SUPERSEDED:
            raise HTTPException(409, "此判断已撤销或被后续判断替代")
        a = db.query(Annotation).filter_by(mention_id=identity.mention_id).first()
        if not a:
            raise HTTPException(409, "请先核对提及的研究标注")
        review_annotation(
            db,
            a.id,
            ReviewRequest(
                expected_version=body.get("expected_version", a.version),
                field="person",
                decision="pending",
                reason=data.reason or "",
                reviewer=data.decided_by or "研究者",
            ),
        )
        mapping.payload = {
            **mapping.payload,
            "is_revoked": True,
            "revoked_reason": data.reason,
            "revoked_at": datetime.utcnow().isoformat(),
        }
        response = mapping.payload
    elif resource == "entities" and action == "roles":
        data = checked(old.PersonRoleCreate)
        if not data.evidence_span_id:
            raise HTTPException(422, "任职记录需要原文证据")
        span = get_or_404(
            db,
            EvidenceSpan,
            resolve(db, "knowledge_evidence_spans", data.evidence_span_id),
        )
        if span.validity != "current":
            raise HTTPException(409, "任职证据需要重新核验")
        obj = Assertion(
            subject_entity_id=resolve(db, "knowledge_entities", id),
            predicate="held_role",
            object_literal=data.role_title,
            valid_from=iso(data.start_date),
            valid_to=iso(data.end_date),
            source_type=SourceType.MANUAL,
            extra_metadata=data.model_dump(mode="json"),
        )
        db.add(obj)
        db.flush()
        db.add(
            AssertionEvidence(
                assertion_id=obj.id,
                evidence_span_id=span.id,
                relation=EvidenceRelation.SUPPORTS,
            )
        )
        response = remember(
            db,
            "knowledge_person_roles",
            obj,
            {
                **data.model_dump(mode="json"),
                "person_entity_id": id,
                "requires_review": True,
            },
        )
    elif resource == "events" and action == "participants":
        data = checked(old.EventParticipantCreate)
        if not data.evidence_span_id:
            raise HTTPException(422, "参与角色需要原文证据")
        span = get_or_404(
            db,
            EvidenceSpan,
            resolve(db, "knowledge_evidence_spans", data.evidence_span_id),
        )
        entity = get_or_404(
            db, Entity, resolve(db, "knowledge_entities", data.entity_id)
        )
        event = get_or_404(db, Event, resolve(db, "knowledge_events", id))
        names = [entity.canonical_name, *json.loads(entity.alternative_names or "[]")]
        form = next((name for name in names if name in span.exact_text), None)
        if not form:
            raise HTTPException(
                422, "证据中未找到参与者姓名，请在工作台建立并复核人物提及"
            )
        revision = get_or_404(db, TextRevision, span.text_revision_id)
        page = get_or_404(db, Page, get_or_404(db, Block, revision.block_id).page_id)
        obj = create_annotation(
            db,
            AnnotationCreate(
                document_id=page.document_id,
                evidence_ids=[span.id],
                fields={
                    "name_form": form,
                    "person": entity.canonical_name,
                    "event": event.title,
                    "role": data.role.value,
                },
            ),
        )
        obj.event_id = event.id
        get_or_404(db, EntityMention, obj.mention_id).candidate_entity_ids = [entity.id]
        response = remember(
            db,
            "knowledge_event_participants",
            obj,
            {**data.model_dump(mode="json"), "event_id": id, "requires_review": True},
        )
    elif resource == "reviews" and id is None:
        data = checked(old.ReviewDecisionCreate)
        targets = {
            "assertion": (
                "knowledge_assertions",
                Assertion,
                ReviewTargetType.ASSERTION,
            ),
            "event": ("knowledge_events", Event, ReviewTargetType.EVENT),
            "mention": (
                "knowledge_entity_mentions",
                EntityMention,
                ReviewTargetType.ENTITY_MENTION,
            ),
            "identity_decision": (
                "knowledge_identity_decisions",
                IdentityDecision,
                ReviewTargetType.IDENTITY_DECISION,
            ),
        }
        if data.target_type not in targets:
            raise HTTPException(422, "此复核目标需要使用研究工作台接口")
        table, model, kind = targets[data.target_type]
        target_id = resolve(db, table, data.target_id)
        get_or_404(db, model, target_id)
        previous = (
            db.query(ReviewDecision)
            .filter_by(target_type=kind, target_id=target_id)
            .order_by(ReviewDecision.id.desc())
            .first()
        )
        if (
            body.get("expected_previous_review_id") is not None
            and (previous.id if previous else 0) != body["expected_previous_review_id"]
        ):
            raise HTTPException(409, "审核记录已更新")
        obj = ReviewDecision(
            target_type=kind,
            target_id=target_id,
            decision={
                "confirm": ReviewDecisionType.APPROVED,
                "reject": ReviewDecisionType.REJECTED,
                "needs_verification": ReviewDecisionType.NEEDS_REVISION,
            }[data.decision.value],
            reason=data.rationale,
            reviewer=data.reviewer or "研究者",
            previous_decision_id=previous.id if previous else None,
        )
        db.add(obj)
        db.flush()
        # Preserve the legacy contract (audit only). Canonical field acceptance
        # remains explicit in /workbench/annotations/{id}/reviews.
        response = remember(
            db, "knowledge_review_decisions", obj, data.model_dump(mode="json")
        )
    elif resource == "events" and id is None:
        data = checked(old.EventCreate)
        obj = Event(
            event_type=data.event_type.value,
            title=data.title,
            summary=data.summary,
            date_start=iso(data.start_date),
            date_end=iso(data.end_date),
            notes=data.date_uncertainty_note,
            location_entity_id=resolve(db, "knowledge_entities", data.place_entity_id),
        )
        db.add(obj)
        db.flush()
        if data.evidence_span_id:
            eid = resolve(db, "knowledge_evidence_spans", data.evidence_span_id)
            span = get_or_404(db, EvidenceSpan, eid)
            rev = get_or_404(db, TextRevision, span.text_revision_id)
            page = get_or_404(db, Page, get_or_404(db, Block, rev.block_id).page_id)
            a = create_annotation(
                db,
                AnnotationCreate(
                    document_id=page.document_id,
                    evidence_ids=[eid],
                    fields={"event": data.title},
                ),
            )
            a.event_id = obj.id
        response = remember(
            db,
            "knowledge_events",
            obj,
            {**data.model_dump(mode="json"), "participants": [], "mentions": []},
        )
    elif resource == "assertions" and id is None:
        data = checked(old.AssertionCreate)
        if not data.evidence:
            raise HTTPException(422, "研究判断必须提供原文证据")
        obj = Assertion(
            subject_entity_id=resolve(db, "knowledge_entities", data.subject_entity_id),
            predicate=data.predicate.value,
            object_entity_id=resolve(db, "knowledge_entities", data.object_entity_id),
            object_literal=data.object_literal,
            source_type=SourceType.MANUAL,
            extra_metadata=data.model_dump(mode="json"),
        )
        db.add(obj)
        db.flush()
        links = []
        for item in data.evidence:
            span = get_or_404(
                db,
                EvidenceSpan,
                resolve(db, "knowledge_evidence_spans", item.evidence_span_id),
            )
            if span.validity != "current":
                raise HTTPException(409, "证据版本待核验")
            link = AssertionEvidence(
                assertion_id=obj.id,
                evidence_span_id=span.id,
                relation={
                    "supports": EvidenceRelation.SUPPORTS,
                    "contradicts": EvidenceRelation.CONTRADICTS,
                    "mentions_only": EvidenceRelation.MENTIONS,
                }[item.stance.value],
            )
            db.add(link)
            db.flush()
            links.append(
                {
                    "id": link.id,
                    "assertion_id": obj.id,
                    **item.model_dump(mode="json"),
                    "created_at": datetime.utcnow().isoformat(),
                }
            )
        response = remember(
            db,
            "knowledge_assertions",
            obj,
            {**data.model_dump(mode="json"), "evidence_links": links},
        )
    elif resource == "corpora" and id is None:
        data = checked(old.CorpusCreate)
        obj = ResearchCorpus(name=data.name, metadata_json=data.model_dump(mode="json"))
        db.add(obj)
        db.flush()
        response = remember(
            db,
            "knowledge_corpora",
            obj,
            {**data.model_dump(mode="json"), "documents": []},
        )
    elif resource == "corpora" and method == "PATCH":
        data = checked(old.CorpusUpdate)
        mapping = mapped("knowledge_corpora")
        obj = get_or_404(db, ResearchCorpus, mapping.new_id)
        if data.name:
            obj.name = data.name
        obj.metadata_json = {
            **(obj.metadata_json or {}),
            **data.model_dump(mode="json", exclude_unset=True),
        }
        mapping.payload = {
            **mapping.payload,
            **data.model_dump(mode="json", exclude_unset=True),
        }
        response = mapping.payload
    elif resource == "corpora" and action == "documents":
        data = checked(old.CorpusDocumentAttach)
        get_or_404(db, Document, data.document_id)
        if db.query(CorpusMembership).filter_by(document_id=data.document_id).first():
            raise HTTPException(409, "文档已经属于一个语料集合")
        obj = CorpusMembership(
            corpus_id=resolve(db, "knowledge_corpora", id),
            document_id=data.document_id,
            metadata_json=data.model_dump(mode="json"),
        )
        db.add(obj)
        db.flush()
        response = remember(
            db,
            "knowledge_corpus_documents",
            obj,
            {**data.model_dump(mode="json"), "corpus_id": id},
        )
    else:
        raise HTTPException(
            409,
            {
                "message": "此操作需要逐字段审核，请使用新的研究工作台接口",
                "canonical_base": "/api/v2/workbench",
            },
        )
    db.commit()
    return response
