"""Lossless legacy archive plus canonical projections. Never writes legacy tables."""

import json
from datetime import date
from uuid import uuid4
from sqlalchemy import MetaData, Table, inspect, select
from app.models import (
    Entity,
    EntityType,
    TextRevision,
    TextType,
    EvidenceSpan,
    EntityMention,
    IdentityDecision,
    DecisionStatus,
    Event,
    Participation,
    Assertion,
    SourceType,
    AssertionEvidence,
    EvidenceRelation,
    ReviewDecision,
    ReviewTargetType,
    ReviewDecisionType,
    Page,
    Block,
    ArchivalMetadata,
    SourceUnit,
    SourceUnitType,
    SourceUnitSpan,
    EventMention,
    Annotation,
    LegacyMapping,
    ResearchCorpus,
    CorpusMembership,
)
from app.workbench.versioning import digest


def iso(value):
    try:
        return date.fromisoformat(value) if value else None
    except (ValueError, TypeError):
        return None


def migrate_legacy(db):
    names = sorted(
        n for n in inspect(db.bind).get_table_names() if n.startswith("knowledge_")
    )
    rows = {}
    for name in names:
        table = Table(name, MetaData(), autoload_with=db.bind)
        rows[name] = list(db.execute(select(table)).mappings())
        for row in rows[name]:
            if (
                not db.query(LegacyMapping)
                .filter_by(source_table=name, old_id=row["id"])
                .first()
            ):
                db.add(
                    LegacyMapping(
                        source_table=name,
                        old_id=row["id"],
                        payload=json.loads(json.dumps(dict(row), default=str)),
                    )
                )
    db.flush()
    mappings = {(m.source_table, m.old_id): m for m in db.query(LegacyMapping)}

    def target(table, old_id):
        m = mappings.get((table, old_id))
        return m.new_id if m else None

    def project(table, row, model, **kwargs):
        m = mappings[(table, row["id"])]
        if m.new_id:
            return db.get(model, m.new_id)
        obj = model(**kwargs)
        db.add(obj)
        db.flush()
        m.target_table, m.new_id = model.__tablename__, obj.id
        return obj

    for r in rows.get("knowledge_corpora", []):
        project(
            "knowledge_corpora",
            r,
            ResearchCorpus,
            name=r["name"],
            metadata_json=mappings[("knowledge_corpora", r["id"])].payload,
        )
    for r in rows.get("knowledge_corpus_documents", []):
        project(
            "knowledge_corpus_documents",
            r,
            CorpusMembership,
            document_id=r["document_id"],
            corpus_id=target("knowledge_corpora", r["corpus_id"]),
            metadata_json=mappings[("knowledge_corpus_documents", r["id"])].payload,
        )
        if (
            not db.query(ArchivalMetadata)
            .filter_by(document_id=r["document_id"])
            .first()
        ):
            db.add(
                ArchivalMetadata(
                    document_id=r["document_id"],
                    collection_name=r["canonical_title"],
                    archival_reference=r["archive_id"],
                    repository=r["source_institution"],
                    coverage_date_start=iso(r["date_start"]),
                    coverage_date_end=iso(r["date_end"]),
                    notes=r["page_mapping_note"],
                )
            )
    for r in rows.get("knowledge_entities", []):
        aliases = [
            n["name"]
            for n in rows.get("knowledge_entity_names", [])
            if n["entity_id"] == r["id"]
        ]
        project(
            "knowledge_entities",
            r,
            Entity,
            entity_type=EntityType(r["entity_type"]),
            canonical_name=r["canonical_name"],
            alternative_names=json.dumps(aliases, ensure_ascii=False),
            notes=r["notes"],
            external_id=r["external_id"],
        )
    for r in rows.get("knowledge_entity_names", []):
        mapping = mappings[("knowledge_entity_names", r["id"])]
        mapping.target_table = "entities"
        mapping.new_id = target("knowledge_entities", r["entity_id"])
    for r in rows.get("knowledge_evidence_spans", []):
        m = mappings[("knowledge_evidence_spans", r["id"])]
        if m.new_id:
            continue
        block = db.get(Block, r["block_id"])
        field = {
            "ocr_raw": "ocr_text_raw",
            "ocr_auto_corrected": "ocr_text_corrected",
            "ocr_human_corrected": "ocr_text_corrected",
            "modern_english": "modern_english",
            "translation_zh": "translation_zh",
        }[r["text_version"]]
        text = getattr(block, field) or ""
        valid = (
            0 <= r["char_start"] < r["char_end"] <= len(text)
            and text[r["char_start"] : r["char_end"]] == r["excerpt"]
        )
        # A matching excerpt alone does not establish the complete historical text.
        # Reuse a pre-existing revision only when its exact slice matches.
        typ = {
            "ocr_text_raw": TextType.OCR_RAW,
            "ocr_text_corrected": TextType.OCR_CORRECTED,
            "modern_english": TextType.MODERN_ENGLISH,
            "translation_zh": TextType.TRANSLATION_ZH,
        }[field]
        revision = (
            db.query(TextRevision)
            .filter_by(block_id=block.id, text_type=typ)
            .order_by(TextRevision.id.desc())
            .first()
        )
        proven = (
            revision
            and revision.content[r["char_start"] : r["char_end"]] == r["excerpt"]
        )
        if not proven:
            revision = TextRevision(
                block_id=block.id,
                text_type=TextType.MANUAL_TRANSCRIPTION,
                content=r["excerpt"],
                content_hash=digest(r["excerpt"]),
                author="legacy migration",
                author_type="excerpt_only",
                review_state="pending",
            )
            db.add(revision)
            db.flush()
        span = project(
            "knowledge_evidence_spans",
            r,
            EvidenceSpan,
            text_revision_id=revision.id,
            page_id=r["page_id"],
            char_start=r["char_start"] if proven else 0,
            char_end=r["char_end"] if proven else len(r["excerpt"]),
            exact_text=r["excerpt"],
            validity="current" if proven and valid else "legacy_unverified",
            public_id=r["public_id"],
            bbox=block.bbox,
        )
    for r in rows.get("knowledge_entity_mentions", []):
        entity_id = target("knowledge_entities", r["current_entity_id"])
        mention = project(
            "knowledge_entity_mentions",
            r,
            EntityMention,
            evidence_span_id=target("knowledge_evidence_spans", r["evidence_span_id"]),
            entity_id=entity_id,
            original_form=r["mention_text"],
        )
        if not db.query(Annotation).filter_by(mention_id=mention.id).first():
            span = db.get(EvidenceSpan, mention.evidence_span_id)
            block = db.get(Block, db.get(TextRevision, span.text_revision_id).block_id)
            page = db.get(Page, block.page_id)
            fields = {"name_form": r["mention_text"]}
            if entity_id:
                fields["person"] = db.get(Entity, entity_id).canonical_name
            db.add(
                Annotation(
                    document_id=page.document_id,
                    mention_id=mention.id,
                    evidence_ids=[span.id],
                    fields=fields,
                    field_states={k: "pending" for k in fields},
                    status="needs_validation",
                )
            )
    for r in rows.get("knowledge_events", []):
        project(
            "knowledge_events",
            r,
            Event,
            event_type=r["event_type"],
            title=r["title"],
            summary=r["summary"],
            date_start=iso(r["start_date"]),
            date_end=iso(r["end_date"]),
            notes=r["date_uncertainty_note"],
            location_entity_id=target("knowledge_entities", r["place_entity_id"]),
        )
    for r in rows.get("knowledge_event_participants", []):
        project(
            "knowledge_event_participants",
            r,
            Participation,
            event_id=target("knowledge_events", r["event_id"]),
            entity_id=target("knowledge_entities", r["entity_id"]),
            role=r["role"],
            notes=json.dumps(
                mappings[("knowledge_event_participants", r["id"])].payload,
                ensure_ascii=False,
            ),
        )
    for r in rows.get("knowledge_event_mentions", []):
        eid = target("knowledge_evidence_spans", r["evidence_span_id"])
        span = db.get(EvidenceSpan, eid)
        block = db.get(Block, db.get(TextRevision, span.text_revision_id).block_id)
        page = db.get(Page, block.page_id)
        meta = (
            db.query(ArchivalMetadata).filter_by(document_id=page.document_id).first()
        )
        if not meta:
            meta = ArchivalMetadata(document_id=page.document_id)
            db.add(meta)
            db.flush()
        unit = SourceUnit(
            archival_metadata_id=meta.id,
            unit_type=SourceUnitType.OTHER,
            title="历史记录迁移",
        )
        m = mappings[("knowledge_event_mentions", r["id"])]
        if not m.new_id:
            db.add(unit)
            db.flush()
            project(
                "knowledge_event_mentions",
                r,
                EventMention,
                source_unit_id=unit.id,
                event_id=target("knowledge_events", r["event_id"]),
                summary=r["trigger_text"] or span.exact_text,
                notes=f"evidence:{eid}",
            )
            db.add(
                SourceUnitSpan(
                    source_unit_id=unit.id,
                    block_id=block.id,
                    revision_id=span.text_revision_id,
                    reading_order=0,
                    char_start=span.char_start,
                    char_end=span.char_end,
                )
            )
            fields = {
                "event": db.get(Event, target("knowledge_events", r["event_id"])).title
            }
            db.add(
                Annotation(
                    document_id=page.document_id,
                    source_unit_id=unit.id,
                    event_id=target("knowledge_events", r["event_id"]),
                    evidence_ids=[eid],
                    fields=fields,
                    field_states={"event": "pending"},
                    status="needs_validation",
                )
            )
    for r in rows.get("knowledge_assertions", []):
        project(
            "knowledge_assertions",
            r,
            Assertion,
            subject_entity_id=target("knowledge_entities", r["subject_entity_id"]),
            predicate=r["predicate"],
            object_entity_id=target("knowledge_entities", r["object_entity_id"]),
            object_literal=r["object_literal"],
            source_type=(
                SourceType.MANUAL
                if r["source_type"] == "human"
                else SourceType.EXTRACTED
            ),
            extra_metadata=mappings[("knowledge_assertions", r["id"])].payload,
        )
    for r in rows.get("knowledge_assertion_evidence", []):
        project(
            "knowledge_assertion_evidence",
            r,
            AssertionEvidence,
            assertion_id=target("knowledge_assertions", r["assertion_id"]),
            evidence_span_id=target("knowledge_evidence_spans", r["evidence_span_id"]),
            relation={
                "supports": EvidenceRelation.SUPPORTS,
                "contradicts": EvidenceRelation.CONTRADICTS,
                "mentions_only": EvidenceRelation.MENTIONS,
            }[r["stance"]],
        )
    for r in rows.get("knowledge_identity_decisions", []):
        entity_id = target("knowledge_entities", r["entity_id"])
        if entity_id:
            project(
                "knowledge_identity_decisions",
                r,
                IdentityDecision,
                mention_id=target("knowledge_entity_mentions", r["mention_id"]),
                entity_id=entity_id,
                basis=r["rationale"],
                status=(
                    DecisionStatus.SUPERSEDED
                    if r["is_revoked"]
                    else (
                        DecisionStatus.APPROVED
                        if r["decision"] == "link"
                        else DecisionStatus.PENDING
                    )
                ),
                reviewer=r["decided_by"],
                notes=json.dumps(
                    mappings[("knowledge_identity_decisions", r["id"])].payload,
                    ensure_ascii=False,
                ),
            )
    target_types = {
        "assertion": ("knowledge_assertions", ReviewTargetType.ASSERTION),
        "event": ("knowledge_events", ReviewTargetType.EVENT),
        "mention": ("knowledge_entity_mentions", ReviewTargetType.ENTITY_MENTION),
    }
    for r in rows.get("knowledge_review_decisions", []):
        pair = target_types.get(r["target_type"])
        if pair and target(pair[0], r["target_id"]):
            project(
                "knowledge_review_decisions",
                r,
                ReviewDecision,
                target_type=pair[1],
                target_id=target(pair[0], r["target_id"]),
                decision={
                    "confirm": ReviewDecisionType.APPROVED,
                    "reject": ReviewDecisionType.REJECTED,
                    "needs_verification": ReviewDecisionType.NEEDS_REVISION,
                }[r["decision"]],
                reason=r["rationale"],
                reviewer=r["reviewer"] or "legacy",
            )
    for r in rows.get("knowledge_person_roles", []):
        assertion = project(
            "knowledge_person_roles",
            r,
            Assertion,
            subject_entity_id=target("knowledge_entities", r["person_entity_id"]),
            predicate="held_role",
            object_literal=r["role_title"],
            valid_from=iso(r["start_date"]),
            valid_to=iso(r["end_date"]),
            source_type=SourceType.MANUAL,
            extra_metadata=mappings[("knowledge_person_roles", r["id"])].payload,
        )
        evidence_id = target("knowledge_evidence_spans", r["evidence_span_id"])
        if (
            evidence_id
            and not db.query(AssertionEvidence)
            .filter_by(assertion_id=assertion.id, evidence_span_id=evidence_id)
            .first()
        ):
            db.add(
                AssertionEvidence(
                    assertion_id=assertion.id,
                    evidence_span_id=evidence_id,
                    relation=EvidenceRelation.SUPPORTS,
                )
            )
    for r in rows.get("knowledge_identity_decisions", []):
        new_id = target("knowledge_identity_decisions", r["id"])
        if new_id and r.get("previous_decision_id"):
            db.get(IdentityDecision, new_id).previous_decision_id = target(
                "knowledge_identity_decisions", r["previous_decision_id"]
            )
    # Unlink decisions with no entity and unknown review targets remain archived
    # with their complete payload rather than fabricated canonical foreign keys.
