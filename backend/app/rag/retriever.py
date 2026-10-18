"""Scoped hybrid retrieval with independent keyword search and explicit degradation."""

import json
import re
from sqlalchemy import func, or_
from sqlalchemy.orm import defer
from app.models import *
from app.rag.embedding import EmbeddingService
from app.rag.indexer import segments_valid
from app.rag.schemas import SearchHitSchema
from app.rag.tokenizer import tokenize, jieba
from app.workbench.schemas import ResearchScope
from app.workbench.service import locator

RRF_K = 60


class HybridRetriever:
    def __init__(self, db, embedder=None):
        self.db = db
        self.embedder = embedder or EmbeddingService()
        self.warnings = []

    def _base(self, scope):
        query = (
            self.db.query(SearchChunk)
            .join(Document, Document.id == SearchChunk.document_id)
            .filter(
                Document.archived_at.is_(None),
                SearchChunk.status == ChunkStatus.INDEXED,
            )
        )
        if scope.mode == "verified":
            query = query.filter(SearchChunk.review_state == "approved")
        if scope.document_id:
            query = query.filter(SearchChunk.document_id == scope.document_id)
        if scope.document_ids:
            query = query.filter(SearchChunk.document_id.in_(scope.document_ids))
        if scope.corpus_id:
            query = query.filter(
                SearchChunk.document_id.in_(
                    self.db.query(CorpusMembership.document_id).filter_by(
                        corpus_id=scope.corpus_id
                    )
                )
            )
        if scope.date_start or scope.date_end or scope.unit_type:
            query = query.join(SourceUnit, SourceUnit.id == SearchChunk.source_unit_id)
            if scope.date_start:
                query = query.filter(
                    func.coalesce(
                        SourceUnit.normalized_date_end, SourceUnit.normalized_date_start
                    )
                    >= scope.date_start
                )
            if scope.date_end:
                query = query.filter(SourceUnit.normalized_date_start <= scope.date_end)
            if scope.unit_type:
                try:
                    unit_type = SourceUnitType(scope.unit_type)
                except ValueError:
                    from fastapi import HTTPException

                    raise HTTPException(422, "未知文书类型")
                query = query.filter(SourceUnit.unit_type == unit_type)
        if scope.entity_id:
            evidence_ids = {
                row[0]
                for row in self.db.query(EntityMention.evidence_span_id).filter_by(
                    entity_id=scope.entity_id
                )
            }
            for annotation in self.db.query(Annotation):
                if scope.entity_id in (annotation.entity_links or {}).values():
                    evidence_ids.update(annotation.evidence_ids)
            spans = (
                self.db.query(EvidenceSpan)
                .filter(
                    EvidenceSpan.id.in_(evidence_ids),
                    EvidenceSpan.validity == "current",
                )
                .all()
            )
            chunk_ids = [
                chunk.id
                for chunk in query
                if any(
                    part["revision_id"] == span.text_revision_id
                    and part["start"] < span.char_end
                    and part["end"] > span.char_start
                    for part in (chunk.segments or [])
                    for span in spans
                )
            ]
            query = query.filter(SearchChunk.id.in_(chunk_ids))
        return query

    def _keyword(self, query, base, limit):
        names = [query]
        for entity in self.db.query(Entity):
            aliases = [
                entity.canonical_name,
                *json.loads(entity.alternative_names or "[]"),
            ]
            if any(
                re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", query, re.I)
                for name in aliases
                if name
            ):
                names.extend(aliases)
        # Exact spelling and aliases do not depend on an embedding being available.
        exact = (
            base.filter(
                or_(
                    *(
                        SearchChunk.content.ilike(
                            "%" + n.replace("%", "\\%").replace("_", "\\_") + "%",
                            escape="\\",
                        )
                        for n in names
                        if n
                    )
                )
            )
            .order_by(SearchChunk.id)
            .limit(limit)
            .all()
        )
        if self.db.bind.dialect.name == "postgresql":
            vector = func.to_tsvector(
                "simple", func.coalesce(SearchChunk.search_text, "")
            )
            tsquery = func.plainto_tsquery("simple", tokenize(query))
            rows = (
                base.filter(vector.op("@@")(tsquery))
                .order_by(func.ts_rank(vector, tsquery).desc())
                .limit(limit)
                .all()
            )
        else:
            tokens = tokenize(query).split()
            rows = (
                base.filter(
                    or_(*(SearchChunk.search_text.contains(token) for token in tokens))
                )
                .limit(limit)
                .all()
                if tokens
                else []
            )
        return list(dict.fromkeys([c.id for c in exact + rows]))

    async def search(
        self,
        query,
        top_k,
        document_id=None,
        scope=None,
        retrieval="hybrid",
        selected_ids=None,
    ):
        self.warnings = []
        scope = scope or ResearchScope(document_id=document_id)
        if not query.strip():
            return []
        base = self._base(scope)
        limit = max(100, top_k * 4)
        if selected_ids is not None:
            chunks = base.filter(SearchChunk.id.in_(selected_ids)).all()
            valid = [c for c in chunks if segments_valid(self.db, c)]
            if len(valid) != len(set(selected_ids)):
                from fastapi import HTTPException

                raise HTTPException(
                    409, "所选证据已失效或不属于当前范围，请刷新检索结果"
                )
            return self._hydrate([c.id for c in valid], {c.id: 1 for c in valid})
        rankings = []
        if retrieval in ("keyword", "hybrid"):
            rankings.append(self._keyword(query, base, limit))
        if jieba is None and any("\u3400" <= ch <= "\u9fff" for ch in query):
            self.warnings.append("中文分词组件不可用，当前使用汉字二元切分检索。")
        if retrieval in ("semantic", "hybrid"):
            try:
                vector = (await self.embedder.embed([query]))[0]
                if len(vector) != 1024:
                    raise ValueError("向量维度不匹配")
                rows = (
                    base.filter(
                        SearchChunk.embedding.isnot(None),
                        SearchChunk.embedding_model == self.embedder.model,
                    )
                    .order_by(SearchChunk.embedding.cosine_distance(vector))
                    .limit(limit)
                    .all()
                )
                rankings.append([c.id for c in rows])
                if not rows:
                    self.warnings.append("当前范围没有可用向量，已返回关键词结果。")
                    rankings.append(self._keyword(query, base, limit))
            except Exception:
                self.warnings.append("语义检索暂不可用，已降级为关键词检索。")
                if retrieval == "semantic":
                    rankings.append(self._keyword(query, base, limit))
        scores = {}
        for ranking in rankings:
            for rank, id in enumerate(ranking):
                scores[id] = scores.get(id, 0) + 1 / (RRF_K + rank + 1)
        candidates = sorted(scores, key=scores.get, reverse=True)
        valid = [
            id
            for id in candidates
            if segments_valid(self.db, self.db.get(SearchChunk, id))
        ][:top_k]
        return self._hydrate(valid, scores)

    def overview(self, scope, limit=24, max_chars=24000):
        """Sample across documents/pages; a broad summary is not a keyword query."""
        self.warnings = []
        base = self._base(scope)
        doc_ids = [
            row[0]
            for row in base.with_entities(SearchChunk.document_id)
            .distinct()
            .order_by(SearchChunk.document_id)
        ]
        if not doc_ids:
            return []
        all_doc_count = len(doc_ids)
        if len(doc_ids) > limit:
            doc_ids = [
                doc_ids[round(i * (len(doc_ids) - 1) / max(1, limit - 1))]
                for i in range(limit)
            ]
        per_doc = max(1, limit // len(doc_ids))
        chosen = []
        chars = 0
        for doc_id in doc_ids:
            query = base.filter(SearchChunk.document_id == doc_id)
            substantial = query.filter(func.length(SearchChunk.content) >= 120)
            if substantial.count():
                query = substantial
            count = query.count()
            for i in range(min(per_doc, count)):
                offset = round((i + 0.5) * count / min(per_doc, count) - 0.5)
                rows = (
                    query.options(defer(SearchChunk.embedding))
                    .order_by(SearchChunk.page_id, SearchChunk.block_id, SearchChunk.id)
                    .offset(offset)
                    .limit(3)
                )
                for chunk in rows:
                    if (
                        chunk.id not in chosen
                        and chars + len(chunk.content) <= max_chars
                        and segments_valid(self.db, chunk)
                    ):
                        chosen.append(chunk.id)
                        chars += len(chunk.content)
                        break
        self.warnings.append(
            f"本次按文献和页段抽样：覆盖 {len(set(self.db.get(SearchChunk,id).document_id for id in chosen))}/{all_doc_count} 份文献、{len(chosen)} 个片段；这是抽样概括，不是全文穷尽统计。"
        )
        return self._hydrate(chosen, {id: 1 for id in chosen})

    def _hydrate(self, ids, scores):
        hits = []
        for id in ids:
            chunk = self.db.get(SearchChunk, id)
            evidence = [
                locator(self.db, self.db.get(EvidenceSpan, p["evidence_id"]))
                for p in (chunk.segments or [])
                if p.get("evidence_id")
            ]
            page = self.db.get(Page, chunk.page_id)
            doc = self.db.get(Document, chunk.document_id)
            hits.append(
                SearchHitSchema(
                    chunk_id=chunk.id,
                    block_id=chunk.block_id,
                    document_id=chunk.document_id,
                    document_title=doc.original_filename,
                    page_number=page.page_number,
                    content=chunk.content,
                    score=round(scores[id], 6),
                    viewer_path=(
                        evidence[0]["viewer_path"]
                        if evidence
                        else f"/viewer/{doc.id}?page={page.page_number}&block={chunk.block_id}"
                    ),
                    evidence=evidence,
                    review_state=chunk.review_state,
                    content_type=chunk.content_type or "ocr_block_temporary",
                    source_unit_id=chunk.source_unit_id,
                )
            )
        return hits
