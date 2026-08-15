"""Regression tests for page-batched historical OCR correction."""
import importlib
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from httpx import Request
from openai import APITimeoutError

from app.config import settings
from app.core import GPTServiceError
from app.schemas import (
    GPTCompletionResultSchema,
    PageCorrectionBlockInputSchema,
    PageCorrectionBlockOutputSchema,
    PageCorrectionCallResultSchema,
    PageCorrectionRequestSchema,
    TokenUsageSchema,
)
from app.services.gpt_service import GPTService
from app.tasks.gpt_tasks import (
    ADJACENT_CONTEXT_BLOCKS,
    _build_page_request,
    _process_correction_page,
    _select_correction_candidate,
)


class FakeBlockRepository:
    """Minimal block repository used by page-task tests."""

    def __init__(self, blocks_by_page: dict[int, list], eligible: list) -> None:
        self.blocks_by_page = blocks_by_page
        self.eligible = eligible
        self.update_args = None

    def get_by_page(self, page_id: int) -> list:
        """Return configured blocks for a page."""
        return self.blocks_by_page.get(page_id, [])

    def get_by_document(self, document_id: int) -> list:
        """Return all configured document blocks."""
        return [block for blocks in self.blocks_by_page.values() for block in blocks]

    def get_unprocessed_by_page(self, page_id: int) -> list:
        """Return configured eligible blocks."""
        return self.eligible

    def update_page_corrections(
        self,
        page_id: int,
        corrections: dict[int, str],
        expected_raw_texts: dict[int, str],
    ) -> list:
        """Record the atomic update arguments."""
        self.update_args = (page_id, corrections, expected_raw_texts)
        return self.eligible

def make_page(page_id: int, number: int, document_id: int = 1) -> SimpleNamespace:
    """Create a page-shaped test object."""
    return SimpleNamespace(id=page_id, page_number=number, document_id=document_id)


def make_block(
    block_id: int,
    raw: str,
    index: int = 0,
    label: str = "text",
    page: SimpleNamespace | None = None,
) -> SimpleNamespace:
    """Create a block-shaped test object with layout provenance."""
    return SimpleNamespace(
        id=block_id,
        page_id=getattr(page, "id", 0),
        page=page,
        block_index=index,
        block_label=label,
        bbox=[0, index * 10, 100, index * 10 + 8],
        confidence=0.95,
        ocr_text_raw=raw,
        ocr_text_corrected=None,
        ocr_correction_source_text=None,
        modern_english=None,
        translation_zh=None,
    )


class GPTPageResponseTests(unittest.TestCase):
    """Validate strict structured page responses."""

    def setUp(self) -> None:
        self.service = GPTService()

    def test_accepts_complete_fenced_json(self) -> None:
        response = self.service._parse_page_response(
            '```json\n{"blocks":[{"block_id":2,"ocr_text_corrected":"B"},'
            '{"block_id":1,"ocr_text_corrected":"A"}]}\n```',
            {1, 2},
        )
        self.assertEqual([item.block_id for item in response.blocks], [2, 1])

    def test_rejects_missing_block_id(self) -> None:
        with self.assertRaises(GPTServiceError):
            self.service._parse_page_response(
                '{"blocks":[{"block_id":1,"ocr_text_corrected":"A"}]}',
                {1, 2},
            )

    def test_rejects_duplicate_block_id(self) -> None:
        with self.assertRaises(GPTServiceError):
            self.service._parse_page_response(
                '{"blocks":[{"block_id":1,"ocr_text_corrected":"A"},'
                '{"block_id":1,"ocr_text_corrected":"B"}]}',
                {1},
            )

class HistoricalCandidateTests(unittest.TestCase):
    """Validate deterministic preservation and correction gates."""

    def test_accepts_supported_formulaic_and_morphology_corrections(self) -> None:
        self.assertEqual(
            _select_correction_candidate("tender more regular", "render more regular"),
            "render more regular",
        )
        self.assertEqual(
            _select_correction_candidate(
                "well quality for executing that Office",
                "well qualified for executing that Office",
            ),
            "well qualified for executing that Office",
        )

    def test_preserves_historical_forms(self) -> None:
        examples = {
            "for the publick service": "for the public service",
            "I shall shew it": "I shall show it",
            "John Smith Esqr.": "John Smith Esquire",
            "Wm. Brown": "William Brown",
        }
        for raw, modernization in examples.items():
            with self.subTest(raw=raw):
                self.assertEqual(
                    _select_correction_candidate(raw, modernization), raw
                )

    def test_preserves_fact_bearing_title(self) -> None:
        raw = "appointed Secretary to the Secret and Superintending Committee"
        candidate = "appointed to the Secret and Superintending Committee"
        self.assertEqual(_select_correction_candidate(raw, candidate), raw)


class GPTPageTaskTests(unittest.TestCase):
    """Validate batching, structured context, and page boundaries."""

    def test_builds_separate_region_aware_page_context(self) -> None:
        previous_page = make_page(9, 1)
        page = make_page(10, 2)
        next_page = make_page(11, 3)
        previous = [
            make_block(90 + index, f"previous {index}", index, page=previous_page)
            for index in range(5)
        ]
        target = make_block(101, "body ends without punctuation", page=page)
        next_title = make_block(
            111, "SECRET COMMITTEE", label="title", page=next_page
        )

        request = _build_page_request(
            page,
            [target],
            [target],
            previous_page,
            previous,
            next_page,
            [next_title],
            previous + [target, next_title],
        )

        self.assertEqual(len(request.previous_page_context), ADJACENT_CONTEXT_BLOCKS)
        self.assertEqual(request.next_page_context[0].region_role, "title")
        self.assertEqual(request.next_boundary.assessment, "unlikely_continuation")
        self.assertEqual(request.blocks[0].ocr_text_raw, "body ends without punctuation")
        self.assertNotIn("SECRET COMMITTEE", request.blocks[0].ocr_text_raw)

    def test_document_references_require_target_overlap(self) -> None:
        """Exclude unrelated corrected blocks from document evidence."""
        page = make_page(10, 2)
        other_page = make_page(12, 4)
        target = make_block(101, "render the Office regular", page=page)
        related = make_block(121, "the Office was regular", page=other_page)
        related.ocr_text_corrected = "the Office was regular"
        related.ocr_correction_source_text = related.ocr_text_raw
        unrelated = make_block(122, "SECRET COMMITTEE", 1, "title", other_page)
        unrelated.ocr_text_corrected = "SECRET COMMITTEE"
        unrelated.ocr_correction_source_text = unrelated.ocr_text_raw

        request = _build_page_request(
            page,
            [target],
            [target],
            None,
            [],
            None,
            [],
            [target, related, unrelated],
        )

        reference_ids = {
            block.block_id for block in request.document_reference_blocks
        }
        self.assertIn(related.id, reference_ids)
        self.assertNotIn(unrelated.id, reference_ids)
        self.assertEqual(
            request.document_reference_blocks[0].corrected_text,
            related.ocr_text_corrected,
        )

    def test_stale_correction_is_not_context_evidence(self) -> None:
        """Expose corrected context only for an exact raw-source snapshot."""
        page = make_page(10, 2)
        other_page = make_page(12, 4)
        target = make_block(101, "the Office regular", page=page)
        stale = make_block(121, "the Office changed", page=other_page)
        stale.ocr_text_corrected = "the Office corrected"
        stale.ocr_correction_source_text = "older raw OCR"

        request = _build_page_request(
            page,
            [target],
            [target],
            None,
            [],
            None,
            [],
            [target, stale],
        )

        self.assertEqual(len(request.document_reference_blocks), 1)
        self.assertIsNone(request.document_reference_blocks[0].corrected_text)

    def test_processes_eligible_page_in_one_call(self) -> None:
        previous_page = make_page(9, 1)
        page = make_page(10, 2)
        next_page = make_page(11, 3)
        target = make_block(101, "target raw", page=page)
        previous = make_block(91, "previous evidence", page=previous_page)
        next_block = make_block(111, "next evidence", page=next_page)
        repo = FakeBlockRepository(
            {10: [target], 9: [previous], 11: [next_block]}, [target]
        )
        call_result = PageCorrectionCallResultSchema(
            blocks=[PageCorrectionBlockOutputSchema(
                block_id=101, ocr_text_corrected="target corrected"
            )],
            token_usage=TokenUsageSchema(
                prompt_tokens=10, completion_tokens=2, total_tokens=12,
                calls=1, calls_with_usage=1,
            ),
        )

        with patch(
            "app.tasks.gpt_tasks.gpt_service.correct_ocr_page",
            new=AsyncMock(return_value=call_result),
        ) as correction_call:
            result = _process_correction_page(repo, page, previous_page, next_page)

        correction_call.assert_awaited_once()
        request = correction_call.await_args.args[0]
        self.assertEqual(request.previous_page_context[0].original_ocr_text, "previous evidence")
        self.assertEqual(request.next_page_context[0].original_ocr_text, "next evidence")
        self.assertEqual(
            repo.update_args,
            (10, {101: "target corrected"}, {101: "target raw"}),
        )
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["llm_calls"], 1)

    def test_skips_page_without_eligible_blocks(self) -> None:
        page = make_page(10, 2)
        current = make_block(101, "already current", page=page)
        repo = FakeBlockRepository({10: [current]}, [])

        with patch(
            "app.tasks.gpt_tasks.gpt_service.correct_ocr_page",
            new=AsyncMock(),
        ) as correction_call:
            result = _process_correction_page(repo, page, None, None)

        correction_call.assert_not_awaited()
        self.assertTrue(result["page_skipped"])
        self.assertEqual(result["processed"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["llm_calls"], 0)


class GPTClientLifecycleTests(unittest.IsolatedAsyncioTestCase):
    """Ensure HTTP clients close before temporary worker loops are torn down."""

    async def test_request_closes_client_in_same_event_loop(self) -> None:
        service = GPTService()
        create_completion = AsyncMock(
            return_value=SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content="corrected text")
                )],
                usage=None,
            )
        )

        class FakeClient:
            """Minimal async OpenAI client context manager."""

            def __init__(self) -> None:
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=create_completion)
                )
                self.closed = False

            async def __aenter__(self) -> "FakeClient":
                return self

            async def __aexit__(self, exc_type, exc, traceback) -> None:
                self.closed = True

        client = FakeClient()
        with patch.object(service, "_create_client", return_value=client):
            result = await service._request_completion(
                "system", "user", "ocr_correction"
            )

        self.assertEqual(result.text, "corrected text")
        self.assertTrue(client.closed)
        create_completion.assert_awaited_once()
        request_options = create_completion.await_args.kwargs
        self.assertEqual(request_options["temperature"], 0.0)
        self.assertEqual(request_options["max_tokens"], 4096)
        self.assertNotIn("response_format", request_options)

    async def test_timeout_returns_actionable_service_error(self) -> None:
        """Report exhausted timeout retries without leaking request content."""
        service = GPTService()
        timeout_error = APITimeoutError(
            request=Request("POST", "https://provider.example/v1/chat/completions")
        )
        create_completion = AsyncMock(side_effect=timeout_error)

        class TimeoutClient:
            """Async client that always times out."""

            def __init__(self) -> None:
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=create_completion)
                )

            async def __aenter__(self) -> "TimeoutClient":
                return self

            async def __aexit__(self, exc_type, exc, traceback) -> None:
                return None

        with patch.object(service, "_create_client", return_value=TimeoutClient()), \
                patch.object(settings, "gpt_timeout", 300), \
                patch.object(settings, "gpt_max_retries", 2):
            with self.assertRaisesRegex(
                GPTServiceError, "read timeout: 300s, retries: 2"
            ):
                await service._request_completion(
                    "system", "private page text", "ocr_correction_page"
                )


class GPTClientConfigurationTests(unittest.TestCase):
    """Validate explicit SDK timeout and retry settings."""

    def test_client_uses_configured_timeout_and_retries(self) -> None:
        """Pass separate read timeout and retry count to the SDK."""
        service = GPTService()
        sentinel = object()
        gpt_service_module = importlib.import_module("app.services.gpt_service")
        with patch.object(settings, "gpt_api_key", "test-key"), \
                patch.object(settings, "gpt_timeout", 321), \
                patch.object(settings, "gpt_max_retries", 4), \
                patch.object(gpt_service_module, "AsyncOpenAI", return_value=sentinel) as client_class:
            client = service._create_client()

        self.assertIs(client, sentinel)
        options = client_class.call_args.kwargs
        self.assertEqual(options["timeout"].read, 321.0)
        self.assertEqual(options["timeout"].connect, 30.0)
        self.assertEqual(options["max_retries"], 4)


class GPTPromptFallbackTests(unittest.IsolatedAsyncioTestCase):
    """Validate safe historical defaults when prompt files are unavailable."""

    async def test_page_correction_uses_historical_fallback(self) -> None:
        service = GPTService()
        request = PageCorrectionRequestSchema(
            page_number=1,
            blocks=[PageCorrectionBlockInputSchema(
                block_id=1,
                block_index=0,
                ocr_text_raw="publick service",
            )],
        )
        completion = GPTCompletionResultSchema(
            text='{"blocks":[{"block_id":1,"ocr_text_corrected":"publick service"}]}',
            token_usage=TokenUsageSchema(calls=1),
        )

        with patch.object(
            service,
            "_load_prompt",
            side_effect=GPTServiceError("missing"),
        ), patch.object(
            service,
            "_request_completion",
            new=AsyncMock(return_value=completion),
        ) as completion_call:
            result = await service.correct_ocr_page(request)

        system_prompt = completion_call.await_args.args[0]
        request_options = completion_call.await_args.kwargs
        self.assertIn("do not polish or modernize", system_prompt)
        self.assertIn("publick", system_prompt)
        self.assertEqual(request_options["max_tokens"], settings.gpt_page_max_tokens)
        response_format = request_options["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        schema = response_format["json_schema"]["schema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(result.blocks[0].ocr_text_corrected, "publick service")

    async def test_page_correction_can_disable_structured_output(self) -> None:
        """Omit response_format for providers without structured output."""
        service = GPTService()
        request = PageCorrectionRequestSchema(
            page_number=1,
            blocks=[PageCorrectionBlockInputSchema(
                block_id=1,
                block_index=0,
                ocr_text_raw="publick service",
            )],
        )
        completion = GPTCompletionResultSchema(
            text='{"blocks":[{"block_id":1,"ocr_text_corrected":"publick service"}]}',
            token_usage=TokenUsageSchema(calls=1),
        )

        with patch.object(settings, "gpt_structured_output", False), \
                patch.object(
                    service,
                    "_request_completion",
                    new=AsyncMock(return_value=completion),
                ) as completion_call:
            await service.correct_ocr_page(request)

        self.assertIsNone(completion_call.await_args.kwargs["response_format"])

    def test_single_block_fallback_preserves_facts_and_forms(self) -> None:
        prompt = GPTService()._get_default_prompt("ocr_correction")
        self.assertIn("tender/render", prompt)
        self.assertIn("publick", prompt)
        self.assertIn("Secretary", prompt)
        self.assertIn("Modern-English rewriting is forbidden", prompt)


class PromptContractTests(unittest.TestCase):
    """Ensure historical restoration rules remain explicit in both prompts."""

    def test_prompts_cover_required_examples_and_preservation(self) -> None:
        prompt_dir = Path(__file__).parents[1] / "app" / "prompts"
        for filename in ("ocr_correction.txt", "ocr_correction_page.txt"):
            prompt = (prompt_dir / filename).read_text(encoding="utf-8")
            with self.subTest(filename=filename):
                self.assertIn("tender more regular", prompt)
                self.assertIn("well quality for executing that Office", prompt)
                self.assertIn("publick", prompt)
                self.assertIn("shew", prompt)
                self.assertIn("Esqr.", prompt)
                self.assertIn("appointed Secretary", prompt)
                self.assertIn("modern", prompt.lower())


if __name__ == "__main__":
    unittest.main()
