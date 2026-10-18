"""Version-pinned paragraph indexing. Keyword persistence precedes embedding calls."""

import json
import re
from datetime import datetime
from uuid import uuid4
from app.models import *
from app.rag.embedding import EmbeddingService
from app.rag.schemas import IndexStatusSchema
from app.rag.tokenizer import tokenize
from app.workbench.versioning import current_revision, digest
from app.workbench.images import freeze_image

SKIP_LABELS = frozenset({"number", "image", "header_image", "footer_image", "chart"})
MAX_CHARS = 3000


def block_text(block):
    return (block.ocr_text_corrected or block.ocr_text_raw or "").strip()


def segments_valid(db, chunk):
    if not chunk.segments:
        return False
    for part in chunk.segments:
        block = db.get(Block, part["block_id"])
        revision = db.get(TextRevision, part["revision_id"])
        if not block or block.retired or not revision:
            return False
        field = {
            TextType.OCR_RAW: "ocr_text_raw",
            TextType.OCR_CORRECTED: "ocr_text_corrected",
            TextType.MODERN_ENGLISH: "modern_english",
            TextType.TRANSLATION_ZH: "translation_zh",
        }.get(revision.text_type)
        if not field or (getattr(block, field) or "") != revision.content:
            return False
        if revision.content[part["start"] : part["end"]] != part["quote"]:
            return False
        if part.get("evidence_id"):
            evidence = db.get(EvidenceSpan, part["evidence_id"])
            if not evidence or evidence.validity != "current":
                return False
    return True


class RagIndexer:
    def __init__(self, db, embedder=None):
        self.db = db
        self.embedder = embedder or EmbeddingService()

    def _specs(self, document_id=None):
        query = (
            self.db.query(Block)
            .join(Page)
            .join(Document, Document.id == Page.document_id)
            .filter(Block.retired.is_(False), Document.archived_at.is_(None))
            .order_by(Page.page_number, Block.block_index)
        )
        if document_id:
            query = query.filter(Page.document_id == document_id)
        blocks = {
            b.id: b
            for b in query.all()
            if b.block_label not in SKIP_LABELS and block_text(b)
        }
        groups = []
        covered = {}
        units = self.db.query(SourceUnit).join(ArchivalMetadata)
        if document_id:
            units = units.filter(ArchivalMetadata.document_id == document_id)
        for unit in units:
            parts = []
            valid = True
            for span in unit.spans:
                if span.block_id not in blocks:
                    valid = False
                    break
                revision = (
                    self.db.get(TextRevision, span.revision_id)
                    if span.revision_id
                    else current_revision(self.db, blocks[span.block_id])
                )
                if current_revision(self.db, blocks[span.block_id]).id != revision.id:
                    valid = False
                    break
                parts.append(
                    (
                        blocks[span.block_id],
                        revision,
                        span.char_start or 0,
                        (
                            span.char_end
                            if span.char_end is not None
                            else len(revision.content)
                        ),
                    )
                )
            if valid and parts:
                groups.append((unit, parts, "original"))
                for b, revision, start, end in parts:
                    covered.setdefault(b.id, []).append((start, end))
        for id, b in blocks.items():
            revision = current_revision(self.db, b)
            cursor = 0
            for start, end in sorted(covered.get(id, [])):
                if cursor < start:
                    groups.append((None, [(b, revision, cursor, start)], "original"))
                cursor = max(cursor, end)
            if cursor < len(revision.content):
                groups.append(
                    (None, [(b, revision, cursor, len(revision.content))], "original")
                )
            # A block translation has no reliable character alignment with a
            # partial original span. Keep its own complete, explicitly temporary chunk.
            if b.translation_zh:
                translated = current_revision(self.db, b, "translation_zh")
                groups.append(
                    (None, [(b, translated, 0, len(translated.content))], "translation")
                )
        specs = []
        for unit, parts, field in groups:
            segments = []
            for b, original, start, end in parts:
                revision = original
                # Paragraph boundaries, with bounded fallback for very long paragraphs.
                for match in re.finditer(
                    r"[^\n]+(?:\n(?!\n)[^\n]+)*", revision.content[start:end]
                ):
                    left = start + match.start()
                    right = start + match.end()
                    for offset in range(left, right, MAX_CHARS):
                        segments.append(
                            {
                                "block_id": b.id,
                                "revision_id": revision.id,
                                "start": offset,
                                "end": min(offset + MAX_CHARS, right),
                                "quote": revision.content[
                                    offset : min(offset + MAX_CHARS, right)
                                ],
                            }
                        )
            # Join adjacent short block fragments only within an explicitly segmented source unit.
            batches = []
            batch = []
            length = 0
            for segment in segments:
                if batch and (
                    not unit or length + len(segment["quote"]) + 2 > MAX_CHARS
                ):
                    batches.append(batch)
                    batch = []
                    length = 0
                batch.append(segment)
                length += len(segment["quote"]) + 2
            if batch:
                batches.append(batch)
            for batch in batches:
                b = blocks[batch[0]["block_id"]]
                page = self.db.get(Page, b.page_id)
                content = "\n\n".join(p["quote"] for p in batch)
                approved = all(
                    self.db.get(TextRevision, p["revision_id"]).review_state
                    == "approved"
                    for p in batch
                ) and (
                    unit is None
                    or unit.segmentation_status == SegmentationStatus.APPROVED
                )
                key = digest(
                    json.dumps(
                        [unit.id if unit else None, field, batch, approved],
                        sort_keys=True,
                    )
                )
                specs.append(
                    dict(
                        content=content,
                        content_hash=key,
                        document_id=page.document_id,
                        page_id=page.id,
                        block_id=b.id,
                        source_unit_id=unit.id if unit else None,
                        segments=batch,
                        review_state="approved" if approved else "pending",
                        content_type=(
                            "source_paragraph" if unit else "ocr_block_temporary"
                        ),
                        content_language="zh" if field == "translation" else "en",
                    )
                )
        return specs

    def status(self, document_id=None):
        # Coverage counts physical current chunks/blocks without creating revisions on reads.
        base = (
            self.db.query(Block)
            .join(Page)
            .join(Document, Document.id == Page.document_id)
            .filter(Block.retired.is_(False), Document.archived_at.is_(None))
        )
        if document_id:
            base = base.filter(Page.document_id == document_id)
        eligible = {
            b.id for b in base if b.block_label not in SKIP_LABELS and block_text(b)
        }
        query = self.db.query(SearchChunk).filter(
            SearchChunk.status == ChunkStatus.INDEXED
        )
        if document_id:
            query = query.filter(SearchChunk.document_id == document_id)
        chunks = [c for c in query if segments_valid(self.db, c)]
        covered = {p["block_id"] for c in chunks for p in c.segments}
        return IndexStatusSchema(
            eligible=len(eligible),
            indexed=len(eligible & covered),
            pending=len(eligible - covered),
            vector_pending=sum(
                c.embedding is None or c.embedding_model != self.embedder.model
                for c in chunks
            ),
            embedding_model=self.embedder.model,
        )

    async def index(self, document_id=None, progress=None):
        # Serialize index builders over the same documents before publishing keyword chunks.
        docs = (
            self.db.query(Document)
            .filter(Document.archived_at.is_(None))
            .order_by(Document.id)
        )
        if document_id:
            docs = docs.filter(Document.id == document_id)
        locked_docs = docs.with_for_update().all()
        if document_id and not locked_docs:
            return {"indexed": 0, "total": 0, "vector_failed": 0}
        specs = self._specs(document_id)
        existing_query = self.db.query(SearchChunk).filter(
            SearchChunk.document_id.in_([d.id for d in locked_docs])
        )
        if document_id:
            existing_query = existing_query.filter_by(document_id=document_id)
        existing = {c.content_hash: c for c in existing_query}
        active = set()
        chunks = []
        for spec in specs:
            chunk = existing.get(spec["content_hash"])
            if not chunk:
                chunk = SearchChunk(**spec)
                self.db.add(chunk)
                self.db.flush()
                # Stable evidence anchors are created for each source segment.
                enriched = []
                for original_part in chunk.segments:
                    part = dict(original_part)
                    revision = self.db.get(TextRevision, part["revision_id"])
                    block = self.db.get(Block, part["block_id"])
                    page = self.db.get(Page, block.page_id)
                    ev = (
                        self.db.query(EvidenceSpan)
                        .filter_by(
                            text_revision_id=revision.id,
                            char_start=part["start"],
                            char_end=part["end"],
                            validity="current",
                        )
                        .first()
                    )
                    if not ev:
                        snapshot, image_version = freeze_image(page)
                        ev = EvidenceSpan(
                            text_revision_id=revision.id,
                            page_id=page.id,
                            char_start=part["start"],
                            char_end=part["end"],
                            exact_text=part["quote"],
                            validity="current",
                            bbox=block.bbox,
                            image_width=page.width,
                            image_height=page.height,
                            image_version=image_version,
                            image_snapshot_path=snapshot,
                            public_id=str(uuid4()),
                            location_precision=LocationPrecision.BLOCK,
                        )
                        self.db.add(ev)
                        self.db.flush()
                    part["evidence_id"] = ev.id
                    enriched.append(part)
                chunk.segments = enriched
            chunk.search_text = tokenize(chunk.content)
            chunk.status = ChunkStatus.INDEXED
            chunk.indexed_at = datetime.utcnow()
            active.add(chunk.id)
            chunks.append(chunk)
        for chunk in existing.values():
            if chunk.id not in active:
                chunk.status = ChunkStatus.INVALIDATED
        self.db.commit()  # keyword search survives a provider outage
        pending = [
            c.id
            for c in chunks
            if c.embedding is None or c.embedding_model != self.embedder.model
        ]
        failed = 0
        done = 0
        from app.config import settings

        for offset in range(0, len(pending), max(1, settings.embedding_batch_size)):
            batch = [
                self.db.get(SearchChunk, id)
                for id in pending[
                    offset : offset + max(1, settings.embedding_batch_size)
                ]
            ]
            try:
                vectors = await self.embedder.embed([c.content for c in batch])
                if len(vectors) != len(batch) or any(len(v) != 1024 for v in vectors):
                    raise ValueError("向量数量或维度不匹配")
                self.db.expire_all()
                for chunk, vector in zip(batch, vectors):
                    if chunk.status == ChunkStatus.INDEXED and segments_valid(
                        self.db, chunk
                    ):
                        chunk.embedding = vector
                        chunk.embedding_model = self.embedder.model
                self.db.commit()
            except Exception:
                self.db.rollback()
                failed += len(batch)
            done += len(batch)
            if progress:
                progress(done, len(pending))
        return {"indexed": len(chunks), "total": len(chunks), "vector_failed": failed}
