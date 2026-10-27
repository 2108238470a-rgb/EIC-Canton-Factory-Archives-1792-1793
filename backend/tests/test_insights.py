"""Complete research flow on an isolated DB and deterministic model, never user archives."""

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.database import Base
from app.api.deps import get_db
from app.models import (
    Document,
    DocumentType,
    Page,
    Block,
    ExtractionStatus,
    ExtractionRun,
)
from app.insights.service import (
    request_analysis,
    payload,
    analyze,
    batches,
    supported_date,
    validated_items,
)
from app.insights.api import router


class InsightsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.doc = Document(
            filename="fixture.pdf",
            original_filename="Fixture",
            file_path="/tmp/fixture.pdf",
            file_type=DocumentType.PDF,
            file_size=10,
            page_count=2,
        )
        self.db.add(self.doc)
        self.db.flush()
        self.blocks = []
        for n, text in enumerate(
            [
                "😀 24 September 1792. Henry Browne sent a letter to Canton.",
                "The committee discussed bills of exchange. No date is stated.",
            ],
            1,
        ):
            page = Page(document_id=self.doc.id, page_number=n)
            self.db.add(page)
            self.db.flush()
            block = Block(
                page_id=page.id, block_index=0, bbox=[1, 2, 3, 4], ocr_text_raw=text
            )
            self.db.add(block)
            self.blocks.append(block)
        self.db.commit()
        app = FastAPI()
        app.include_router(router, prefix="/api/v2")

        def override():
            yield self.db

        app.dependency_overrides[get_db] = override
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def completion(self, _prompt, text, **kwargs):
        s = json.loads(text)[0]
        if kwargs.get("mode") == "historical_insights_summary":
            return SimpleNamespace(
                text=json.dumps(
                    {
                        "sections": [
                            {
                                "text": "文献记载函件往来与商馆事务。",
                                "source_ids": [s["id"]],
                            }
                        ]
                    }
                ),
                token_usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )
        items = [
            {
                "kind": kind,
                "title": title,
                "description": "有引句支撑的候选解释",
                "revision_id": s["revision_id"],
                "quote": s["text"],
                "char_start": 0,
                "date": "1792-09-24",
                "date_basis": "event_explicit",
                "date_quote": "24 September 1792",
                "people": ["Henry Browne", "Invented"],
            }
            for kind, title in [
                ("overview", "商馆事务"),
                ("topic", "信函"),
                ("event", "寄送函件"),
            ]
        ]
        return SimpleNamespace(
            text=json.dumps({"items": items}),
            token_usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    def test_complete_api_workflow_version_edit_export_and_stale(self):
        result = self.client.post(
            f"/api/v2/insights/documents/{self.doc.id}", json={"mode": "directory"}
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(len(result.json()["artifact"]["toc"]), 2)
        with patch("app.insights.api.dispatch"):
            run_id = self.client.post(
                f"/api/v2/insights/documents/{self.doc.id}", json={"mode": "ai"}
            ).json()["id"]
        with patch(
            "app.insights.service.gpt_service.complete",
            new=AsyncMock(side_effect=self.completion),
        ) as model:
            asyncio.run(analyze(self.db, run_id))
            asyncio.run(analyze(self.db, run_id))
            self.assertEqual(model.await_count, 2)
        result = self.client.get(f"/api/v2/insights/runs/{run_id}").json()
        a = result["artifact"]
        self.assertEqual(result["status"], "completed")
        self.assertEqual(a["covered_characters"], a["total_characters"])
        self.assertEqual(a["items"][2]["date"], "1792-09-24")
        self.assertEqual(a["items"][2]["people"], ["Henry Browne"])
        entry = a["items"][1]
        path = f"/api/v2/insights/runs/{run_id}/toc/{entry['id']}"
        edited = self.client.patch(
            path, json={"title": "人工改名", "expected_revision": 1}
        )
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertNotEqual(edited.json()["id"], run_id)
        self.assertEqual(
            self.db.get(ExtractionRun, run_id).output_summary["items"][1]["title"],
            "信函",
        )
        self.assertEqual(
            self.client.patch(
                path, json={"title": "并发修改", "expected_revision": 1}
            ).status_code,
            409,
        )
        self.assertIn(
            "manifest", self.client.get(f"/api/v2/insights/runs/{run_id}/export").json()
        )
        self.assertIn(
            "版本",
            self.client.get(
                f"/api/v2/insights/runs/{run_id}/export?format=markdown"
            ).text,
        )
        self.blocks[0].ocr_text_raw += " Updated."
        self.db.commit()
        self.assertTrue(
            self.client.get(f"/api/v2/insights/runs/{run_id}").json()["stale"]
        )

    def test_idempotency_force_empty_and_archive(self):
        run, _ = request_analysis(self.db, self.doc.id)
        self.db.commit()
        same, created = request_analysis(self.db, self.doc.id)
        self.assertFalse(created)
        self.assertEqual(run.id, same.id)
        other, created = request_analysis(self.db, self.doc.id, force=True)
        self.assertTrue(created)
        self.assertNotEqual(run.id, other.id)
        for block in self.blocks:
            block.ocr_text_raw = ""
        self.db.commit()
        self.assertEqual(
            self.client.post(
                f"/api/v2/insights/documents/{self.doc.id}", json={}
            ).status_code,
            422,
        )

    def test_unicode_large_block_and_illegal_citations(self):
        source = {
            "revision_id": 1,
            "block_id": 1,
            "page_id": 1,
            "page_number": 1,
            "text_type": "ocr_raw",
            "review_status": "pending",
            "bbox": [],
            "text": "😀" * 20001,
        }
        chunks = list(batches([source]))
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[-1][0]["offset"], 18000)
        items, _ = validated_items(
            json.dumps(
                {
                    "items": [
                        {
                            "kind": "event",
                            "title": "x",
                            "description": "x",
                            "revision_id": 1,
                            "quote": "😀😀",
                            "char_start": 0,
                        }
                    ]
                }
            ),
            chunks[-1],
        )
        self.assertEqual(items[0]["sources"][0]["char_start"], 18000)
        items, errors = validated_items(
            json.dumps(
                {
                    "items": [
                        {
                            "kind": "event",
                            "title": "x",
                            "description": "x",
                            "revision_id": 9,
                            "quote": "invented",
                        }
                    ]
                }
            ),
            chunks[-1],
        )
        self.assertFalse(items)
        self.assertTrue(errors)

    def test_dates_and_document_date_basis(self):
        for value, quote in [
            ("1792-09-24", "September 1792"),
            ("1792-02-31", "31 February 1792"),
            ("1792", "1702"),
        ]:
            self.assertIsNone(supported_date(value, quote, quote))
        self.assertEqual(
            supported_date("1792-09", "September 1792", "September 1792"), "1792-09"
        )
        source = {
            "revision_id": 1,
            "offset": 0,
            "text": "24 September 1792. A meeting discussed a prior duel.",
        }
        item = {
            "kind": "event",
            "title": "duel",
            "description": "prior",
            "revision_id": 1,
            "quote": source["text"],
            "char_start": 0,
            "date": "1792-09-24",
            "date_quote": "24 September 1792",
            "date_basis": "document_explicit",
        }
        items, _ = validated_items(json.dumps({"items": [item]}), [source])
        self.assertEqual(items[0]["date_basis"], "document_explicit")

    def test_failure_retry_cancel_and_update_during_generation(self):
        run, _ = request_analysis(self.db, self.doc.id, "ai")
        self.db.commit()
        with patch(
            "app.insights.service.gpt_service.complete",
            new=AsyncMock(side_effect=RuntimeError("offline")),
        ):
            with self.assertRaises(RuntimeError):
                asyncio.run(analyze(self.db, run.id))
        self.assertEqual(run.status, ExtractionStatus.FAILED)
        with patch("app.insights.api.dispatch") as dispatch:
            self.assertEqual(
                self.client.post(f"/api/v2/insights/runs/{run.id}/retry").json()[
                    "status"
                ],
                "pending",
            )
            dispatch.assert_called_once()
        self.client.post(f"/api/v2/insights/runs/{run.id}/cancel")
        with patch(
            "app.insights.service.gpt_service.complete", new=AsyncMock()
        ) as model:
            asyncio.run(analyze(self.db, run.id))
            model.assert_not_called()
        other, _ = request_analysis(self.db, self.doc.id, "ai", force=True)
        self.db.commit()

        async def changes(*args, **kwargs):
            self.blocks[0].ocr_text_raw += " Changed."
            self.db.commit()
            return self.completion(*args, **kwargs)

        with patch("app.insights.service.gpt_service.complete", new=changes):
            with self.assertRaises(ValueError):
                asyncio.run(analyze(self.db, other.id))
        self.assertFalse(other.output_summary["items"])
        self.assertTrue(payload(self.db, other)["stale"])

    def test_cancel_and_immediate_retry_cannot_publish_old_attempt(self):
        run, _ = request_analysis(self.db, self.doc.id, "ai")
        self.db.commit()

        async def cancelled(*args, **kwargs):
            self.client.post(f"/api/v2/insights/runs/{run.id}/cancel")
            with patch("app.insights.api.dispatch"):
                self.client.post(f"/api/v2/insights/runs/{run.id}/retry")
            return self.completion(*args, **kwargs)

        with patch("app.insights.service.gpt_service.complete", new=cancelled):
            asyncio.run(analyze(self.db, run.id))
        self.db.refresh(run)
        self.assertEqual(run.status, ExtractionStatus.PENDING)
        self.assertEqual(run.output_summary["items"], [])
        with patch(
            "app.insights.service.gpt_service.complete",
            new=AsyncMock(side_effect=self.completion),
        ):
            asyncio.run(analyze(self.db, run.id))
        self.db.refresh(run)
        self.assertEqual(run.status, ExtractionStatus.COMPLETED)
        self.assertEqual(len(run.output_summary["items"]), 3)

    def test_failed_batch_resumes_without_repeating_completed_batch(self):
        self.blocks[0].ocr_text_raw = "A" * 10000
        self.db.commit()
        run, _ = request_analysis(self.db, self.doc.id, "ai")
        self.db.commit()
        run.parameters = {**run.parameters, "batch_char_limit": 9000}
        self.db.commit()
        count = 0

        async def flaky(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError("second batch offline")
            return SimpleNamespace(
                text='{"items":[]}',
                token_usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

        with patch("app.insights.service.gpt_service.complete", new=flaky):
            with self.assertRaises(RuntimeError):
                asyncio.run(analyze(self.db, run.id))
        self.assertEqual(run.output_summary["completed_batches"], 1)
        with patch("app.insights.api.dispatch"):
            self.client.post(f"/api/v2/insights/runs/{run.id}/retry")
        with patch(
            "app.insights.service.gpt_service.complete",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    text='{"items":[]}',
                    token_usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
                )
            ),
        ) as model:
            asyncio.run(analyze(self.db, run.id))
            self.assertEqual(model.await_count, 1)
        self.db.refresh(run)
        self.assertEqual(
            run.output_summary["covered_characters"],
            run.output_summary["total_characters"],
        )

    def test_cross_page_original_unit_keeps_all_sources(self):
        from app.models import (
            ArchivalMetadata,
            SourceUnit,
            SourceUnitSpan,
            SourceUnitType,
            SegmentationStatus,
        )
        from app.workbench.versioning import current_revision

        metadata = ArchivalMetadata(document_id=self.doc.id)
        self.db.add(metadata)
        self.db.flush()
        unit = SourceUnit(
            archival_metadata_id=metadata.id,
            title="Cross page letter",
            unit_type=SourceUnitType.LETTER_INCOMING,
            segmentation_status=SegmentationStatus.APPROVED,
        )
        self.db.add(unit)
        self.db.flush()
        for index, block in enumerate(self.blocks):
            revision = current_revision(self.db, block)
            self.db.add(
                SourceUnitSpan(
                    source_unit_id=unit.id,
                    block_id=block.id,
                    reading_order=index,
                    revision_id=revision.id,
                    char_start=0,
                    char_end=len(revision.content),
                )
            )
        self.db.commit()
        run, _ = request_analysis(self.db, self.doc.id)
        entries = [e for e in run.output_summary["toc"] if e["toc_type"] == "original"]
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0]["page_start"], entries[0]["page_end"]), (1, 2))
        self.assertEqual(len(entries[0]["sources"]), 2)

    def test_hierarchical_summary_only_accepts_known_notes(self):
        from app.insights.service import summarize

        items = [
            {
                "id": str(i),
                "kind": "overview",
                "description": "内容" * 700,
                "sources": [{"revision_id": i, "char_start": 0, "char_end": 1}],
            }
            for i in range(20)
        ]
        seen = []

        async def aggregate(_prompt, text, **kwargs):
            notes = json.loads(text)
            seen.extend(n["id"] for n in notes)
            return SimpleNamespace(
                text=json.dumps(
                    {
                        "sections": [
                            {
                                "text": "有出处的汇总",
                                "source_ids": [n["id"] for n in notes],
                            }
                        ]
                    }
                )
            )

        with patch("app.insights.service.gpt_service.complete", new=aggregate):
            paragraphs = asyncio.run(summarize(items, lambda: None))
        self.assertTrue(all(str(i) in seen for i in range(20)))
        self.assertEqual(len(paragraphs[0]["sources"]), 20)
        with patch(
            "app.insights.service.gpt_service.complete",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    text='{"sections":[{"text":"invented","source_ids":["bad"]}]}'
                )
            ),
        ):
            with self.assertRaises(ValueError):
                asyncio.run(summarize(items, lambda: None))

    def test_total_batches_published_before_dispatch_and_slow_first_response(self):
        run, _ = request_analysis(self.db, self.doc.id, "ai")
        self.db.commit()
        self.assertEqual(run.output_summary["total_batches"], 1)
        self.assertEqual(run.output_summary["stage"], "queued")

        async def slow_first(*args, **kwargs):
            # A separate API session must see the in-flight batch before any
            # provider response has returned, including if that response fails.
            with Session(self.engine) as observer:
                visible = observer.get(ExtractionRun, run.id).output_summary
                self.assertEqual(visible["total_batches"], 1)
                self.assertEqual(visible["current_batch"], 1)
                self.assertEqual(visible["completed_batches"], 0)
                self.assertEqual(visible["stage"], "extracting")
            raise RuntimeError("first response unavailable")

        with patch("app.insights.service.gpt_service.complete", new=slow_first):
            with self.assertRaises(RuntimeError):
                asyncio.run(analyze(self.db, run.id))
        self.db.refresh(run)
        self.assertEqual(run.status, ExtractionStatus.FAILED)
        self.assertEqual(run.output_summary["total_batches"], 1)
        self.assertEqual(run.output_summary["completed_batches"], 0)

    def test_short_jobs_checkpoint_and_continue_without_duplicate_generation(self):
        self.blocks[0].ocr_text_raw = "A" * 10000
        self.db.commit()
        run, _ = request_analysis(self.db, self.doc.id, "ai")
        self.db.commit()
        self.assertEqual(run.output_summary["total_batches"], 3)
        response = SimpleNamespace(
            text='{"items":[]}',
            token_usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )
        with patch(
            "app.insights.service.gpt_service.complete",
            new=AsyncMock(return_value=response),
        ) as model:
            for done in [1, 2]:
                result = asyncio.run(analyze(self.db, run.id, max_batches=1))
                self.assertTrue(result["continue"])
                self.db.refresh(run)
                self.assertEqual(run.status, ExtractionStatus.PENDING)
                self.assertEqual(run.output_summary["completed_batches"], done)
            asyncio.run(analyze(self.db, run.id, max_batches=1))
            self.db.refresh(run)
            self.assertEqual(run.status, ExtractionStatus.COMPLETED)
            self.assertEqual(model.await_count, 3)
            self.assertEqual(model.await_args.kwargs["max_tokens"], 2600)
        self.assertEqual(
            run.output_summary["covered_characters"],
            run.output_summary["total_characters"],
        )

    def test_non_reasoning_option_is_scoped_to_supported_provider_and_model(self):
        from app.insights.service import provider_options
        from app.config import settings

        with patch.object(
            settings, "gpt_base_url", "https://api.siliconflow.cn/v1"
        ), patch.object(settings, "gpt_model", "deepseek-ai/DeepSeek-V3.2"):
            self.assertEqual(
                provider_options(), {"extra_body": {"enable_thinking": False}}
            )
        with patch.object(
            settings, "gpt_base_url", "https://example.com/v1"
        ), patch.object(settings, "gpt_model", "deepseek-ai/DeepSeek-V3.2"):
            self.assertEqual(provider_options(), {})
        with patch.object(settings, "gpt_model", "other-model"):
            self.assertEqual(provider_options(), {})

    def test_queue_continuation_and_publish_failure_preserve_checkpoint(self):
        from app.tasks.insight_tasks import analyze_document

        run, _ = request_analysis(self.db, self.doc.id, "ai")
        self.db.commit()
        with patch(
            "app.tasks.insight_tasks.SessionLocal", return_value=Session(self.engine)
        ), patch(
            "app.insights.service.analyze",
            new=AsyncMock(return_value={"continue": True}),
        ), patch.object(
            analyze_document, "delay"
        ) as queue:
            analyze_document.run(run.id)
            queue.assert_called_once_with(run.id)
        with patch(
            "app.tasks.insight_tasks.SessionLocal", return_value=Session(self.engine)
        ), patch(
            "app.insights.service.analyze",
            new=AsyncMock(return_value={"continue": True}),
        ), patch.object(
            analyze_document, "delay", side_effect=RuntimeError("broker offline")
        ):
            with self.assertRaises(RuntimeError):
                analyze_document.run(run.id)
        self.db.refresh(run)
        self.assertEqual(run.status, ExtractionStatus.FAILED)
        self.assertIn("下一批任务入队失败", run.error_message)
        self.assertEqual(run.output_summary["completed_batches"], 0)

    def test_timeout_splits_only_unfinished_span_and_preserves_unicode_offsets(self):
        from app.insights.service import decode_plan, snapshot

        self.blocks[0].ocr_text_raw = "😀" * 10000
        self.db.commit()
        run, _ = request_analysis(self.db, self.doc.id, "ai")
        self.db.commit()
        empty = SimpleNamespace(
            text='{"items":[]}',
            token_usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )
        with patch(
            "app.insights.service.gpt_service.complete",
            new=AsyncMock(return_value=empty),
        ):
            asyncio.run(analyze(self.db, run.id, max_batches=1))
        self.db.refresh(run)
        before = run.output_summary["covered_characters"]
        with patch(
            "app.insights.service.gpt_service.complete",
            new=AsyncMock(side_effect=asyncio.TimeoutError),
        ):
            result = asyncio.run(analyze(self.db, run.id, max_batches=1))
        self.db.refresh(run)
        self.assertTrue(result["continue"])
        self.assertEqual(run.output_summary["completed_batches"], 1)
        self.assertEqual(run.output_summary["covered_characters"], before)
        chunks = decode_plan(
            run.output_summary["batch_plan"], snapshot(self.db, self.doc.id)
        )
        self.assertEqual(chunks[1][0]["offset"], 4500)
        self.assertEqual(chunks[2][0]["offset"], 6750)
        with patch(
            "app.insights.service.gpt_service.complete",
            new=AsyncMock(return_value=empty),
        ):
            while run.status == ExtractionStatus.PENDING:
                asyncio.run(analyze(self.db, run.id, max_batches=1))
                self.db.refresh(run)
        self.assertEqual(run.status, ExtractionStatus.COMPLETED)
        self.assertEqual(
            run.output_summary["covered_characters"],
            run.output_summary["total_characters"],
        )

    def test_invalid_plan_cannot_repeat_or_omit_source_characters(self):
        from app.insights.service import decode_plan

        with self.assertRaises(ValueError):
            decode_plan(
                [[{"revision_id": 1, "offset": 1, "length": 2}]],
                [{"revision_id": 1, "text": "abc"}],
            )

    def test_summary_timeout_preserves_groups_and_resume_does_not_repeat_them(self):
        from app.insights.service import summarize
        import copy

        items = [
            {
                "id": str(i),
                "kind": "overview",
                "description": "A" * 2000,
                "sources": [{"revision_id": i, "char_start": 0, "char_end": 1}],
            }
            for i in range(8)
        ]
        saved = {}
        seen = []

        def checkpoint(state):
            saved.clear()
            saved.update(copy.deepcopy(state))

        async def model(_prompt, text, **kwargs):
            group = json.loads(text)
            seen.append([n["id"] for n in group])
            if len(seen) == 2:
                raise asyncio.TimeoutError()
            return SimpleNamespace(
                text=json.dumps(
                    {
                        "sections": [
                            {
                                "text": "有依据的概述",
                                "source_ids": [n["id"] for n in group],
                            }
                        ]
                    }
                )
            )

        with patch("app.insights.service.gpt_service.complete", new=model):
            with self.assertRaises(asyncio.TimeoutError):
                asyncio.run(summarize(items, lambda: None, checkpoint=checkpoint))
            self.assertEqual(saved["next_group"], 1)
            result = asyncio.run(
                summarize(
                    items, lambda: None, state=saved, checkpoint=lambda state: None
                )
            )
        self.assertEqual(seen.count(seen[0]), 1)
        self.assertEqual(
            {s["revision_id"] for s in result[0]["sources"]}, set(range(8))
        )

    def test_summary_short_job_yields_after_one_group(self):
        from app.insights.service import summarize, SummaryPending

        items = [
            {
                "id": str(i),
                "kind": "overview",
                "description": "B" * 2000,
                "sources": [{"revision_id": i, "char_start": 0, "char_end": 1}],
            }
            for i in range(8)
        ]
        state = {}

        async def model(_prompt, text, **kwargs):
            return SimpleNamespace(
                text=json.dumps(
                    {
                        "sections": [
                            {
                                "text": "概述",
                                "source_ids": [n["id"] for n in json.loads(text)],
                            }
                        ]
                    }
                )
            )

        with patch(
            "app.insights.service.gpt_service.complete",
            new=AsyncMock(side_effect=model),
        ) as provider:
            with self.assertRaises(SummaryPending):
                asyncio.run(summarize(items, lambda: None, state=state, max_groups=1))
        self.assertEqual(provider.await_count, 1)
        self.assertEqual(state["next_group"], 1)
        self.assertGreater(state["total_groups"], 1)

    def test_analysis_queue_resumes_persisted_summary_after_timeout(self):
        run, _ = request_analysis(self.db, self.doc.id, "ai")
        artifact = dict(run.output_summary)
        source = artifact["toc"][0]["sources"][0]
        artifact["items"] = [
            {
                "id": str(i),
                "kind": "overview",
                "description": "C" * 2000,
                "sources": [source],
            }
            for i in range(8)
        ]
        artifact["completed_batches"] = artifact["total_batches"]
        artifact["covered_characters"] = artifact["total_characters"]
        run.output_summary = artifact
        self.db.commit()
        calls = []

        async def model(_prompt, text, **kwargs):
            self.assertEqual(kwargs["mode"], "historical_insights_summary")
            ids = [n["id"] for n in json.loads(text)]
            calls.append(ids)
            return SimpleNamespace(
                text=json.dumps(
                    {"sections": [{"text": "有来源的聚合", "source_ids": ids}]}
                ),
                token_usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

        with patch("app.insights.service.gpt_service.complete", new=model):
            result = asyncio.run(analyze(self.db, run.id, max_batches=1))
        self.assertTrue(result["continue"])
        self.db.refresh(run)
        self.assertEqual(run.output_summary["summary_progress"]["next_group"], 1)
        with patch(
            "app.insights.service.gpt_service.complete",
            new=AsyncMock(side_effect=asyncio.TimeoutError),
        ):
            with self.assertRaises(asyncio.TimeoutError):
                asyncio.run(analyze(self.db, run.id, max_batches=1))
        self.db.refresh(run)
        self.assertEqual(run.status, ExtractionStatus.FAILED)
        self.assertIn("聚合", run.error_message)
        self.assertEqual(run.output_summary["summary_progress"]["next_group"], 1)
        run.status = ExtractionStatus.PENDING
        self.db.commit()
        with patch("app.insights.service.gpt_service.complete", new=model):
            for _ in range(8):
                asyncio.run(analyze(self.db, run.id, max_batches=1))
                self.db.refresh(run)
                if run.status == ExtractionStatus.COMPLETED:
                    break
        self.assertEqual(run.status, ExtractionStatus.COMPLETED)
        self.assertEqual(calls.count(calls[0]), 1)
        self.assertTrue(run.output_summary["summary"])
