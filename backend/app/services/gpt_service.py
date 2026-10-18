"""GPT service for text processing."""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from httpx import Timeout
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
)
from pydantic import ValidationError

from app.config import settings
from app.services.correction_quality import FAITHFUL_PROMPT, assess_correction
from app.core import logger, GPTServiceError
from app.schemas import (
    GPTBlockProcessingResultSchema,
    GPTCompletionResultSchema,
    PageCorrectionCallResultSchema,
    PageCorrectionRequestSchema,
    PageCorrectionResponseSchema,
    TokenUsageSchema,
)


JSON_FENCE_PATTERN = re.compile(r"\A```(?:json)?\s*\n(?P<body>.*)\n```\Z", re.DOTALL)
DEFAULT_MAX_TOKENS = 4096
PAGE_CORRECTION_RESPONSE_FORMAT: Dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "page_correction_response",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "blocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "block_id": {"type": "integer"},
                            "ocr_text_corrected": {"type": "string", "minLength": 1},
                        },
                        "required": ["block_id", "ocr_text_corrected"],
                    },
                }
            },
            "required": ["blocks"],
        },
    },
}


class GPTService:
    """Service for GPT-based text processing."""

    def __init__(self):
        self.prompts_dir = Path(__file__).parent.parent / "prompts"

    def _create_client(self) -> AsyncOpenAI:
        """Create OpenAI-compatible client from current settings."""
        api_key = settings.gpt_api_key.strip()
        if not api_key:
            raise GPTServiceError(
                "GPT API key is not configured. Please set GPT_API_KEY in your backend .env before running polish tasks."
            )

        return AsyncOpenAI(
            api_key=api_key,
            base_url=settings.gpt_base_url,
            timeout=Timeout(
                connect=30.0,
                read=float(settings.gpt_timeout),
                write=30.0,
                pool=30.0,
            ),
            max_retries=0,
        )

    @property
    def model(self) -> str:
        """Return currently configured model name."""
        return settings.gpt_model

    def _load_prompt(self, prompt_name: str) -> str:
        """Load prompt template from file."""
        prompt_path = self.prompts_dir / f"{prompt_name}.txt"
        if not prompt_path.exists():
            raise GPTServiceError(f"Prompt template not found: {prompt_name}")
        return prompt_path.read_text(encoding="utf-8")

    @staticmethod
    def _normalize_usage(usage: object) -> TokenUsageSchema:
        """Normalize optional provider token usage."""
        if usage is None:
            return TokenUsageSchema(calls=1)
        return TokenUsageSchema(
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
            calls=1,
            calls_with_usage=1,
        )

    async def _request_completion(
        self,
        system_prompt: str,
        user_message: str,
        mode: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        response_format: Optional[Dict[str, Any]] = None,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> GPTCompletionResultSchema:
        """Request one completion with fresh-connection retries."""
        request_options: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.0,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            request_options["response_format"] = response_format
        if extra_body is not None:
            request_options["extra_body"] = extra_body

        max_retries = max(0, settings.gpt_max_retries)
        for attempt in range(max_retries + 1):
            try:
                async with self._create_client() as client:
                    response = await client.chat.completions.create(**request_options)
                result = response.choices[0].message.content
                if not result or not result.strip():
                    raise GPTServiceError("GPT returned an empty response")
                usage = self._normalize_usage(response.usage)
                logger.info(
                    "GPT usage model=%s mode=%s prompt_tokens=%s completion_tokens=%s total_tokens=%s",
                    self.model,
                    mode,
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    usage.total_tokens,
                )
                return GPTCompletionResultSchema(text=result.strip(), token_usage=usage)
            except GPTServiceError:
                raise
            except AuthenticationError as exc:
                logger.error(
                    "GPT authentication error model=%s mode=%s", self.model, mode
                )
                raise GPTServiceError(
                    "GPT authentication failed. Please verify GPT_API_KEY and "
                    "GPT_BASE_URL for your OpenAI-compatible provider."
                ) from exc
            except APIConnectionError as exc:
                if attempt < max_retries:
                    delay = max(0.0, settings.gpt_retry_backoff_seconds) * (2**attempt)
                    logger.warning(
                        "Transient GPT connection error model=%s mode=%s retry=%s/%s delay=%.1fs error=%s",
                        self.model,
                        mode,
                        attempt + 1,
                        max_retries,
                        delay,
                        str(exc)[:200],
                    )
                    await asyncio.sleep(delay)
                    continue
                error_kind = (
                    "timed out"
                    if isinstance(exc, APITimeoutError)
                    else "connection failed"
                )
                logger.error(
                    "GPT request %s model=%s mode=%s attempts=%s read_timeout=%ss error=%s",
                    error_kind,
                    self.model,
                    mode,
                    max_retries + 1,
                    settings.gpt_timeout,
                    str(exc)[:200],
                )
                raise GPTServiceError(
                    f"GPT request {error_kind} after {max_retries + 1} attempts. "
                    f"Error: {str(exc)[:100]}"
                ) from exc
            except APIStatusError as exc:
                retryable = exc.status_code == 429 or exc.status_code >= 500
                if retryable and attempt < max_retries:
                    delay = max(0.0, settings.gpt_retry_backoff_seconds) * (2**attempt)
                    logger.warning(
                        "Transient GPT HTTP error model=%s mode=%s status=%s retry=%s/%s delay=%.1fs",
                        self.model,
                        mode,
                        exc.status_code,
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.error(
                    "GPT HTTP error model=%s mode=%s status=%s response=%s",
                    self.model,
                    mode,
                    exc.status_code,
                    str(exc.response.text if hasattr(exc, "response") else "")[:200],
                )
                raise GPTServiceError(
                    f"GPT provider returned HTTP {exc.status_code}. "
                    f"Response: {str(exc.response.text if hasattr(exc, 'response') else '')[:100]}"
                ) from exc
            except Exception as exc:
                logger.error(
                    "GPT API error model=%s mode=%s error_type=%s: %s",
                    self.model,
                    mode,
                    type(exc).__name__,
                    exc,
                )
                raise GPTServiceError(str(exc)) from exc

    async def process_text_with_usage(
        self,
        text: str,
        mode: str,
        context: Optional[str] = None,
    ) -> GPTCompletionResultSchema:
        """Process text and return normalized token usage."""
        if not text or not text.strip():
            return GPTCompletionResultSchema(text="", token_usage=TokenUsageSchema())

        try:
            system_prompt = self._load_prompt(mode)
        except GPTServiceError:
            system_prompt = self._get_default_prompt(mode)

        user_message = text
        if context:
            user_message = (
                "Use the context only as secondary documentary evidence. "
                "Do not copy, continue, or substitute context text into the target passage."
                f"\n\nContext:\n{context}\n\nText to process:\n{text}"
            )
        if mode == "ocr_correction":
            system_prompt = FAITHFUL_PROMPT
        result = await self._request_completion(system_prompt, user_message, mode)
        logger.debug("GPT %s completed for text length %s", mode, len(text))
        return result

    async def process_text(
        self,
        text: str,
        mode: str,
        context: Optional[str] = None,
    ) -> str:
        """Process text while preserving the legacy text-only return value."""
        result = await self.process_text_with_usage(text, mode, context)
        return (
            assess_correction(text, result.text)["text"]
            if mode == "ocr_correction"
            else result.text
        )

    async def correct_ocr(self, text: str, context: Optional[str] = None) -> str:
        """Correct OCR errors in text."""
        return await self.process_text(text, "ocr_correction", context)

    async def modernize_english(self, text: str, context: Optional[str] = None) -> str:
        """Rewrite text in modern English."""
        return await self.process_text(text, "modern_english", context)

    async def translate_to_chinese(
        self, text: str, context: Optional[str] = None
    ) -> str:
        """Translate text to Chinese."""
        return await self.process_text(text, "translation_zh", context)

    @staticmethod
    def _add_usage(total: TokenUsageSchema, item: TokenUsageSchema) -> None:
        """Add one normalized usage record to an aggregate."""
        total.prompt_tokens += item.prompt_tokens
        total.completion_tokens += item.completion_tokens
        total.total_tokens += item.total_tokens
        total.calls += item.calls
        total.calls_with_usage += item.calls_with_usage

    async def process_block_with_usage(
        self,
        text: str,
        modes: List[str],
        context: Optional[str] = None,
    ) -> GPTBlockProcessingResultSchema:
        """Process one block and aggregate usage across requested modes."""
        results: Dict[str, str] = {}
        usage = TokenUsageSchema()
        current_text = text
        quality_report = {}

        if "ocr_correction" in modes:
            completion = await self.process_text_with_usage(
                current_text, "ocr_correction", context
            )
            quality_report = assess_correction(current_text, completion.text)
            results["ocr_text_corrected"] = quality_report["text"]
            current_text = quality_report["text"]
            self._add_usage(usage, completion.token_usage)

        if "modern_english" in modes:
            completion = await self.process_text_with_usage(
                current_text, "modern_english", context
            )
            results["modern_english"] = completion.text
            self._add_usage(usage, completion.token_usage)

        if "translation_zh" in modes:
            source_text = (
                results.get("modern_english")
                or results.get("ocr_text_corrected")
                or text
            )
            completion = await self.process_text_with_usage(
                source_text, "translation_zh", context
            )
            results["translation_zh"] = completion.text
            self._add_usage(usage, completion.token_usage)

        return GPTBlockProcessingResultSchema(
            results=results, token_usage=usage, quality_report=quality_report
        )

    async def process_block(
        self,
        text: str,
        modes: List[str],
        context: Optional[str] = None,
    ) -> dict:
        """Process one block while preserving the legacy result shape."""
        result = await self.process_block_with_usage(text, modes, context)
        return result.results

    @staticmethod
    def _parse_page_response(
        content: str,
        requested_ids: Set[int],
    ) -> PageCorrectionResponseSchema:
        """Parse and validate a complete page correction response."""
        normalized = content.lstrip("﻿").strip()
        fence_match = JSON_FENCE_PATTERN.fullmatch(normalized)
        if fence_match:
            normalized = fence_match.group("body").strip()
        try:
            payload = json.loads(normalized)
            response = PageCorrectionResponseSchema.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise GPTServiceError(
                f"Invalid page correction JSON response: {exc}"
            ) from exc

        output_ids = [item.block_id for item in response.blocks]
        if len(output_ids) != len(set(output_ids)):
            raise GPTServiceError(
                "Page correction response contains duplicate block IDs"
            )
        output_id_set = set(output_ids)
        missing_ids = requested_ids - output_id_set
        unknown_ids = output_id_set - requested_ids
        if missing_ids or unknown_ids:
            raise GPTServiceError(
                "Page correction response block IDs do not match the request "
                f"(missing={sorted(missing_ids)}, unknown={sorted(unknown_ids)})"
            )
        if any(not item.ocr_text_corrected.strip() for item in response.blocks):
            raise GPTServiceError("Page correction response contains blank text")
        return response

    async def correct_ocr_page(
        self,
        request: PageCorrectionRequestSchema,
    ) -> PageCorrectionCallResultSchema:
        """Correct a page with bounded output batches; validate all targets before return."""
        requested_ids = {item.block_id for item in request.blocks}
        if len(requested_ids) != len(request.blocks):
            raise GPTServiceError(
                "Page correction request contains duplicate block IDs"
            )
        if (
            len(request.blocks) > 1
            and sum(len(b.ocr_text_raw) for b in request.blocks) > 3500
        ):
            batches = []
            batch = []
            size = 0
            for block in request.blocks:
                if batch and size + len(block.ocr_text_raw) > 3500:
                    batches.append(batch)
                    batch = []
                    size = 0
                batch.append(block)
                size += len(block.ocr_text_raw)
            if batch:
                batches.append(batch)
            outputs = []
            reports = {}
            usage = TokenUsageSchema()
            for batch in batches:
                result = await self.correct_ocr_page(
                    request.model_copy(update={"blocks": batch})
                )
                outputs.extend(result.blocks)
                reports.update(result.quality_reports)
                self._add_usage(usage, result.token_usage)
            return PageCorrectionCallResultSchema(
                blocks=outputs, quality_reports=reports, token_usage=usage
            )
        try:
            system_prompt = self._load_prompt("ocr_correction_page")
        except GPTServiceError:
            system_prompt = self._get_default_prompt("ocr_correction_page")
        system_prompt = FAITHFUL_PROMPT
        user_message = json.dumps(
            request.model_dump(), ensure_ascii=False, separators=(",", ":")
        )
        response_format = (
            {"type": "json_object"} if settings.gpt_structured_output else None
        )
        completion = await self._request_completion(
            system_prompt,
            user_message,
            "ocr_correction_page",
            max_tokens=settings.gpt_page_max_tokens,
            response_format=response_format,
            extra_body={
                "enable_thinking": settings.gpt_page_enable_thinking,
            },
        )
        response = self._parse_page_response(completion.text, requested_ids)
        output_by_id = {item.block_id: item for item in response.blocks}
        reports = {
            item.block_id: assess_correction(
                item.ocr_text_raw, output_by_id[item.block_id].ocr_text_corrected
            )
            for item in request.blocks
        }
        ordered = [
            output_by_id[item.block_id].model_copy(
                update={"ocr_text_corrected": reports[item.block_id]["text"]}
            )
            for item in request.blocks
        ]
        return PageCorrectionCallResultSchema(
            quality_reports=reports,
            blocks=ordered,
            token_usage=completion.token_usage,
        )

    def _get_default_prompt(self, mode: str) -> str:
        """Get default prompt for a mode.

        Production deployments should provide custom prompts via the prompts/
        directory. These fallback prompts are generic placeholders.
        """
        if mode in {"ocr_correction", "ocr_correction_page"}:
            return FAITHFUL_PROMPT
        prompts = {
            "ocr_correction": """You are an OCR correction assistant. Correct recognition errors in the provided text while preserving the original meaning and style. Return only the corrected text without explanations.""",
            "ocr_correction_page": """You are an OCR correction assistant. Correct recognition errors in the provided text blocks while preserving the original meaning and style. Return JSON only as {"blocks":[{"block_id":1,"ocr_text_corrected":"..."}]}. Return every requested block exactly once, in input order, without extra fields or explanations.""",
            "modern_english": """You are a text modernization assistant. Rewrite the provided historical text in modern English while preserving the original meaning. Return only the modernized text without explanations.""",
            "translation_zh": """You are a translation assistant. Translate the provided text into natural, readable Chinese. Return only the Chinese translation without explanations.""",
        }

        return prompts.get(mode, prompts["ocr_correction"])

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        mode: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        response_format: Optional[Dict[str, Any]] = None,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> GPTCompletionResultSchema:
        """Run one chat completion with the shared retry policy.

        Args:
            system_prompt: System instructions.
            user_message: User content.
            mode: Label used in usage logs.
            max_tokens: Completion token limit.

        Returns:
            Completion text and token usage.
        """
        return await self._request_completion(
            system_prompt,
            user_message,
            mode,
            max_tokens=max_tokens,
            response_format=response_format,
            extra_body=extra_body,
        )


# Singleton instance
gpt_service = GPTService()
