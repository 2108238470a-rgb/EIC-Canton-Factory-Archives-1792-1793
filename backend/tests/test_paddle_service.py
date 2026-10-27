"""Focused tests for PaddleOCR response and retry handling."""
import asyncio
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.core import OCRServiceError
from app.services.ocr_service import OCRService
from app.utils.pdf_utils import split_pdf_to_page_pdfs


MODULE_PATH = Path(__file__).parents[1] / "app" / "services" / "paddle_service.py"
SPEC = importlib.util.spec_from_file_location("paddle_service_under_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
service_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(service_module)
PaddleOCRService = service_module.PaddleOCRService


class PaddleOCRServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = PaddleOCRService()
        self.service.retry_backoff = 0

    def test_build_restructure_url(self) -> None:
        self.assertEqual(
            self.service._build_restructure_url(
                "http://127.0.0.1:8888/layout-parsing"
            ),
            "http://127.0.0.1:8888/restructure-pages",
        )

    def test_normalize_result(self) -> None:
        result = {
            "result": {
                "layoutParsingResults": [
                    {"markdown": {"text": "Page one", "images": {}}},
                    {"markdown": {"text": "Page two"}},
                ],
                "dataInfo": {"numPages": 2},
            }
        }
        normalized = self.service._normalize_result(result)
        self.assertEqual(normalized["fullMarkdown"], "Page one\n\nPage two")
        self.assertEqual(len(normalized["layoutParsingResults"]), 2)

    def test_rejects_empty_results(self) -> None:
        with self.assertRaises(OCRServiceError):
            self.service._normalize_result(
                {"result": {"layoutParsingResults": []}}
            )

    def test_sanitize_response_text(self) -> None:
        sanitized = self.service._sanitize_response_text("a\n b " + "x" * 20, limit=8)
        self.assertEqual(sanitized, "a b xxxx... [truncated]")

    def test_retry_transient_status(self) -> None:
        request = httpx.Request("POST", self.service.api_url)
        unavailable = httpx.Response(503, request=request)
        success = httpx.Response(200, request=request, json={"result": {}})
        client = AsyncMock()
        client.post = AsyncMock(side_effect=[unavailable, success])
        self.service.max_retries = 1

        with patch.object(service_module.asyncio, "sleep", new=AsyncMock()):
            response = asyncio.run(
                self.service._post_with_retry(client, self.service.api_url, {})
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.post.await_count, 2)

    def test_does_not_retry_internal_server_error(self) -> None:
        """Fail fast on 500 because the server may still be processing input."""
        request = httpx.Request("POST", self.service.api_url)
        server_error = httpx.Response(500, request=request)
        client = AsyncMock()
        client.post = AsyncMock(return_value=server_error)
        self.service.max_retries = 2

        with self.assertRaises(httpx.HTTPStatusError):
            asyncio.run(
                self.service._post_with_retry(client, self.service.api_url, {})
            )

        self.assertEqual(client.post.await_count, 1)

    def test_does_not_retry_read_error(self) -> None:
        """Avoid duplicate inference when the server drops a response stream."""
        request = httpx.Request("POST", self.service.api_url)
        client = AsyncMock()
        client.post = AsyncMock(
            side_effect=httpx.ReadError("connection dropped", request=request)
        )
        self.service.max_retries = 2

        with self.assertRaises(httpx.ReadError):
            asyncio.run(
                self.service._post_with_retry(client, self.service.api_url, {})
            )

        self.assertEqual(client.post.await_count, 1)

    def test_pdf_and_image_use_distinct_file_types(self) -> None:
        """Send PDFs as fileType 0 and images as fileType 1."""
        request = httpx.Request("POST", self.service.api_url)
        response = httpx.Response(
            200,
            request=request,
            json={
                "result": {
                    "layoutParsingResults": [
                        {"markdown": {"text": "text"}, "prunedResult": {}}
                    ]
                }
            },
        )
        client = AsyncMock()
        client.post = AsyncMock(return_value=response)
        client_context = MagicMock()
        client_context.__aenter__ = AsyncMock(return_value=client)
        client_context.__aexit__ = AsyncMock(return_value=None)

        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "page.pdf"
            image_path = Path(tmp_dir) / "page.png"
            pdf_path.write_bytes(b"pdf")
            image_path.write_bytes(b"image")
            with patch.object(
                service_module.httpx,
                "AsyncClient",
                return_value=client_context,
            ):
                asyncio.run(
                    self.service.process_pdf(pdf_path, restructure_pages=False)
                )
                pdf_payload = client.post.await_args.kwargs["json"]
                client.post.reset_mock()
                asyncio.run(
                    self.service.process_image(image_path, restructure_pages=False)
                )
                image_payload = client.post.await_args.kwargs["json"]

        self.assertEqual(pdf_payload["fileType"], 0)
        self.assertEqual(image_payload["fileType"], 1)

    def test_split_pdf_creates_ordered_single_page_files(self) -> None:
        """Create one ordered one-page PDF per source page."""
        import fitz

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source_path = root / "source.pdf"
            source = fitz.open()
            source.new_page().insert_text((72, 72), "first")
            source.new_page().insert_text((72, 72), "second")
            source.save(source_path)
            source.close()

            page_paths = split_pdf_to_page_pdfs(source_path, root / "pages")
            page_texts = []
            page_counts = []
            for page_path in page_paths:
                with fitz.open(page_path) as page_pdf:
                    page_counts.append(len(page_pdf))
                    page_texts.append(page_pdf[0].get_text().strip())

        self.assertEqual(
            [path.name for path in page_paths],
            ["page_0001.pdf", "page_0002.pdf"],
        )
        self.assertEqual(page_counts, [1, 1])
        self.assertEqual(page_texts, ["first", "second"])

    def test_reports_upload_timeout_separately(self) -> None:
        """Identify request-body upload timeouts instead of inference timeouts."""
        self.service.max_retries = 0
        request = httpx.Request("POST", self.service.api_url)
        client = AsyncMock()
        client.post = AsyncMock(
            side_effect=httpx.WriteTimeout("upload stalled", request=request)
        )
        client_context = MagicMock()
        client_context.__aenter__ = AsyncMock(return_value=client)
        client_context.__aexit__ = AsyncMock(return_value=None)

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "page.png"
            image_path.write_bytes(b"image")
            with patch.object(
                service_module.httpx,
                "AsyncClient",
                return_value=client_context,
            ):
                with self.assertRaisesRegex(
                    OCRServiceError, "upload timed out"
                ):
                    asyncio.run(
                        self.service.process_image(
                            image_path, restructure_pages=False
                        )
                    )

    def test_restructure_transport_failure_is_nonfatal(self) -> None:
        """Fall back when optional document restructuring times out."""
        request = httpx.Request("POST", self.service.restructure_url)
        with patch.object(
            self.service,
            "_restructure_pages",
            new=AsyncMock(
                side_effect=httpx.ReadTimeout("slow", request=request)
            ),
        ):
            result = asyncio.run(self.service.restructure_pages([]))

        self.assertIsNone(result)


class OCRServicePageFlowTests(unittest.TestCase):
    """Validate sequential PDF OCR persistence and resumption."""

    def setUp(self) -> None:
        self.service = OCRService(MagicMock())
        self.service.doc_repo = MagicMock()
        self.service.page_repo = MagicMock()
        self.service.block_repo = MagicMock()

    def test_failed_document_resumes_after_completed_page(self) -> None:
        """Reuse persisted pages and OCR only the first missing page onward."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            pages_dir = root / "pages"
            results_dir = root / "results"
            pages_dir.mkdir()
            results_dir.mkdir()
            page_one_image = pages_dir / "page_0001.png"
            page_two_image = pages_dir / "page_0002.png"
            page_one_image.write_bytes(b"one")
            page_two_image.write_bytes(b"two")

            page_one_result_dir = results_dir / "page_0001"
            page_one_result_dir.mkdir()
            (page_one_result_dir / "content.md").write_text(
                "Page one", encoding="utf-8"
            )
            (page_one_result_dir / "pruned_result.json").write_text(
                '{"parsing_res_list": []}', encoding="utf-8"
            )
            existing_page = SimpleNamespace(id=1, markdown_content="Page one")
            self.service.page_repo.get_by_document_and_number.side_effect = (
                lambda document_id, page_number: existing_page
                if page_number == 1 else None
            )
            page_one_pdf = root / "page_0001.pdf"
            page_two_pdf = root / "page_0002.pdf"
            page_one_pdf.write_bytes(b"pdf one")
            page_two_pdf.write_bytes(b"pdf two")
            persisted_page_two = SimpleNamespace(
                id=2, markdown_content="Page two"
            )
            process_pdf = AsyncMock(return_value={
                "layoutParsingResults": [{
                    "markdown": "Page two",
                    "markdownImages": None,
                    "prunedResult": {"parsing_res_list": []},
                }]
            })
            progress_events = []

            with patch(
                "app.services.ocr_service.split_pdf_to_images",
                return_value=[
                    (page_one_image, 100, 200),
                    (page_two_image, 100, 200),
                ],
            ), patch(
                "app.services.ocr_service.split_pdf_to_page_pdfs",
                return_value=[page_one_pdf, page_two_pdf],
            ), patch(
                "app.services.ocr_service.paddle_service.process_pdf",
                new=process_pdf,
            ), patch.object(
                self.service,
                "_persist_page_result",
                new=AsyncMock(return_value=persisted_page_two),
            ):
                markdown = asyncio.run(self.service._process_pdf(
                    document_id=48,
                    file_path=root / "source.pdf",
                    pages_dir=pages_dir,
                    results_dir=results_dir,
                    visualize=False,
                    restructure_pages=False,
                    merge_tables=True,
                    relevel_titles=True,
                    progress_callback=lambda progress, result: progress_events.append(
                        (progress, result)
                    ),
                    resume_existing=True,
                ))

        process_pdf.assert_awaited_once()
        self.assertEqual(process_pdf.await_args.args[0], page_two_pdf)
        self.assertEqual(process_pdf.await_args.kwargs["layout_shape_mode"], "rect")
        self.assertEqual(process_pdf.await_args.kwargs["max_pixels"], 4_200_000)
        self.assertEqual(process_pdf.await_args.kwargs["max_new_tokens"], 1024)
        self.assertEqual(markdown, "Page one\n\nPage two")
        self.assertTrue(progress_events[1][1]["resumed"])
        self.assertFalse(progress_events[2][1]["resumed"])

    def test_save_blocks_batches_block_create_schemas(self) -> None:
        """Persist normalized block schemas in one repository transaction."""
        saved = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        self.service.block_repo.create_many.return_value = saved

        blocks = self.service._save_blocks(
            7,
            {
                "blocks": [
                    {"bbox": [1, 2, 3, 4], "text": "first", "label": "text"},
                    {"bbox": [5, 6, 7, 8], "text": "second", "label": "title"},
                ]
            },
        )

        schemas = self.service.block_repo.create_many.call_args.args[0]
        self.assertEqual(len(schemas), 2)
        self.assertTrue(all(hasattr(item, "model_dump") for item in schemas))
        self.assertEqual(schemas[0].ocr_text_raw, "first")
        self.assertEqual(schemas[1].block_label, "title")
        self.assertEqual(blocks, saved)

    def test_page_rerun_reuses_row_and_replaces_blocks(self) -> None:
        """Avoid duplicate page rows when a page must be OCRed again."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            image_path = root / "page.png"
            image_path.write_bytes(b"image")
            existing_page = SimpleNamespace(id=7)
            updated_page = SimpleNamespace(id=7, markdown_content="Updated")
            self.service.page_repo.get_by_document_and_number.return_value = (
                existing_page
            )
            self.service.page_repo.update.return_value = updated_page

            with patch.object(self.service, "_save_blocks") as save_blocks:
                result = asyncio.run(self.service._persist_page_result(
                    document_id=48,
                    page_number=7,
                    image_path=image_path,
                    width=100,
                    height=200,
                    results_dir=root / "results",
                    result={
                        "markdown": "Updated",
                        "prunedResult": {},
                        "outputImages": None,
                    },
                ))

        self.assertIs(result, updated_page)
        self.service.page_repo.create.assert_not_called()
        self.service.block_repo.delete_by_page.assert_called_once_with(7)
        save_blocks.assert_called_once()


if __name__ == "__main__":
    unittest.main()
