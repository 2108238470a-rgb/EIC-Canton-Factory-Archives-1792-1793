"""Research workflow invariants, isolated from the user's database and paid APIs."""

import asyncio
import os
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.database import Base
from app.models import *
from app.workbench.schemas import (
    EvidenceCreate,
    AnnotationCreate,
    ReviewRequest,
    ExtractionRequest,
    ResearchScope,
)
from app.workbench.service import (
    create_evidence,
    create_annotation,
    review_annotation,
    annotation_payload,
)
from app.workbench.versioning import current_revision
from app.workbench.extraction import request_run, extract_run
from app.rag.indexer import RagIndexer
from app.rag.retriever import HybridRetriever
from app.rag.qa import validate_answer, RagAnswerService
from app.schemas import TokenUsageSchema


class UnavailableEmbedding:
    model = "test-embedding"

    async def embed(self, texts):
        raise RuntimeError("provider offline")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        url = os.environ.get("WORKBENCH_TEST_DATABASE_URL", "sqlite:///:memory:")
        if url != "sqlite:///:memory:" and "ocr_workbench_test_" not in url:
            raise RuntimeError(
                "Tests require a disposable ocr_workbench_test_ database"
            )
        self.engine = (
            create_engine(
                url, connect_args={"check_same_thread": False}, poolclass=StaticPool
            )
            if url.startswith("sqlite")
            else create_engine(url)
        )
        if self.engine.dialect.name == "postgresql":
            Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.doc = Document(
            filename="test.pdf",
            original_filename="Archive 1792",
            file_path="/tmp/test.pdf",
            file_type=DocumentType.PDF,
            file_size=100,
            page_count=2,
        )
        self.db.add(self.doc)
        self.db.flush()
        self.page = Page(document_id=self.doc.id, page_number=1, width=100, height=200)
        self.db.add(self.page)
        self.db.flush()
        self.block = Block(
            page_id=self.page.id,
            block_index=0,
            bbox=[1, 2, 50, 60],
            ocr_text_raw="😀 Captain Smith sent a request to Canton.\n\nThe reply was delayed.",
            review_status=ReviewStatus.PENDING,
        )
        self.db.add(self.block)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_index_inventory_uses_real_ocr_and_excludes_images(self):
        from app.rag.api import index_documents

        self.doc.status = DocumentStatus.FAILED
        image = Document(
            filename="scan.png",
            original_filename="scan.png",
            file_path="/tmp/scan.png",
            file_type=DocumentType.IMAGE,
            file_size=1,
        )
        empty = Document(
            filename="empty.pdf",
            original_filename="empty.pdf",
            file_path="/tmp/empty.pdf",
            file_type=DocumentType.PDF,
            file_size=1,
        )
        self.db.add_all([image, empty])
        self.db.flush()
        page = Page(document_id=image.id, page_number=1)
        self.db.add(page)
        self.db.flush()
        self.db.add(
            Block(
                page_id=page.id,
                block_index=0,
                bbox=[0, 0, 10, 10],
                ocr_text_raw="image text",
            )
        )
        self.db.commit()
        items = index_documents(self.db)["items"]
        self.assertEqual([d["id"] for d in items], [self.doc.id])
        self.assertEqual(items[0]["ocr_pages"], 1)
        self.assertEqual(items[0]["eligible"], 1)
        self.assertEqual(items[0]["indexed"], 0)

    def test_index_requires_explicit_valid_selection_and_deduplicates(self):
        from app.rag.api import start_indexing
        from app.rag.schemas import IndexRequestSchema

        with patch("app.rag.api.build_rag_index_task.delay") as queue:
            for ids in ([], [999999], [-1]):
                with self.assertRaises(HTTPException) as raised:
                    start_indexing(IndexRequestSchema(document_ids=ids), self.db)
                self.assertEqual(raised.exception.status_code, 422)
            queue.assert_not_called()
            queue.return_value = SimpleNamespace(id="selected-job", state="PENDING")
            result = start_indexing(
                IndexRequestSchema(document_ids=[self.doc.id, self.doc.id]), self.db
            )
            self.assertEqual(result.task_id, "selected-job")
            queue.assert_called_once_with(document_ids=[self.doc.id])

    def test_index_batch_never_expands_selection(self):
        from app.tasks.rag_tasks import build_rag_index_task

        with patch("app.tasks.rag_tasks.SessionLocal", return_value=self.db), patch(
            "app.tasks.rag_tasks.RagIndexer"
        ) as indexer:
            indexer.return_value.index = AsyncMock(
                return_value={"indexed": 2, "total": 2, "vector_failed": 1}
            )
            result = build_rag_index_task.run(document_ids=[15, 29, 15])
            self.assertEqual(
                [call.args[0] for call in indexer.return_value.index.await_args_list],
                [15, 29],
            )
            self.assertEqual(result["indexed"], 4)
            self.assertEqual(result["documents_done"], 2)
            self.assertEqual(result["vector_failed"], 2)

    def test_recycle_preserves_references_and_restores_search_scope(self):
        from app.services.document_service import DocumentService
        from app.rag.api import index_documents

        annotation = self.annotation()
        asyncio.run(RagIndexer(self.db, UnavailableEmbedding()).index(self.doc.id))
        chunk_ids = [c.id for c in self.db.query(SearchChunk)]
        service = DocumentService(self.db)
        with patch("app.services.document_service.delete_document_files") as files:
            self.assertTrue(service.delete_document(self.doc.id))
            files.assert_not_called()
        self.assertIsNotNone(self.db.get(Document, self.doc.id).archived_at)
        self.assertEqual(service.get_documents()[1], 0)
        self.assertEqual(service.get_documents(archived=True)[1], 1)
        self.assertIsNotNone(self.db.get(Annotation, annotation.id))
        self.assertEqual(index_documents(self.db)["items"], [])
        self.assertEqual(
            HybridRetriever(self.db)._base(ResearchScope(mode="explore")).count(), 0
        )
        asyncio.run(RagIndexer(self.db, UnavailableEmbedding()).index())
        self.assertEqual([c.id for c in self.db.query(SearchChunk)], chunk_ids)
        self.assertTrue(service.restore_document(self.doc.id))
        self.assertEqual(service.get_documents()[1], 1)
        self.assertGreater(
            HybridRetriever(self.db)._base(ResearchScope(mode="explore")).count(), 0
        )

    def test_polish_summary_uses_text_coverage_and_current_task(self):
        from app.services.document_progress import processing_summaries

        self.assertEqual(
            processing_summaries(self.db, [self.doc.id])[self.doc.id]["polish_status"],
            "not_started",
        )
        self.block.ocr_text_corrected = self.block.ocr_text_raw
        self.db.commit()
        summary = processing_summaries(self.db, [self.doc.id])[self.doc.id]
        self.assertEqual(summary["polish_status"], "completed")
        self.assertEqual(summary["polished_blocks"], 1)
        self.db.add(
            Task(
                document_id=self.doc.id,
                task_type=TaskType.OCR_CORRECTION,
                status=TaskStatus.RUNNING,
            )
        )
        self.db.commit()
        self.assertEqual(
            processing_summaries(self.db, [self.doc.id])[self.doc.id]["polish_status"],
            "running",
        )

    def evidence(self, start=2, end=15):
        span = create_evidence(
            self.db,
            EvidenceCreate(
                block_id=self.block.id,
                expected_text=self.block.ocr_text_raw,
                char_start=start,
                char_end=end,
            ),
        )
        self.db.commit()
        return span

    def annotation(self, fields=None):
        span = self.evidence(0, len(self.block.ocr_text_raw))
        a = create_annotation(
            self.db,
            AnnotationCreate(
                document_id=self.doc.id,
                evidence_ids=[span.id],
                fields=fields
                or {
                    "name_form": "Smith",
                    "person": "Smith",
                    "event": "Request",
                    "role": "sender",
                },
            ),
        )
        self.db.commit()
        return a

    def approve(self, a, field, **kwargs):
        a = review_annotation(
            self.db,
            a.id,
            ReviewRequest(
                expected_version=a.version, field=field, decision="approved", **kwargs
            ),
        )
        self.db.commit()
        return a

    def index(self):
        return asyncio.run(RagIndexer(self.db, UnavailableEmbedding()).index())

    def test_unicode_evidence_and_dedup(self):
        span = self.evidence()
        self.assertEqual(span.exact_text, "Captain Smith")
        self.assertEqual(span.id, self.evidence().id)

    def test_expected_snapshot_conflict(self):
        with self.assertRaises(HTTPException) as e:
            create_evidence(
                self.db,
                EvidenceCreate(
                    block_id=self.block.id,
                    expected_text="old",
                    char_start=0,
                    char_end=1,
                ),
            )
        self.assertEqual(e.exception.status_code, 409)

    def test_invalid_offsets_and_name(self):
        with self.assertRaises(HTTPException):
            self.evidence(0, 500)
        self.db.rollback()
        with self.assertRaises(HTTPException):
            self.annotation({"name_form": "NotPresent"})

    def test_text_change_retains_old_quote_and_invalidates(self):
        a = self.annotation()
        span = self.db.get(EvidenceSpan, a.evidence_ids[0])
        self.index()
        self.block.ocr_text_raw = "Changed archive content"
        self.db.commit()
        self.assertIn("Smith", span.exact_text)
        self.assertEqual(span.validity, "stale")
        self.assertEqual(a.status, "needs_validation")
        self.assertTrue(
            all(c.status == ChunkStatus.INVALIDATED for c in self.db.query(SearchChunk))
        )
        self.assertGreaterEqual(self.db.query(TextRevision).count(), 2)

    def test_celery_direct_text_assignment_is_versioned(self):
        self.block.ocr_text_corrected = "Corrected text"
        self.db.commit()
        self.assertEqual(
            self.db.query(TextRevision)
            .filter_by(text_type=TextType.OCR_CORRECTED)
            .one()
            .content,
            "Corrected text",
        )

    def test_reocr_archives_without_deleting_evidence(self):
        a = self.annotation()
        self.block.retired = True
        self.db.commit()
        self.assertIsNotNone(self.db.get(Block, self.block.id))
        self.assertEqual(self.db.get(EvidenceSpan, a.evidence_ids[0]).validity, "stale")

    def test_review_version_conflict(self):
        a = self.annotation()
        old = a.version
        self.approve(a, "name_form")
        with self.assertRaises(HTTPException) as exc:
            review_annotation(
                self.db,
                a.id,
                ReviewRequest(
                    expected_version=old, field="person", decision="approved"
                ),
            )
        self.assertEqual(exc.exception.status_code, 409)

    def test_review_identity_revoke_and_same_name_separate(self):
        a = self.annotation()
        self.approve(a, "person")
        first = self.db.get(EntityMention, a.mention_id).entity_id
        b = self.annotation()
        self.approve(b, "person")
        self.assertNotEqual(first, self.db.get(EntityMention, b.mention_id).entity_id)
        review_annotation(
            self.db,
            a.id,
            ReviewRequest(
                expected_version=a.version, field="person", decision="pending"
            ),
        )
        self.db.commit()
        self.assertIsNone(self.db.get(EntityMention, a.mention_id).entity_id)
        self.assertEqual(
            self.db.query(IdentityDecision)
            .filter_by(mention_id=a.mention_id)
            .one()
            .status,
            DecisionStatus.SUPERSEDED,
        )

    def test_approved_data_not_touched_by_new_candidate(self):
        a = self.annotation()
        self.approve(a, "name_form")
        self.approve(a, "person")
        v = a.version
        self.annotation()
        self.assertEqual(a.version, v)
        self.assertEqual(a.field_states["person"], "approved")

    def test_stale_evidence_cannot_be_approved(self):
        a = self.annotation()
        self.block.ocr_text_raw = "New text"
        self.db.commit()
        with self.assertRaises(HTTPException):
            self.approve(a, "person")

    def test_event_and_identity_review_are_independent(self):
        a = self.annotation()
        self.approve(a, "event")
        self.assertIsNotNone(a.event_id)
        self.assertIsNone(self.db.get(EntityMention, a.mention_id).entity_id)
        self.approve(a, "person")
        self.approve(a, "role")
        self.assertEqual(self.db.query(Participation).count(), 1)
        review_annotation(
            self.db,
            a.id,
            ReviewRequest(
                expected_version=a.version, field="role", decision="rejected"
            ),
        )
        self.db.commit()
        self.assertEqual(self.db.query(Participation).count(), 0)

    def test_keyword_survives_embedding_outage(self):
        result = self.index()
        self.assertGreater(result["vector_failed"], 0)
        retriever = HybridRetriever(self.db, UnavailableEmbedding())
        hits = asyncio.run(
            retriever.search(
                "Smith", 20, scope=ResearchScope(mode="explore"), retrieval="hybrid"
            )
        )
        self.assertTrue(hits)
        self.assertTrue(retriever.warnings)
        self.assertTrue(hits[0].evidence)

    def test_verified_default_excludes_pending(self):
        self.index()
        retriever = HybridRetriever(self.db, UnavailableEmbedding())
        self.assertFalse(
            asyncio.run(retriever.search("Smith", 10, retrieval="keyword"))
        )
        current_revision(self.db, self.block).review_state = "approved"
        self.db.commit()
        self.index()
        self.assertTrue(asyncio.run(retriever.search("Smith", 10, retrieval="keyword")))

    def test_selected_sources_enforce_scope(self):
        self.index()
        id = self.db.query(SearchChunk).first().id
        with self.assertRaises(HTTPException):
            asyncio.run(
                HybridRetriever(self.db).search(
                    "Smith",
                    10,
                    scope=ResearchScope(document_id=999, mode="explore"),
                    selected_ids=[id],
                )
            )

    def test_extraction_idempotency_and_force_new(self):
        request = ExtractionRequest()
        a, created = request_run(self.db, self.doc.id, request)
        self.db.commit()
        b, created2 = request_run(self.db, self.doc.id, request)
        self.assertEqual(a.id, b.id)
        self.assertFalse(created2)
        c, _ = request_run(self.db, self.doc.id, ExtractionRequest(force_new=True))
        self.assertNotEqual(a.id, c.id)

    def test_citation_ids_quotes_and_no_citation(self):
        hits = [SimpleNamespace(content="Captain Smith sent a request.")]
        valid = {
            "insufficient_evidence": False,
            "claims": [
                {
                    "text": "Smith sent a request.",
                    "citations": [1],
                    "quotes": ["Smith sent a request"],
                }
            ],
        }
        self.assertEqual(len(validate_answer(json.dumps(valid), hits).claims), 1)
        for change in [
            {"citations": [9]},
            {"quotes": ["invented quote"]},
            {"citations": []},
            {"text": ""},
        ]:
            payload = json.loads(json.dumps(valid))
            payload["claims"][0].update(change)
            with self.assertRaises(ValueError):
                validate_answer(json.dumps(payload), hits)

    def test_followup_uses_history_for_context_but_only_current_sources_for_citations(
        self,
    ):
        self.index()
        hits = asyncio.run(
            HybridRetriever(self.db, UnavailableEmbedding()).search(
                "Smith", 5, scope=ResearchScope(mode="explore"), retrieval="keyword"
            )
        )
        service = RagAnswerService(self.db)
        service.retriever.search = AsyncMock(return_value=hits)
        history = [
            {
                "question": "What did Captain Smith request?",
                "answer": "Unverified historical answer [999]",
            }
        ]
        complete = AsyncMock(
            return_value=SimpleNamespace(
                text=json.dumps(
                    {
                        "insufficient_evidence": False,
                        "claims": [
                            {
                                "text": "A request was sent.",
                                "citations": [1],
                                "quotes": [hits[0].content],
                            }
                        ],
                    }
                )
            )
        )
        with patch("app.rag.qa.gpt_service.complete", complete):
            result = asyncio.run(
                service.answer(
                    "Why was it delayed?",
                    5,
                    scope=ResearchScope(mode="explore"),
                    retrieval="keyword",
                    history=history,
                )
            )
        self.assertFalse(result.insufficient_evidence)
        self.assertIn(
            history[0]["question"], service.retriever.search.call_args.args[0]
        )
        prompt = json.loads(complete.call_args.args[1])
        self.assertEqual(prompt["conversation"], history)
        self.assertTrue(
            all("Unverified" not in source["text"] for source in prompt["sources"])
        )
        self.assertEqual(result.claims[0].citations, [1])

    def test_followup_cannot_cite_a_quote_from_a_previous_answer(self):
        self.index()
        service = RagAnswerService(self.db)
        service.retriever = HybridRetriever(self.db, UnavailableEmbedding())
        complete = AsyncMock(
            return_value=SimpleNamespace(
                text=json.dumps(
                    {
                        "insufficient_evidence": False,
                        "claims": [
                            {
                                "text": "Unsupported",
                                "citations": [1],
                                "quotes": ["fictional-history-quote"],
                            }
                        ],
                    }
                )
            )
        )
        with patch("app.rag.qa.gpt_service.complete", complete):
            result = asyncio.run(
                service.answer(
                    "Smith",
                    5,
                    scope=ResearchScope(mode="explore"),
                    retrieval="keyword",
                    history=[
                        {"question": "Smith?", "answer": "fictional-history-quote"}
                    ],
                )
            )
        self.assertEqual(complete.await_count, 2)
        self.assertTrue(result.insufficient_evidence)
        self.assertEqual(result.claims, [])

    def test_layout_only_quotes_are_reanchored_but_factual_changes_rejected(self):
        from app.rag.qa import anchored_quotes

        source = "Captain Smith sent\na request in 1792. The reply was delayed."
        self.assertEqual(
            anchored_quotes("Captain Smith sent a request in 1792.", source),
            ["Captain Smith sent\na request in 1792."],
        )
        self.assertEqual(
            anchored_quotes("Captain Smith sent...The reply was delayed.", source),
            ["Captain Smith sent", "The reply was delayed."],
        )
        for invented in [
            "Captain Smyth sent a request in 1792.",
            "Captain Smith sent a request in 1793.",
            "The reply was delayed...Captain Smith sent",
        ]:
            with self.assertRaises(ValueError):
                anchored_quotes(invented, source)

    def test_overview_samples_multiple_documents_without_changing_review_scope(self):
        self.index()
        other = Document(
            filename="other.pdf",
            original_filename="Other",
            file_path="/tmp/other.pdf",
            file_type=DocumentType.PDF,
            file_size=1,
            page_count=1,
        )
        self.db.add(other)
        self.db.flush()
        page = Page(document_id=other.id, page_number=1)
        self.db.add(page)
        self.db.flush()
        self.db.add(
            Block(
                page_id=page.id,
                block_index=0,
                bbox=[0, 0, 1, 1],
                ocr_text_raw="Captain Brown delivered a letter.",
            )
        )
        self.db.commit()
        asyncio.run(RagIndexer(self.db, UnavailableEmbedding()).index(other.id))
        retriever = HybridRetriever(self.db, UnavailableEmbedding())
        self.assertEqual(retriever.overview(ResearchScope(mode="verified")), [])
        hits = retriever.overview(ResearchScope(mode="explore"), limit=4)
        self.assertEqual({h.document_id for h in hits}, {self.doc.id, other.id})
        selected = retriever.overview(
            ResearchScope(mode="explore", document_ids=[other.id]), limit=4
        )
        self.assertEqual({h.document_id for h in selected}, {other.id})

    def test_automatic_correction_does_not_overwrite_reviewed_text(self):
        from app.repositories import BlockRepository
        from app.schemas import BlockUpdate

        self.block.review_status = ReviewStatus.APPROVED
        self.db.commit()
        repo = BlockRepository(self.db)
        self.assertEqual(repo.get_unprocessed_by_page(self.page.id), [])
        with self.assertRaises(ValueError):
            repo.update_generated(
                self.block.id,
                BlockUpdate(ocr_text_corrected="changed"),
                self.block.ocr_text_raw,
            )
        self.assertIsNone(self.db.get(Block, self.block.id).ocr_text_corrected)

    def test_verified_mode_never_silently_expands_to_pending_ocr(self):
        self.index()
        service = RagAnswerService(self.db)
        with patch("app.rag.qa.gpt_service.complete", AsyncMock()) as complete:
            result = asyncio.run(
                service.answer(
                    "概括主要人物与事件",
                    8,
                    scope=ResearchScope(mode="verified"),
                    answer_style="guide",
                )
            )
        complete.assert_not_awaited()
        self.assertEqual(result.outcome, "no_sources")
        self.assertEqual(result.scope["mode"], "verified")
        self.assertIn("不表示档案没有答案", result.answer)

    def test_exploratory_guide_separates_record_and_interpretation(self):
        self.index()
        service = RagAnswerService(self.db)
        service.retriever = HybridRetriever(self.db, UnavailableEmbedding())
        complete = AsyncMock(
            return_value=SimpleNamespace(
                text=json.dumps(
                    {
                        "insufficient_evidence": False,
                        "claims": [
                            {
                                "kind": "source_record",
                                "text": "原文记载 Smith 发出请求。",
                                "citations": [1],
                                "quotes": ["Captain Smith sent a request to Canton."],
                            },
                            {
                                "kind": "interpretation",
                                "text": "这可能表明存在请求往来，具体背景不能仅由此确定。",
                                "citations": [1],
                                "quotes": ["Captain Smith sent a request to Canton."],
                            },
                        ],
                    }
                )
            )
        )
        with patch("app.rag.qa.gpt_service.complete", complete):
            result = asyncio.run(
                service.answer(
                    "Smith",
                    8,
                    scope=ResearchScope(mode="explore"),
                    retrieval="keyword",
                    answer_style="guide",
                )
            )
        self.assertFalse(result.insufficient_evidence)
        self.assertEqual(
            [x.title for x in result.sections], ["原文记载", "AI 解读 · 仍需核对"]
        )
        self.assertTrue(any("尚未人工复核" in w for w in result.warnings))
        self.assertEqual(result.claims[1].kind, "interpretation")
        self.assertIn("虚构的 AI 研究助手", complete.await_args.args[0])
        self.assertEqual(result.answer_style, "guide")

    def test_catalog_review_counts_are_actual_current_fragments(self):
        from app.rag.api import index_documents

        self.index()
        item = next(
            d for d in index_documents(self.db)["items"] if d["id"] == self.doc.id
        )
        self.assertGreater(item["current_chunks"], 0)
        self.assertEqual(item["approved_chunks"], 0)
        self.block.ocr_text_raw = "new original"
        self.db.commit()
        item = next(
            d for d in index_documents(self.db)["items"] if d["id"] == self.doc.id
        )
        self.assertEqual(item["current_chunks"], 0)

    def test_question_generation_timeout_returns_evidence_and_cancels_model(self):
        self.index()
        service = RagAnswerService(self.db)
        service.retriever = HybridRetriever(self.db, UnavailableEmbedding())
        cancelled = []

        async def slow_model(*args, **kwargs):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.append(True)

        with patch(
            "app.rag.qa.gpt_service.complete", AsyncMock(side_effect=slow_model)
        ), patch("app.rag.qa.settings.rag_answer_timeout_seconds", 0.01):
            result = asyncio.run(
                service.answer(
                    "Smith", 8, scope=ResearchScope(mode="explore"), retrieval="keyword"
                )
            )
        self.assertEqual(result.outcome, "model_timeout")
        self.assertTrue(result.insufficient_evidence)
        self.assertTrue(result.citations)
        self.assertEqual(cancelled, [True])
        self.assertIn("超时", result.answer)

    def test_overview_timeout_keeps_explicit_literal_fallback(self):
        self.index()

        async def slow_model(*args, **kwargs):
            await asyncio.sleep(10)

        with patch(
            "app.rag.qa.gpt_service.complete", AsyncMock(side_effect=slow_model)
        ), patch("app.rag.qa.settings.rag_answer_timeout_seconds", 0.01):
            result = asyncio.run(
                RagAnswerService(self.db).answer(
                    "概括主要人物与事件", 8, scope=ResearchScope(mode="explore")
                )
            )
        self.assertEqual(result.outcome, "extractive_overview")
        self.assertTrue(result.claims)
        self.assertTrue(any("等待时限" in w for w in result.warnings))
        self.assertEqual(result.model, "extractive-local")

    def test_overview_refusal_keeps_literal_source_clues(self):
        self.index()
        service = RagAnswerService(self.db)
        complete = AsyncMock(
            return_value=SimpleNamespace(
                text='{"claims":[],"insufficient_evidence":true}'
            )
        )
        with patch("app.rag.qa.gpt_service.complete", complete):
            result = asyncio.run(
                service.answer(
                    "概括主要人物与事件", 8, scope=ResearchScope(mode="explore")
                )
            )
        self.assertEqual(complete.await_count, 1)
        self.assertEqual(result.outcome, "extractive_overview")
        self.assertFalse(result.insufficient_evidence)
        self.assertTrue(any(c.category == "person" for c in result.claims))
        self.assertIn("人物与相关记载", [s.title for s in result.sections])
        self.assertIn("不冒充完整分析", result.answer)
        for claim in result.claims:
            for number, quote in zip(claim.citations, claim.quotes):
                self.assertIn(quote, result.citations[number - 1].content)

    def test_overview_fallback_is_discarded_when_source_changes(self):
        self.index()
        service = RagAnswerService(self.db)

        async def update_while_answering(*args, **kwargs):
            self.block.ocr_text_raw = "A different current original"
            self.db.commit()
            return SimpleNamespace(text='{"claims":[],"insufficient_evidence":true}')

        with patch(
            "app.rag.qa.gpt_service.complete",
            AsyncMock(side_effect=update_while_answering),
        ):
            result = asyncio.run(
                service.answer(
                    "概括主要人物与事件", 8, scope=ResearchScope(mode="explore")
                )
            )
        self.assertEqual(result.outcome, "stale_sources")
        self.assertTrue(result.insufficient_evidence)
        self.assertEqual(result.claims, [])
        self.assertEqual(result.sections, [])
        self.assertFalse(any(c.cited for c in result.citations))

    def test_overview_partial_claims_survive_insufficient_flag(self):
        self.index()
        service = RagAnswerService(self.db)
        complete = AsyncMock(
            return_value=SimpleNamespace(
                text=json.dumps(
                    {
                        "insufficient_evidence": True,
                        "claims": [
                            {
                                "category": "person",
                                "text": "Smith 发出请求。",
                                "citations": [1],
                                "quotes": ["Captain Smith sent a request to Canton."],
                            }
                        ],
                    }
                )
            )
        )
        with patch("app.rag.qa.gpt_service.complete", complete):
            result = asyncio.run(
                service.answer(
                    "概括主要人物与事件", 8, scope=ResearchScope(mode="explore")
                )
            )
        self.assertEqual(result.outcome, "answered_partial")
        self.assertFalse(result.insufficient_evidence)
        self.assertEqual(result.claims[0].category, "person")
        self.assertIn("Smith 发出请求", result.answer)
        self.assertIn("不代表全文穷尽", result.answer)

    def test_invalid_model_answer_retries_once(self):
        self.index()
        service = RagAnswerService(self.db)
        service.retriever = HybridRetriever(self.db, UnavailableEmbedding())
        complete = AsyncMock(
            return_value=SimpleNamespace(
                text='{"claims":[],"insufficient_evidence":false}'
            )
        )
        with patch("app.rag.qa.gpt_service.complete", complete):
            answer = asyncio.run(
                service.answer(
                    "Smith", 5, scope=ResearchScope(mode="explore"), retrieval="keyword"
                )
            )
        self.assertEqual(complete.await_count, 2)
        self.assertTrue(answer.insufficient_evidence)

    def test_cross_page_source_preserves_each_anchor(self):
        from app.workbench.api import new_source_unit, review_source_unit
        from app.workbench.schemas import SourceUnitCreate, SegmentPart
        from app.workbench.api import SegmentReview

        second_page = Page(document_id=self.doc.id, page_number=2)
        self.db.add(second_page)
        self.db.flush()
        second = Block(
            page_id=second_page.id,
            block_index=0,
            bbox=[0, 0, 10, 10],
            ocr_text_raw="Continued request by Smith.",
        )
        self.db.add(second)
        self.db.commit()
        r1 = current_revision(self.db, self.block)
        r2 = current_revision(self.db, second)
        unit = new_source_unit(
            self.doc.id,
            SourceUnitCreate(
                title="Cross-page letter",
                spans=[
                    SegmentPart(
                        block_id=self.block.id,
                        revision_id=r1.id,
                        char_start=0,
                        char_end=len(r1.content),
                    ),
                    SegmentPart(
                        block_id=second.id,
                        revision_id=r2.id,
                        char_start=0,
                        char_end=len(r2.content),
                    ),
                ],
            ),
            self.db,
        )
        self.index()
        chunks = self.db.query(SearchChunk).filter_by(source_unit_id=unit["id"]).all()
        self.assertTrue(any(len(c.segments) > 1 for c in chunks))
        self.assertEqual(len({p["block_id"] for c in chunks for p in c.segments}), 2)

    def test_extraction_rejects_fabricated_quote_and_duplicate_execution(self):
        run, _ = request_run(self.db, self.doc.id, ExtractionRequest())
        self.db.commit()
        rid = run.input_version_ids[0]
        value = {
            "items": [
                {
                    "revision_id": rid,
                    "quote": "Smith",
                    "char_start": 10,
                    "fields": {"name_form": "Smith", "person": "Smith"},
                },
                {
                    "revision_id": rid,
                    "quote": "fabricated",
                    "fields": {"person": "Fake"},
                },
            ]
        }
        complete = AsyncMock(
            return_value=SimpleNamespace(
                text=json.dumps(value),
                token_usage=TokenUsageSchema(prompt_tokens=10, completion_tokens=20),
            )
        )
        with patch("app.workbench.extraction.gpt_service.complete", complete):
            result = asyncio.run(extract_run(self.db, run.id))
            asyncio.run(extract_run(self.db, run.id))
        self.assertEqual(result["created"], 1)
        self.assertEqual(len(result["rejected_candidates"]), 1)
        self.assertEqual(self.db.query(Annotation).count(), 1)
        self.assertEqual(complete.await_count, 1)

    def test_export_csv_and_evidence_manifest(self):
        import io, zipfile, csv
        from app.workbench.api import export_annotations

        a = self.annotation()
        csv_response = export_annotations("csv", None, None, None, None, self.db)
        csv_rows = list(csv.reader(io.StringIO(csv_response.body.decode("utf-8-sig"))))
        self.assertEqual(len(csv_rows[0]), 16)
        self.assertEqual(csv_rows[1][0], a.public_id)
        archive = export_annotations("zip", None, None, None, None, self.db)
        with zipfile.ZipFile(io.BytesIO(archive.body)) as z:
            self.assertIn("manifest.json", z.namelist())
            manifest = json.loads(z.read("manifest.json"))
            self.assertEqual(manifest["evidence"][0]["id"], a.evidence_ids[0])
            self.assertIn("crop_error", manifest["evidence"][0])

    def test_source_segmentation_does_not_invalidate_annotations(self):
        from app.workbench.api import new_source_unit
        from app.workbench.schemas import SourceUnitCreate, SegmentPart

        a = self.annotation()
        rev = current_revision(self.db, self.block)
        new_source_unit(
            self.doc.id,
            SourceUnitCreate(
                title="Letter",
                spans=[
                    SegmentPart(
                        block_id=self.block.id,
                        revision_id=rev.id,
                        char_start=0,
                        char_end=len(rev.content),
                    )
                ],
            ),
            self.db,
        )
        self.assertEqual(
            self.db.get(EvidenceSpan, a.evidence_ids[0]).validity, "current"
        )
        self.assertEqual(a.status, "pending")

    def test_rejected_identity_removes_official_assertions(self):
        a = self.annotation(
            {"name_form": "Smith", "person": "Smith", "occupation": "Captain"}
        )
        self.approve(a, "person")
        self.approve(a, "occupation")
        self.assertEqual(
            self.db.query(Assertion).filter_by(status=AssertionStatus.VERIFIED).count(),
            1,
        )
        review_annotation(
            self.db,
            a.id,
            ReviewRequest(
                expected_version=a.version, field="person", decision="rejected"
            ),
        )
        self.db.commit()
        self.assertEqual(
            self.db.query(Assertion).filter_by(status=AssertionStatus.VERIFIED).count(),
            0,
        )

    def test_reviewed_organization_and_place_have_dossiers(self):
        a = self.annotation(
            {
                "name_form": "Smith",
                "person": "Smith",
                "organization": "East India Company",
                "location": "Canton",
                "event": "Request",
                "event_date": "1792-10-01",
            }
        )
        self.approve(a, "person")
        self.approve(a, "organization")
        self.approve(a, "location")
        self.approve(a, "event")
        self.approve(a, "event_date")
        self.assertEqual(
            self.db.get(Entity, a.entity_links["organization"]).entity_type,
            EntityType.ORGANIZATION,
        )
        event = self.db.get(Event, a.event_id)
        self.assertEqual(event.location_entity_id, a.entity_links["location"])
        self.assertEqual(str(event.date_start), "1792-10-01")

    def test_structured_counts_do_not_depend_on_index(self):
        a = self.annotation()
        self.approve(a, "person")
        answer = asyncio.run(RagAnswerService(self.db).answer("人物总数是多少？", 8))
        self.assertEqual(answer.model, "structured-query")
        self.assertIn("共 1 个", answer.answer)
        self.assertEqual(self.db.query(SearchChunk).count(), 0)

    def test_api_create_review_conflict_and_export(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.workbench.api import router
        from app.api.deps import get_db

        app = FastAPI()
        app.include_router(router, prefix="/api/v2")
        app.dependency_overrides[get_db] = lambda: self.db
        with TestClient(app) as client:
            e = client.post(
                "/api/v2/workbench/evidence",
                json={
                    "block_id": self.block.id,
                    "expected_text": self.block.ocr_text_raw,
                    "char_start": 0,
                    "char_end": len(self.block.ocr_text_raw),
                },
            )
            self.assertEqual(e.status_code, 201)
            self.assertIn("revision_id", e.json())
            a = client.post(
                "/api/v2/workbench/annotations",
                json={
                    "document_id": self.doc.id,
                    "evidence_ids": [e.json()["id"]],
                    "fields": {"name_form": "Smith", "person": "Smith"},
                },
            )
            self.assertEqual(a.status_code, 201)
            data = {"field": "person", "decision": "approved", "expected_version": 1}
            approved = client.post(
                f"/api/v2/workbench/annotations/{a.json()['id']}/reviews", json=data
            )
            self.assertEqual(approved.status_code, 200)
            conflict = client.post(
                f"/api/v2/workbench/annotations/{a.json()['id']}/reviews", json=data
            )
            self.assertEqual(conflict.status_code, 409)
            self.db.rollback()
            response = client.get("/api/v2/workbench/exports?format=json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["count"], 1)

    @unittest.skipUnless(
        os.environ.get("WORKBENCH_TEST_DATABASE_URL"), "PostgreSQL locking only"
    )
    def test_concurrent_reviews_keep_first_decision(self):
        import threading

        a = self.annotation()
        self.approve(a, "name_form")
        reviewed = review_annotation(
            self.db,
            a.id,
            ReviewRequest(
                expected_version=a.version, field="person", decision="approved"
            ),
        )
        expected_version = reviewed.version - 1
        started = threading.Event()
        result = []

        def other_reviewer():
            with Session(self.engine, autoflush=False) as other:
                started.set()
                try:
                    review_annotation(
                        other,
                        a.id,
                        ReviewRequest(
                            expected_version=expected_version,
                            field="person",
                            decision="rejected",
                        ),
                    )
                    other.commit()
                    result.append("overwritten")
                except HTTPException as exc:
                    other.rollback()
                    result.append(exc.status_code)

        thread = threading.Thread(target=other_reviewer)
        thread.start()
        started.wait(2)
        self.db.commit()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [409])
        self.assertEqual(a.field_states["person"], "approved")

    def test_saving_stale_annotation_cannot_restore_verified_knowledge(self):
        a = self.annotation(
            {"name_form": "Smith", "person": "Smith", "occupation": "Captain"}
        )
        self.approve(a, "person")
        self.approve(a, "occupation")
        self.block.ocr_text_raw = "Updated original"
        self.db.commit()
        review_annotation(
            self.db,
            a.id,
            ReviewRequest(
                expected_version=a.version, field="occupation", decision="pending"
            ),
        )
        self.db.commit()
        self.assertEqual(a.status, "needs_validation")
        self.assertFalse(
            self.db.query(Assertion).filter_by(status=AssertionStatus.VERIFIED).count()
        )

    def test_partial_source_does_not_hide_unsegmented_text(self):
        from app.workbench.api import new_source_unit
        from app.workbench.schemas import SourceUnitCreate, SegmentPart

        revision = current_revision(self.db, self.block)
        new_source_unit(
            self.doc.id,
            SourceUnitCreate(
                title="Partial letter",
                spans=[
                    SegmentPart(
                        block_id=self.block.id,
                        revision_id=revision.id,
                        char_start=0,
                        char_end=15,
                    )
                ],
            ),
            self.db,
        )
        self.index()
        contents = " ".join(
            c.content
            for c in self.db.query(SearchChunk).filter_by(status=ChunkStatus.INDEXED)
        )
        self.assertIn("Captain Smith", contents)
        self.assertIn("reply was delayed", contents)

    def test_legacy_writes_use_canonical_tables(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.workbench.compat import router
        from app.api.deps import get_db

        app = FastAPI()
        app.include_router(router, prefix="/api/v2")
        app.dependency_overrides[get_db] = lambda: self.db
        with TestClient(app) as client:
            r = client.post(
                "/api/v2/entities",
                json={"entity_type": "person", "canonical_name": "Smith"},
            )
            self.assertEqual(r.status_code, 200)
            legacy_id = r.json()["id"]
            read = client.get(f"/api/v2/entities/{legacy_id}")
            self.assertEqual(read.status_code, 200)
            self.assertIsNotNone(read.json()["canonical_id"])
            self.assertEqual(self.db.query(Entity).count(), 1)
            r = client.post(
                "/api/v2/evidence-spans",
                json={"block_id": self.block.id, "char_start": 0, "char_end": 15},
            )
            self.assertEqual(r.status_code, 200)
            locate = client.get(f"/api/v2/evidence-spans/{r.json()['id']}/locator")
            self.assertEqual(locate.status_code, 200)
            self.assertIn("evidence=", locate.json()["viewer_path"])

    def test_revision_content_is_immutable(self):
        revision = current_revision(self.db, self.block)
        original = revision.content
        revision.content = "Silent rewrite"
        with self.assertRaises(ValueError):
            self.db.commit()
        self.db.rollback()
        self.assertEqual(self.db.get(TextRevision, revision.id).content, original)

    def test_evidence_image_survives_source_replacement(self):
        import tempfile
        from pathlib import Path
        from PIL import Image
        from app.config import settings

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "original.png"
            Image.new("RGB", (100, 200), "white").save(source)
            self.page.image_path = str(source)
            self.db.commit()
            with patch.object(settings, "storage_path", folder):
                e = self.evidence()
                frozen = Path(e.image_snapshot_path)
                self.assertTrue(frozen.is_file())
                Image.new("RGB", (100, 200), "black").save(source)
                with Image.open(frozen) as image:
                    self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))

    def test_source_review_detects_concurrent_change(self):
        from app.workbench.api import new_source_unit, review_source_unit, SegmentReview
        from app.workbench.schemas import SourceUnitCreate, SegmentPart

        revision = current_revision(self.db, self.block)
        created = new_source_unit(
            self.doc.id,
            SourceUnitCreate(
                title="Letter",
                spans=[
                    SegmentPart(
                        block_id=self.block.id,
                        revision_id=revision.id,
                        char_start=0,
                        char_end=len(revision.content),
                    )
                ],
            ),
            self.db,
        )
        body = SegmentReview(approved=True, expected_updated_at=created["updated_at"])
        review_source_unit(created["id"], body, self.db)
        with self.assertRaises(HTTPException) as exc:
            review_source_unit(created["id"], body, self.db)
        self.assertEqual(exc.exception.status_code, 409)

    def test_manual_correction_versions_and_rejects_stale_snapshot(self):
        from app.workbench.api import manual_correction, ManualCorrectionInput

        a = self.annotation()
        data = ManualCorrectionInput(
            expected_raw_text=self.block.ocr_text_raw,
            expected_corrected_text=None,
            corrected_text="Captain Smith sent a request to Canton.",
        )
        result = manual_correction(self.block.id, data, self.db)
        self.assertEqual(result.ocr_text_corrected, data.corrected_text)
        self.assertEqual(current_revision(self.db, self.block).author_type, "human")
        self.assertEqual(self.db.get(EvidenceSpan, a.evidence_ids[0]).validity, "stale")
        with self.assertRaises(HTTPException) as exc:
            manual_correction(self.block.id, data, self.db)
        self.assertEqual(exc.exception.status_code, 409)

    def test_place_filter_uses_reviewed_entity_links(self):
        from app.workbench.service import annotation_query

        a = self.annotation(
            {"name_form": "Smith", "person": "Smith", "location": "Canton"}
        )
        self.approve(a, "person")
        self.approve(a, "location")
        self.index()
        place_id = a.entity_links["location"]
        self.assertEqual(annotation_query(self.db, entity_id=place_id).count(), 1)
        hits = asyncio.run(
            HybridRetriever(self.db, UnavailableEmbedding()).search(
                "Canton",
                10,
                scope=ResearchScope(mode="explore", entity_id=place_id),
                retrieval="keyword",
            )
        )
        self.assertTrue(hits)

    def test_entity_filter_does_not_include_unrelated_paragraph_on_same_block(self):
        evidence = self.evidence(10, 15)
        a = create_annotation(
            self.db,
            AnnotationCreate(
                document_id=self.doc.id,
                evidence_ids=[evidence.id],
                fields={"name_form": "Smith", "person": "Smith"},
            ),
        )
        self.db.commit()
        self.approve(a, "person")
        self.index()
        entity_id = self.db.get(EntityMention, a.mention_id).entity_id
        hits = asyncio.run(
            HybridRetriever(self.db, UnavailableEmbedding()).search(
                "reply",
                10,
                scope=ResearchScope(mode="explore", entity_id=entity_id),
                retrieval="keyword",
            )
        )
        self.assertFalse(hits)


if __name__ == "__main__":
    unittest.main()
