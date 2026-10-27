"""Deprecated v2 URLs: old IDs resolve explicitly through the migration archive.

Canonical workflow URLs live under /workbench and never reinterpret numeric IDs.
Legacy writes are translated into canonical records. Field-review-only actions
return an actionable conflict rather than bypassing the review workflow.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models import LegacyMapping, Entity, EvidenceSpan
from app.workbench.service import locator, serialize, get_or_404
from app.workbench.api import overview

router = APIRouter(tags=["legacy-knowledge-compatibility"])


@router.get("/evidence-spans/{id}/locator")
def old_locator(id: int, db: Session = Depends(get_db)):
    mapping = (
        db.query(LegacyMapping)
        .filter_by(source_table="knowledge_evidence_spans", old_id=id)
        .first()
    )
    if not mapping or not mapping.new_id:
        raise HTTPException(404, "旧证据不存在")
    evidence = locator(db, get_or_404(db, EvidenceSpan, mapping.new_id))
    old = dict(mapping.payload)
    return {
        "evidence_span": old,
        "page_number": evidence["page_number"],
        "bbox": evidence["bbox"],
        "viewer_path": evidence["viewer_path"],
        "validity": evidence["validity"],
        "canonical_evidence_id": evidence["id"],
    }


@router.api_route(
    "/{resource}/{id}/{action}", methods=["GET", "POST", "PATCH", "DELETE"]
)
@router.api_route("/{resource}/{id}", methods=["GET", "POST", "PATCH", "DELETE"])
@router.api_route("/{resource}", methods=["GET", "POST"])
async def legacy(
    request: Request,
    resource: str,
    id: int | None = None,
    action: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    tables = {
        "entities": "knowledge_entities",
        "events": "knowledge_events",
        "evidence-spans": "knowledge_evidence_spans",
        "assertions": "knowledge_assertions",
        "mentions": "knowledge_entity_mentions",
        "identity-decisions": "knowledge_identity_decisions",
        "corpora": "knowledge_corpora",
        "reviews": "knowledge_review_decisions",
    }
    if resource not in tables:
        raise HTTPException(404, "接口不存在")
    if request.method != "GET":
        from app.workbench.compat_writes import write_legacy

        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(422, "请求必须是有效 JSON")
        return write_legacy(db, resource, id, action, body, request.method)
    if page < 1 or not 1 <= page_size <= 100:
        raise HTTPException(422, "分页参数无效")
    query = db.query(LegacyMapping).filter_by(source_table=tables[resource])

    def payload(mapping):
        value = dict(mapping.payload)
        value["canonical_id"] = mapping.new_id
        value["archived"] = not value.get("_canonical_write", False)
        if resource == "entities":
            e = db.get(Entity, mapping.new_id) if mapping.new_id else None
            if e:
                value["canonical_name"] = e.canonical_name
            value["names"] = [
                m.payload
                for m in db.query(LegacyMapping).filter_by(
                    source_table="knowledge_entity_names"
                )
                if m.payload.get("entity_id") == mapping.old_id
            ]
            value["mentions"] = [
                m.payload
                for m in db.query(LegacyMapping).filter_by(
                    source_table="knowledge_entity_mentions"
                )
                if m.payload.get("current_entity_id") == mapping.old_id
            ]
            value["roles"] = [
                m.payload
                for m in db.query(LegacyMapping).filter_by(
                    source_table="knowledge_person_roles"
                )
                if m.payload.get("person_entity_id") == mapping.old_id
            ]
            value["identity_decisions"] = [
                m.payload
                for m in db.query(LegacyMapping).filter_by(
                    source_table="knowledge_identity_decisions"
                )
                if m.payload.get("entity_id") == mapping.old_id
            ]
        elif resource == "events":
            value["participants"] = [
                m.payload
                for m in db.query(LegacyMapping).filter_by(
                    source_table="knowledge_event_participants"
                )
                if m.payload.get("event_id") == mapping.old_id
            ]
        elif resource == "assertions":
            value["evidence_links"] = [
                m.payload
                for m in db.query(LegacyMapping).filter_by(
                    source_table="knowledge_assertion_evidence"
                )
                if m.payload.get("assertion_id") == mapping.old_id
            ]
        elif resource == "corpora":
            value["documents"] = [
                m.payload
                for m in db.query(LegacyMapping).filter_by(
                    source_table="knowledge_corpus_documents"
                )
                if m.payload.get("corpus_id") == mapping.old_id
            ]
        return value

    if id is not None:
        mapping = query.filter_by(old_id=id).first()
        if not mapping:
            raise HTTPException(404, "旧记录不存在")
        return payload(mapping)
    return {
        "items": [
            payload(m)
            for m in query.order_by(LegacyMapping.old_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ],
        "total": query.count(),
        "page": page,
        "page_size": page_size,
    }
