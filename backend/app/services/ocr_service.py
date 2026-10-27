"""OCR service for processing documents."""

import base64
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, cast

from sqlalchemy.orm import Session

from app.models import Document, Page, Block, DocumentStatus, DocumentType
from app.schemas import DocumentUpdate, PageCreate, PageUpdate, BlockCreate
from app.repositories import DocumentRepository, PageRepository, BlockRepository
from app.services.paddle_service import paddle_service
from app.utils import (
    split_pdf_to_images,
    split_pdf_to_page_pdfs,
    get_document_pages_dir,
    get_document_results_dir,
    get_image_dimensions,
)
from app.core import logger, OCRServiceError
from app.config import settings
from app.services.correction_quality import ocr_warnings

ProgressCallback = Callable[[int, Optional[Dict[str, Any]]], None]


class OCRService:
    """Service for OCR processing."""

    def __init__(self, db: Session):
        self.db = db
        self.doc_repo = DocumentRepository(db)
        self.page_repo = PageRepository(db)
        self.block_repo = BlockRepository(db)

    async def process_document(
        self,
        document_id: int,
        visualize: bool = False,
        restructure_pages: bool = True,
        merge_tables: bool = True,
        relevel_titles: bool = True,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Document:
        """
        Process a document through OCR.

        Args:
            document_id: Document ID
            visualize: Whether to generate visualization
            restructure_pages: Whether to restructure pages
            merge_tables: Whether to merge tables
            relevel_titles: Whether to relevel titles

        Returns:
            Updated document
        """
        document = self.doc_repo.get_by_id(document_id)
        if not document:
            raise OCRServiceError(f"Document {document_id} not found")

        file_path = Path(cast(str, document.file_path))
        document_file_type = cast(DocumentType, document.file_type)
        resolved_document_id = cast(int, document.id)

        previous_status = cast(DocumentStatus, document.status)
        self.doc_repo.update(
            document_id,
            DocumentUpdate(
                status=DocumentStatus.PROCESSING,
                error_message=None,
            ),
        )

        try:
            pages_dir = get_document_pages_dir(document_id)
            results_dir = get_document_results_dir(document_id)

            if progress_callback:
                progress_callback(5, {"stage": "preparing_document"})

            if document_file_type == DocumentType.PDF:
                resume_failed = previous_status == DocumentStatus.FAILED
                full_markdown = await self._process_pdf(
                    resolved_document_id,
                    file_path,
                    pages_dir,
                    results_dir,
                    visualize,
                    restructure_pages,
                    merge_tables,
                    relevel_titles,
                    progress_callback,
                    resume_existing=resume_failed,
                )
            else:
                full_markdown = await self._process_image(
                    resolved_document_id,
                    file_path,
                    pages_dir,
                    results_dir,
                    visualize,
                    restructure_pages,
                    merge_tables,
                    relevel_titles,
                    progress_callback,
                )

            self.doc_repo.update(
                document_id,
                DocumentUpdate(
                    status=DocumentStatus.OCR_COMPLETED,
                    full_markdown=full_markdown,
                ),
            )
            logger.info(f"OCR completed for document {document_id}")

        except Exception as exc:
            logger.error(f"OCR failed for document {document_id}: {exc}")
            self.doc_repo.update_status(document_id, DocumentStatus.FAILED, str(exc))
            raise

        updated_document = self.doc_repo.get_by_id(document_id)
        if not updated_document:
            raise OCRServiceError(
                f"Document {document_id} not found after OCR processing"
            )
        return updated_document

    async def _process_pdf(
        self,
        document_id: int,
        file_path: Path,
        pages_dir: Path,
        results_dir: Path,
        visualize: bool,
        restructure_pages: bool,
        merge_tables: bool,
        relevel_titles: bool,
        progress_callback: Optional[ProgressCallback] = None,
        resume_existing: bool = False,
    ) -> str:
        """Process PDF pages sequentially, optionally resuming persisted results."""
        page_images = split_pdf_to_images(file_path, pages_dir)
        page_pdfs = split_pdf_to_page_pdfs(file_path, results_dir / "ocr_page_pdfs")
        if len(page_images) != len(page_pdfs):
            raise OCRServiceError(
                "Rendered image count does not match single-page PDF count"
            )
        logger.info("Prepared %s PDF pages for sequential OCR", len(page_images))
        if progress_callback:
            progress_callback(
                15,
                {
                    "stage": "pdf_pages_rendered",
                    "page_count": len(page_images),
                    "message": "PDF pages will be processed sequentially.",
                },
            )

        total_pages = len(page_images)
        self.doc_repo.update(document_id, DocumentUpdate(page_count=total_pages))

        page_markdowns: List[str] = []
        restructure_inputs: List[Dict[str, Any]] = []
        for idx, ((image_path, width, height), page_pdf) in enumerate(
            zip(page_images, page_pdfs)
        ):
            page_number = idx + 1
            persisted = (
                self._load_persisted_page_result(document_id, page_number, results_dir)
                if resume_existing
                else None
            )
            if persisted:
                page, page_result = persisted
                logger.info(
                    "Resuming document %s: reused OCR result for page %s",
                    document_id,
                    page_number,
                )
            else:
                try:
                    page_ocr_result = await paddle_service.process_pdf(
                        page_pdf,
                        visualize=visualize,
                        restructure_pages=False,
                        merge_tables=merge_tables,
                        relevel_titles=relevel_titles,
                        layout_shape_mode="rect",
                        max_pixels=settings.ocr_pdf_max_pixels,
                        max_new_tokens=settings.ocr_pdf_max_new_tokens,
                    )
                except OCRServiceError as exc:
                    raise OCRServiceError(
                        f"PDF page {page_number} failed", str(exc)
                    ) from exc
                page_results = page_ocr_result.get("layoutParsingResults", [])
                if not page_results:
                    raise OCRServiceError(
                        f"OCR API returned no result for PDF page {page_number}"
                    )
                page_result = page_results[0]
                page = await self._persist_page_result(
                    document_id=document_id,
                    page_number=page_number,
                    image_path=image_path,
                    width=width,
                    height=height,
                    results_dir=results_dir,
                    result=page_result,
                )

            page_markdown = self._get_page_markdown(page)
            if page_markdown:
                page_markdowns.append(page_markdown)
            restructure_inputs.append(
                {
                    "prunedResult": page_result.get("prunedResult", {}),
                    "markdownImages": page_result.get("markdownImages"),
                }
            )
            if progress_callback:
                progress = 15 + int((page_number / total_pages) * 75)
                progress_callback(
                    progress,
                    {
                        "stage": "processing_pages",
                        "page_number": page_number,
                        "page_count": total_pages,
                        "resumed": bool(persisted),
                    },
                )

        restructured = None
        if restructure_pages and restructure_inputs:
            restructured = await paddle_service.restructure_pages(
                pages=restructure_inputs,
                merge_tables=merge_tables,
                relevel_titles=relevel_titles,
            )
        document_markdown = self._resolve_document_markdown(
            restructured, page_markdowns, {"fullMarkdown": ""}
        )
        self._write_document_markdown(results_dir, document_markdown)
        if progress_callback:
            progress_callback(
                98, {"stage": "finalizing_document", "page_count": total_pages}
            )
        return document_markdown

    async def _process_image(
        self,
        document_id: int,
        file_path: Path,
        pages_dir: Path,
        results_dir: Path,
        visualize: bool,
        restructure_pages: bool,
        merge_tables: bool,
        relevel_titles: bool,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> str:
        """Process single image document."""
        import shutil

        dest_path = pages_dir / f"page_0001{file_path.suffix}"
        shutil.copy(file_path, dest_path)

        width, height = get_image_dimensions(file_path)
        self.doc_repo.update(document_id, DocumentUpdate(page_count=1))
        if progress_callback:
            progress_callback(20, {"stage": "image_uploaded", "page_count": 1})

        ocr_started = time.monotonic()
        result = await paddle_service.process_image(
            dest_path,
            visualize=visualize,
            restructure_pages=False,
            merge_tables=merge_tables,
            relevel_titles=relevel_titles,
            layout_shape_mode="rect",
            max_pixels=settings.ocr_image_max_pixels,
            max_new_tokens=settings.ocr_image_max_new_tokens,
        )
        ocr_seconds = time.monotonic() - ocr_started
        logger.info(
            "Single-image PaddleOCR completed document=%s seconds=%.2f",
            document_id,
            ocr_seconds,
        )
        page_result = result.get("layoutParsingResults", [])
        resolved_page_result = page_result[0] if page_result else {}

        persistence_started = time.monotonic()
        page = await self._persist_page_result(
            document_id=document_id,
            page_number=1,
            image_path=dest_path,
            width=width,
            height=height,
            results_dir=results_dir,
            result=resolved_page_result,
        )
        persistence_seconds = time.monotonic() - persistence_started
        logger.info(
            "Single-image OCR persistence completed document=%s seconds=%.2f",
            document_id,
            persistence_seconds,
        )

        page_markdown = self._get_page_markdown(page)
        document_markdown = page_markdown or result.get("fullMarkdown", "") or ""
        self._write_document_markdown(results_dir, document_markdown)
        if progress_callback:
            progress_callback(98, {"stage": "finalizing_document", "page_count": 1})
        return document_markdown

    def _load_persisted_page_result(
        self,
        document_id: int,
        page_number: int,
        results_dir: Path,
    ) -> Optional[tuple[Page, Dict[str, Any]]]:
        """Load a completed page result for failed-document resumption.

        Args:
            document_id: Document owning the page.
            page_number: One-based page number.
            results_dir: Document results directory.

        Returns:
            Existing page and normalized persisted result, or None when incomplete.
        """
        page = self.page_repo.get_by_document_and_number(document_id, page_number)
        page_results_dir = results_dir / f"page_{page_number:04d}"
        markdown_path = page_results_dir / "content.md"
        pruned_path = page_results_dir / "pruned_result.json"
        if not page or not markdown_path.exists() or not pruned_path.exists():
            return None
        try:
            pruned_result = json.loads(pruned_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Ignoring invalid persisted OCR result for document %s page %s: %s",
                document_id,
                page_number,
                exc,
            )
            return None
        if not isinstance(pruned_result, dict):
            return None
        return page, {
            "markdown": markdown_path.read_text(encoding="utf-8"),
            "markdownImages": None,
            "prunedResult": pruned_result,
        }

    async def _persist_page_result(
        self,
        document_id: int,
        page_number: int,
        image_path: Optional[Path],
        width: Optional[int],
        height: Optional[int],
        results_dir: Path,
        result: Dict[str, Any],
    ) -> Page:
        """Persist OCR output for a single page."""
        logger.info(f"Processing page {page_number} for document {document_id}")

        page_results_dir = results_dir / f"page_{page_number:04d}"
        page_results_dir.mkdir(parents=True, exist_ok=True)

        resolved_image_path = self._persist_input_image(
            page_results_dir, result, image_path
        )
        # Now that _persist_input_image always returns the high-res fallback,
        # resolved_image_path == image_path, so we use the provided dimensions directly.
        resolved_width = width
        resolved_height = height
        if resolved_image_path and (resolved_width is None or resolved_height is None):
            resolved_width, resolved_height = get_image_dimensions(resolved_image_path)

        existing_page = self.page_repo.get_by_document_and_number(
            document_id, page_number
        )
        if existing_page:
            page = existing_page
            page_id = cast(int, page.id)
            self.block_repo.delete_by_page(page_id)
        else:
            page_data = PageCreate(
                document_id=document_id,
                page_number=page_number,
                image_path=str(resolved_image_path) if resolved_image_path else None,
                width=resolved_width,
                height=resolved_height,
            )
            page = self.page_repo.create(page_data)
            page_id = cast(int, page.id)

        markdown_content = (
            result.get("markdown", "") if isinstance(result, dict) else ""
        )
        markdown_path = page_results_dir / "content.md"
        markdown_path.write_text(markdown_content, encoding="utf-8")

        pruned_result = (
            result.get("prunedResult", {}) if isinstance(result, dict) else {}
        )
        pruned_path = page_results_dir / "pruned_result.json"
        pruned_path.write_text(
            json.dumps(pruned_result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        visualization_path = self._persist_output_image(
            page_results_dir,
            result.get("outputImages") if isinstance(result, dict) else None,
        )

        page_update = PageUpdate(
            image_path=str(resolved_image_path) if resolved_image_path else None,
            markdown_content=markdown_content,
            pruned_result_path=str(pruned_path),
            visualization_path=visualization_path,
            width=resolved_width,
            height=resolved_height,
        )
        updated_page = self.page_repo.update(page_id, page_update)
        if not updated_page:
            raise OCRServiceError(f"Failed to update page {page_id}")

        saved_blocks = self._save_blocks(
            page_id, result, resolved_width, resolved_height
        )
        is_pdf = (
            getattr(self.doc_repo.get_by_id(document_id), "file_type", None)
            == DocumentType.PDF
        )
        quality = {
            "blocks": [
                {"block_id": b.id, "warnings": ocr_warnings(b.ocr_text_raw or "")}
                for b in saved_blocks
                if ocr_warnings(b.ocr_text_raw or "")
            ],
            "recognition_max_pixels": (
                settings.ocr_pdf_max_pixels if is_pdf else settings.ocr_image_max_pixels
            ),
            "recognition_max_tokens": (
                settings.ocr_pdf_max_new_tokens
                if is_pdf
                else settings.ocr_image_max_new_tokens
            ),
            "note": "风险提示并非 CER 或识别正确率；需要人工真值评估。",
        }
        (page_results_dir / "ocr_quality.json").write_text(
            json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return updated_page

    def _persist_input_image(
        self,
        page_results_dir: Path,
        result: Dict[str, Any],
        fallback_image_path: Optional[Path],
    ) -> Optional[Path]:
        """Always use the high-resolution fallback image.

        PaddleOCR may return a downsampled inputImage when maxPixels is set,
        creating a coordinate-space mismatch: bbox coords are in one resolution
        while the image is in another. Always using the high-res fallback ensures
        page.width/height matches the bbox coordinate canvas.
        """
        return fallback_image_path

    def _persist_output_image(
        self, page_results_dir: Path, output_images: Any
    ) -> Optional[str]:
        """Persist a visualization image when present."""
        if isinstance(output_images, dict):
            vis_data = next((value for value in output_images.values() if value), None)
        elif isinstance(output_images, list):
            vis_data = next((value for value in output_images if value), None)
        else:
            vis_data = None

        if not vis_data:
            return None

        vis_path = page_results_dir / "visualization.png"
        vis_path.write_bytes(base64.b64decode(vis_data))
        return str(vis_path)

    def _get_page_markdown(self, page: Page) -> str:
        """Safely read markdown content from a page model."""
        page_markdown = getattr(page, "markdown_content", None)
        return page_markdown if isinstance(page_markdown, str) else ""

    def _resolve_document_markdown(
        self,
        restructured: Any,
        page_markdowns: List[str],
        pdf_result: Dict[str, Any],
    ) -> str:
        """Resolve full-document markdown from available OCR outputs."""
        if isinstance(restructured, dict):
            markdown = restructured.get("markdown")
            if isinstance(markdown, str) and markdown.strip():
                return markdown

        if page_markdowns:
            joined_markdown = "\n\n".join(
                markdown for markdown in page_markdowns if markdown
            )
            if joined_markdown.strip():
                return joined_markdown

        full_markdown = pdf_result.get("fullMarkdown")
        if isinstance(full_markdown, str):
            return full_markdown
        return ""

    def _write_document_markdown(self, results_dir: Path, markdown: str) -> None:
        """Write document-level markdown artifact."""
        document_markdown_path = results_dir / "document.md"
        document_markdown_path.write_text(markdown or "", encoding="utf-8")

    def _save_blocks(
        self,
        page_id: int,
        result: Dict[str, Any],
        page_width: Optional[int] = None,
        page_height: Optional[int] = None,
    ) -> List[Block]:
        """Parse OCR blocks and persist them in one database transaction.

        Args:
            page_id: Page owning the blocks.
            result: Raw PaddleOCR page result.
            page_width: Width of the stored page image, used as the bbox canvas.
            page_height: Height of the stored page image, used as the bbox canvas.

        Returns:
            Persisted blocks.
        """
        block_items = self._extract_block_items(result)

        if not block_items and isinstance(result, dict):
            logger.warning(
                "No OCR blocks extracted for page %s. Available result keys: %s",
                page_id,
                sorted(result.keys()),
            )
            pruned_result = result.get("prunedResult")
            if isinstance(pruned_result, dict):
                logger.warning(
                    "No OCR blocks extracted for page %s. Available prunedResult keys: %s",
                    page_id,
                    sorted(pruned_result.keys()),
                )
            block_items = self._build_markdown_fallback_blocks(result)

        block_schemas = [
            block_schema
            for block_index, block_data in enumerate(block_items)
            if (
                block_schema := self._build_block_create(
                    page_id, block_index, block_data
                )
            )
            is not None
        ]
        scale_x, scale_y = self._bbox_scale(result, page_width, page_height)
        if scale_x != 1.0 or scale_y != 1.0:
            logger.info(
                "Rescaling bboxes for page %s by (%.4f, %.4f) to match stored image",
                page_id,
                scale_x,
                scale_y,
            )
            for schema in block_schemas:
                x1, y1, x2, y2 = schema.bbox[:4]
                schema.bbox = [x1 * scale_x, y1 * scale_y, x2 * scale_x, y2 * scale_y]
        blocks = self.block_repo.create_many(block_schemas) if block_schemas else []
        logger.info("Saved %s blocks for page %s", len(blocks), page_id)
        return blocks

    def _extract_block_items(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract normalized block items from Paddle results."""
        if not isinstance(result, dict):
            return []

        direct_blocks = result.get("blocks")
        if isinstance(direct_blocks, list) and direct_blocks:
            return [block for block in direct_blocks if isinstance(block, dict)]

        pruned_result = result.get("prunedResult", {})
        candidates: List[Any] = []
        if isinstance(pruned_result, dict):
            for key in (
                "parsing_res_list",
                "parsing_res",
                "blocks",
                "block_infos",
                "layout_det_res",
            ):
                value = pruned_result.get(key)
                if value:
                    candidates.append(value)
            res_value = pruned_result.get("res")
            if isinstance(res_value, dict):
                for key in (
                    "parsing_res_list",
                    "parsing_res",
                    "blocks",
                    "block_infos",
                    "layout_det_res",
                ):
                    value = res_value.get(key)
                    if value:
                        candidates.append(value)

        extracted: List[Dict[str, Any]] = []
        for candidate in candidates:
            extracted.extend(self._flatten_block_candidates(candidate))

        return extracted

    def _build_markdown_fallback_blocks(
        self, result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Build coarse fallback blocks from page markdown when structured blocks are missing."""
        markdown = result.get("markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            return []

        paragraphs = [
            segment.strip() for segment in markdown.split("\n\n") if segment.strip()
        ]
        if not paragraphs:
            paragraphs = [
                line.strip() for line in markdown.splitlines() if line.strip()
            ]
        if not paragraphs:
            return []

        fallback_blocks: List[Dict[str, Any]] = []
        total_blocks = len(paragraphs)
        for index, paragraph in enumerate(paragraphs):
            top = float(index) / float(total_blocks)
            bottom = float(index + 1) / float(total_blocks)
            fallback_blocks.append(
                {
                    "label": "markdown_fallback",
                    "bbox": [0.0, top, 1.0, bottom],
                    "text": paragraph,
                    "confidence": None,
                    "bbox_normalized": True,
                }
            )

        logger.warning(
            "Using markdown fallback blocks for page because Paddle did not return structured block geometry"
        )
        return fallback_blocks

    def _flatten_block_candidates(self, value: Any) -> List[Dict[str, Any]]:
        """Flatten nested block candidate structures."""
        if isinstance(value, list):
            list_items: List[Dict[str, Any]] = []
            for item in value:
                list_items.extend(self._flatten_block_candidates(item))
            return list_items

        if isinstance(value, dict):
            bbox = (
                value.get("bbox")
                or value.get("block_bbox")
                or value.get("poly")
                or value.get("box")
                or value.get("coordinate")
            )
            if bbox:
                return [value]

            layout_boxes = value.get("boxes")
            if isinstance(layout_boxes, list):
                return [item for item in layout_boxes if isinstance(item, dict)]

            nested_items: List[Dict[str, Any]] = []
            for nested_key in (
                "res",
                "blocks",
                "children",
                "parsing_res_list",
                "parsing_res",
                "block_infos",
                "sub_blocks",
            ):
                nested_value = value.get(nested_key)
                if nested_value:
                    nested_items.extend(self._flatten_block_candidates(nested_value))
            return nested_items

        return []

    def _build_block_create(
        self,
        page_id: int,
        block_index: int,
        block_data: Dict[str, Any],
    ) -> Optional[BlockCreate]:
        """Build a block schema from normalized OCR data."""
        bbox = (
            block_data.get("bbox")
            or block_data.get("block_bbox")
            or block_data.get("poly")
            or block_data.get("box")
            or block_data.get("coordinate")
        )
        if not bbox or not isinstance(bbox, list):
            return None

        normalized_bbox = self._normalize_bbox(bbox)
        text = (
            block_data.get("text")
            or block_data.get("content")
            or block_data.get("block_content")
            or block_data.get("md")
            or ""
        )

        block_create = BlockCreate(
            page_id=page_id,
            block_index=block_index,
            block_label=block_data.get("label")
            or block_data.get("type")
            or block_data.get("block_label")
            or "text",
            bbox=normalized_bbox,
            confidence=block_data.get("confidence", block_data.get("score")),
            ocr_text_raw=text,
        )

        return block_create

    @staticmethod
    def _bbox_scale(
        result: Dict[str, Any],
        page_width: Optional[int],
        page_height: Optional[int],
    ) -> tuple[float, float]:
        """Compute the factor mapping PaddleOCR's canvas onto the stored page image.

        PaddleOCR renders PDF input at its own resolution, so its bbox canvas
        (prunedResult.width/height) can differ from the locally rendered page image.

        Args:
            result: Raw PaddleOCR page result.
            page_width: Width of the stored page image.
            page_height: Height of the stored page image.

        Returns:
            (scale_x, scale_y); (1.0, 1.0) when sizes are unknown or already match.
        """
        pruned = result.get("prunedResult") if isinstance(result, dict) else None
        if not isinstance(pruned, dict) or not page_width or not page_height:
            return 1.0, 1.0
        src_width = pruned.get("width")
        src_height = pruned.get("height")
        if not isinstance(src_width, (int, float)) or not isinstance(
            src_height, (int, float)
        ):
            return 1.0, 1.0
        if src_width <= 0 or src_height <= 0:
            return 1.0, 1.0
        scale_x = page_width / src_width
        scale_y = page_height / src_height
        if abs(scale_x - 1.0) < 0.01 and abs(scale_y - 1.0) < 0.01:
            return 1.0, 1.0
        return scale_x, scale_y

    def _normalize_bbox(self, bbox: List[Any]) -> List[float]:
        """Normalize bbox arrays to [x1, y1, x2, y2]."""
        if len(bbox) == 4 and all(not isinstance(item, list) for item in bbox):
            values = [float(item) for item in bbox]
            if all(0.0 <= value <= 1.0 for value in values):
                return [
                    values[0] * 1000.0,
                    values[1] * 1000.0,
                    values[2] * 1000.0,
                    values[3] * 1000.0,
                ]
            return values

        if len(bbox) == 8 and all(not isinstance(item, list) for item in bbox):
            xs = [float(bbox[i]) for i in range(0, 8, 2)]
            ys = [float(bbox[i]) for i in range(1, 8, 2)]
            return [min(xs), min(ys), max(xs), max(ys)]

        if all(isinstance(item, list) and len(item) == 2 for item in bbox):
            xs = [float(point[0]) for point in bbox]
            ys = [float(point[1]) for point in bbox]
            return [min(xs), min(ys), max(xs), max(ys)]

        return [float(item) for item in bbox[:4]]
