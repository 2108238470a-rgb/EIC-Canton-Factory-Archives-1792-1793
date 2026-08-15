"""PaddleOCR service for calling local OCR API."""
import asyncio
import base64
import weakref
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.core import logger, OCRServiceError


class PaddleOCRService:
    """Service for interacting with local PaddleOCR-VL API."""

    RETRYABLE_STATUS_CODES = {429, 502, 503, 504}

    def __init__(self):
        self.api_url = settings.paddle_ocr_url
        self.restructure_url = self._build_restructure_url(self.api_url)
        self.model_name = settings.paddle_ocr_model_name
        self.timeout = httpx.Timeout(
            connect=float(settings.paddle_ocr_connect_timeout_seconds),
            read=float(settings.paddle_ocr_timeout_seconds),
            write=float(settings.paddle_ocr_write_timeout_seconds),
            pool=float(settings.paddle_ocr_connect_timeout_seconds),
        )
        self.max_retries = max(0, settings.paddle_ocr_retries)
        self.retry_backoff = max(0.0, settings.paddle_ocr_retry_backoff_seconds)
        self.max_file_bytes = max(1, settings.paddle_ocr_max_file_mb) * 1024 * 1024
        self.max_pixels = max(0, settings.paddle_ocr_max_pixels)
        self.max_new_tokens = max(0, settings.paddle_ocr_max_new_tokens)
        self.max_concurrency = max(1, settings.paddle_ocr_max_concurrency)
        self._semaphores: weakref.WeakKeyDictionary[Any, asyncio.Semaphore] = (
            weakref.WeakKeyDictionary()
        )

    async def process_file(
        self,
        file_path: Path,
        file_type: int,
        visualize: bool = False,
        restructure_pages: bool = True,
        merge_tables: bool = True,
        relevel_titles: bool = True,
        layout_shape_mode: str = "poly",
        max_pixels: Optional[int] = None,
        max_new_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Process a file through PaddleOCR-VL API."""
        try:
            file_size = file_path.stat().st_size
            if file_size > self.max_file_bytes:
                raise OCRServiceError(
                    f"Input file is {file_size / (1024 * 1024):.1f} MB; "
                    f"the configured limit is {self.max_file_bytes / (1024 * 1024):.0f} MB"
                )
            file_content = base64.b64encode(file_path.read_bytes()).decode("utf-8")
        except OSError as exc:
            logger.error(f"Failed to read file {file_path}: {exc}")
            raise OCRServiceError(f"Failed to read file: {str(exc)}") from exc

        payload: Dict[str, Any] = {
            "file": file_content,
            "fileType": file_type,
            "visualize": visualize,
            "restructurePages": restructure_pages,
        }
        if layout_shape_mode:
            payload["layoutShapeMode"] = layout_shape_mode
        resolved_max_pixels = self.max_pixels if max_pixels is None else max_pixels
        resolved_max_new_tokens = self.max_new_tokens if max_new_tokens is None else max_new_tokens
        if resolved_max_pixels:
            payload["maxPixels"] = resolved_max_pixels
        if resolved_max_new_tokens:
            payload["maxNewTokens"] = resolved_max_new_tokens
        if restructure_pages:
            payload["mergeTables"] = merge_tables
            payload["relevelTitles"] = relevel_titles

        logger.info(
            "Calling PaddleOCR API model=%s file=%s size_mb=%.1f visualize=%s",
            self.model_name,
            file_path,
            file_size / (1024 * 1024),
            visualize,
        )

        try:
            limits = httpx.Limits(
                max_connections=max(1, settings.paddle_ocr_max_concurrency),
                max_keepalive_connections=max(1, settings.paddle_ocr_max_concurrency),
            )
            async with self._get_semaphore():
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    limits=limits,
                    trust_env=settings.paddle_ocr_trust_env,
                ) as client:
                    response = await self._post_with_retry(client, self.api_url, payload)
                    result = self._decode_json_response(response)
                    logger.info(f"PaddleOCR API call successful for: {file_path}")
                    normalized_result = self._normalize_result(result)

                    if (
                        file_type == 0
                        and restructure_pages
                        and normalized_result["layoutParsingResults"]
                    ):
                        restructured = await self._restructure_pages(
                            client=client,
                            pages=normalized_result["layoutParsingResults"],
                            merge_tables=merge_tables,
                            relevel_titles=relevel_titles,
                        )
                        if restructured is not None:
                            normalized_result["restructured"] = restructured

                    return normalized_result

        except httpx.WriteTimeout as exc:
            logger.error(f"PaddleOCR API upload timeout for file: {file_path}")
            raise OCRServiceError(
                "OCR request upload timed out; process PDFs page by page or increase "
                "PADDLE_OCR_WRITE_TIMEOUT_SECONDS"
            ) from exc
        except httpx.ReadTimeout as exc:
            logger.error(f"PaddleOCR API response timeout for file: {file_path}")
            raise OCRServiceError(
                "OCR inference timed out; reduce image resolution or increase "
                "PADDLE_OCR_TIMEOUT_SECONDS"
            ) from exc
        except httpx.ConnectTimeout as exc:
            logger.error(f"PaddleOCR API connect timeout: {self.api_url}")
            raise OCRServiceError(
                "OCR connection timed out; verify the endpoint or increase "
                "PADDLE_OCR_CONNECT_TIMEOUT_SECONDS"
            ) from exc
        except httpx.TimeoutException as exc:
            logger.error(f"PaddleOCR API timeout for file: {file_path}")
            raise OCRServiceError("OCR request timed out") from exc
        except httpx.ConnectError as exc:
            logger.error(f"PaddleOCR API connection failed: {self.api_url}")
            raise OCRServiceError(
                f"Cannot connect to OCR endpoint {self.api_url}; confirm the model service is running"
            ) from exc
        except httpx.NetworkError as exc:
            error_type = type(exc).__name__
            logger.error(
                "PaddleOCR API network error type=%s endpoint=%s",
                error_type,
                self.api_url,
            )
            raise OCRServiceError(
                f"OCR network connection failed ({error_type}); retry the task when the OCR service is stable"
            ) from exc
        except httpx.HTTPStatusError as exc:
            response_text = self._sanitize_response_text(exc.response.text)
            logger.error(
                f"PaddleOCR API HTTP error: {exc.response.status_code}, response: {response_text}"
            )
            raise OCRServiceError(
                f"OCR API returned error: {exc.response.status_code}, response: {response_text}"
            ) from exc
        except OCRServiceError:
            raise
        except Exception as exc:
            logger.error(f"PaddleOCR API error: {exc}")
            raise OCRServiceError(f"OCR API error: {str(exc)}") from exc

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Return a limiter bound to the current FastAPI/Celery event loop."""
        loop = asyncio.get_running_loop()
        semaphore = self._semaphores.get(loop)
        if semaphore is None:
            semaphore = asyncio.Semaphore(self.max_concurrency)
            self._semaphores[loop] = semaphore
        return semaphore

    async def process_image(
        self,
        image_path: Path,
        visualize: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """Process a single image through OCR."""
        return await self.process_file(
            file_path=image_path,
            file_type=1,
            visualize=visualize,
            **kwargs,
        )

    async def process_pdf(
        self,
        pdf_path: Path,
        visualize: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """Process a PDF through OCR."""
        return await self.process_file(
            file_path=pdf_path,
            file_type=0,
            visualize=visualize,
            **kwargs,
        )

    async def restructure_pages(
        self,
        pages: List[Dict[str, Any]],
        merge_tables: bool = True,
        relevel_titles: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Best-effort document restructuring for independently OCRed pages.

        Args:
            pages: Ordered normalized page results.
            merge_tables: Whether to merge tables spanning pages.
            relevel_titles: Whether to normalize title levels across pages.

        Returns:
            Restructured document output, or None when restructuring fails.
        """
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                trust_env=settings.paddle_ocr_trust_env,
            ) as client:
                return await self._restructure_pages(
                    client=client,
                    pages=pages,
                    merge_tables=merge_tables,
                    relevel_titles=relevel_titles,
                )
        except httpx.HTTPError as exc:
            logger.warning("PaddleOCR document restructure skipped: %s", exc)
            return None

    async def healthcheck(self) -> Dict[str, Any]:
        """Check whether the configured PaddleOCR HTTP server is reachable."""
        base_url = self.api_url.rsplit("/", 1)[0]
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                trust_env=settings.paddle_ocr_trust_env,
            ) as client:
                response = await client.get(base_url)
            return {
                "reachable": response.status_code < 500,
                "status_code": response.status_code,
                "endpoint": self.api_url,
                "model": self.model_name,
            }
        except httpx.HTTPError as exc:
            return {
                "reachable": False,
                "endpoint": self.api_url,
                "model": self.model_name,
                "error": str(exc),
            }

    async def _post_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: Dict[str, Any],
    ) -> httpx.Response:
        """Retry transient transport and server errors without retrying bad input."""
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                if (
                    response.status_code in self.RETRYABLE_STATUS_CODES
                    and attempt < self.max_retries
                ):
                    logger.warning(
                        "Transient PaddleOCR HTTP %s; retry %s/%s",
                        response.status_code,
                        attempt + 1,
                        self.max_retries,
                    )
                    await asyncio.sleep(self.retry_backoff * (2**attempt))
                    continue
                response.raise_for_status()
                return response
            except (httpx.ConnectTimeout, httpx.ConnectError) as exc:
                if attempt >= self.max_retries:
                    raise
                logger.warning(
                    "PaddleOCR connection failed type=%s; retry %s/%s",
                    type(exc).__name__,
                    attempt + 1,
                    self.max_retries,
                )
                await asyncio.sleep(self.retry_backoff * (2**attempt))
        raise OCRServiceError("OCR retry loop exited unexpectedly")

    def _decode_json_response(self, response: httpx.Response) -> Dict[str, Any]:
        """Decode and validate the top-level JSON response."""
        try:
            payload = response.json()
        except ValueError as exc:
            raise OCRServiceError(
                "OCR API returned a non-JSON response",
                self._sanitize_response_text(response.text),
            ) from exc
        if not isinstance(payload, dict):
            raise OCRServiceError("OCR API returned a non-object JSON response")
        return payload

    def _sanitize_response_text(self, text: str, limit: int = 2000) -> str:
        """Keep upstream errors useful without flooding logs with huge responses."""
        compact = " ".join((text or "").split())
        if len(compact) <= limit:
            return compact
        return f"{compact[:limit]}... [truncated]"

    def _build_restructure_url(self, api_url: str) -> str:
        """Build restructure-pages endpoint from layout-parsing URL."""
        if api_url.endswith("/layout-parsing"):
            return f"{api_url.rsplit('/', 1)[0]}/restructure-pages"
        return f"{api_url.rstrip('/')}/restructure-pages"

    def _normalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize PaddleOCR-VL response payloads for callers."""
        api_result = result.get("result")
        if not isinstance(api_result, dict):
            raise OCRServiceError("OCR API returned invalid result payload")

        layout_results = api_result.get("layoutParsingResults")
        if not isinstance(layout_results, list) or not layout_results:
            raise OCRServiceError("OCR API returned no layout parsing results")

        normalized_pages = [self._normalize_page_result(item) for item in layout_results]
        full_markdown = "\n\n".join(
            page["markdown"] for page in normalized_pages if page.get("markdown")
        )
        return {
            "layoutParsingResults": normalized_pages,
            "dataInfo": api_result.get("dataInfo", {}),
            "fullMarkdown": full_markdown,
        }

    def _normalize_page_result(self, page_result: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a single page result from PaddleOCR-VL."""
        markdown = page_result.get("markdown")
        markdown_text = ""
        markdown_images: Optional[Dict[str, str]] = None
        if isinstance(markdown, dict):
            markdown_text = markdown.get("text", "") or ""
            raw_markdown_images = markdown.get("images")
            markdown_images = (
                raw_markdown_images
                if isinstance(raw_markdown_images, dict) and raw_markdown_images
                else None
            )

        output_images = page_result.get("outputImages") or {}
        pruned_result = page_result.get("prunedResult", {}) or {}

        return {
            "markdown": markdown_text,
            "markdownImages": markdown_images,
            "prunedResult": pruned_result,
            "outputImages": output_images,
            "inputImage": page_result.get("inputImage"),
            "rawPageResult": page_result,
            "blocks": self._extract_blocks(pruned_result, page_result),
        }

    async def _restructure_pages(
        self,
        client: httpx.AsyncClient,
        pages: List[Dict[str, Any]],
        merge_tables: bool,
        relevel_titles: bool,
    ) -> Optional[Dict[str, Any]]:
        """Call the PDF restructure endpoint when enabled."""
        restructure_payload = {
            "pages": [
                {
                    "prunedResult": page.get("prunedResult", {}),
                    "markdownImages": page.get("markdownImages", {}) or None,
                }
                for page in pages
            ],
            "concatenatePages": True,
            "mergeTables": merge_tables,
            "relevelTitles": relevel_titles,
        }

        try:
            response = await client.post(
                self.restructure_url,
                json=restructure_payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                f"PaddleOCR restructure failed: {exc.response.status_code}, response: {exc.response.text}"
            )
            return None

        result = response.json().get("result", {})
        layout_results = result.get("layoutParsingResults")
        if not isinstance(layout_results, list) or not layout_results:
            return None

        normalized_pages = [self._normalize_page_result(item) for item in layout_results]
        markdown = "\n\n".join(
            page["markdown"] for page in normalized_pages if page.get("markdown")
        )
        return {
            "layoutParsingResults": normalized_pages,
            "markdown": markdown,
        }

    def _extract_blocks(
        self,
        pruned_result: Dict[str, Any],
        page_result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Extract block-like items from Paddle results."""
        candidates: List[Any] = []
        if isinstance(pruned_result, dict):
            for key in ("parsing_res_list", "parsing_res", "blocks", "block_infos"):
                value = pruned_result.get(key)
                if value:
                    candidates.append(value)
            res_value = pruned_result.get("res")
            if isinstance(res_value, dict):
                for key in ("parsing_res_list", "parsing_res", "blocks", "block_infos"):
                    value = res_value.get(key)
                    if value:
                        candidates.append(value)

        for key in ("blocks", "parsing_res_list", "parsing_res"):
            value = page_result.get(key)
            if value:
                candidates.append(value)

        extracted: List[Dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for candidate in candidates:
            self._collect_blocks(candidate, extracted, seen)

        return extracted

    def _collect_blocks(
        self,
        value: Any,
        extracted: List[Dict[str, Any]],
        seen: set[tuple[Any, ...]],
    ) -> None:
        """Recursively collect normalized blocks from nested result structures."""
        if isinstance(value, list):
            for item in value:
                self._collect_blocks(item, extracted, seen)
            return

        if not isinstance(value, dict):
            return

        bbox = (
            value.get("bbox")
            or value.get("block_bbox")
            or value.get("poly")
            or value.get("box")
            or value.get("coordinate")
        )
        text = (
            value.get("text")
            or value.get("content")
            or value.get("block_content")
            or value.get("md")
        )
        label = (
            value.get("label")
            or value.get("type")
            or value.get("block_label")
            or "text"
        )
        confidence = value.get("confidence", value.get("score"))

        if bbox and isinstance(bbox, list):
            normalized_bbox = self._normalize_bbox(bbox)
            signature = tuple(normalized_bbox + [text or "", label or "text"])
            if signature not in seen:
                seen.add(signature)
                extracted.append(
                    {
                        "label": label,
                        "bbox": normalized_bbox,
                        "text": text or "",
                        "confidence": confidence,
                    }
                )

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
                self._collect_blocks(nested_value, extracted, seen)

    def _normalize_bbox(self, bbox: List[Any]) -> List[float]:
        """Normalize bbox arrays to [x1, y1, x2, y2]."""
        if len(bbox) == 4 and all(not isinstance(item, list) for item in bbox):
            return [float(item) for item in bbox]

        if len(bbox) == 8 and all(not isinstance(item, list) for item in bbox):
            xs = [float(bbox[i]) for i in range(0, 8, 2)]
            ys = [float(bbox[i]) for i in range(1, 8, 2)]
            return [min(xs), min(ys), max(xs), max(ys)]

        if all(isinstance(item, list) and len(item) == 2 for item in bbox):
            xs = [float(point[0]) for point in bbox]
            ys = [float(point[1]) for point in bbox]
            return [min(xs), min(ys), max(xs), max(ys)]

        return [float(item) for item in bbox[:4]]


paddle_service = PaddleOCRService()
