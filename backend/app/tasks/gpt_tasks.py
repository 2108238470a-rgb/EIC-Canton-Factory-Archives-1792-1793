"""GPT processing Celery tasks."""

import asyncio
from difflib import SequenceMatcher
import re
from typing import Any, Dict, List, Optional, Sequence

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.services.gpt_service import gpt_service
from app.services.correction_quality import assess_correction
from app.repositories import (
    TaskRepository,
    BlockRepository,
    PageRepository,
    DocumentRepository,
)
from app.models import TaskStatus, Block, Page, ReviewStatus
from app.schemas import (
    BlockUpdate,
    PageBoundaryEvidenceSchema,
    PageCorrectionBlockInputSchema,
    PageCorrectionContextBlockSchema,
    PageCorrectionRequestSchema,
    TokenUsageSchema,
)
from app.core import logger

BLOCK_NEIGHBOR_WINDOW = 1
ADJACENT_CONTEXT_BLOCKS = 3
CURRENT_PAGE_REFERENCE_LIMIT = 12
DOCUMENT_REFERENCE_LIMIT = 8

REGION_ROLE_KEYWORDS = {
    "header": ("header", "running_header", "page_header"),
    "footer": ("footer", "running_footer", "page_footer"),
    "title": ("title", "heading", "section_title"),
    "date": ("date",),
    "signature": ("signature", "signed", "seal"),
    "marginalia": ("marginal", "margin", "side_note", "annotation"),
    "page_number": ("page_number", "pagination"),
    "table": ("table",),
}
SENTENCE_END_PATTERN = re.compile(r"[.!?][\"')\]]*$")
CONTINUATION_START_PATTERN = re.compile(r"^[a-z,;:)\]]")
HEADER_TEXT_PATTERN = re.compile(r"^(?:page\s+)?(?:[ivxlcdm]+|\d+)$", re.IGNORECASE)
CAPITALIZED_TOKEN_PATTERN = re.compile(r"\b[A-Z][A-Za-z'’.-]*\b")
NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,:/-]\d+)*\b")
NEGATION_PATTERN = re.compile(
    r"\b(?:no|not|never|neither|nor|without)\b", re.IGNORECASE
)
PROTECTED_HISTORICAL_FORMS = (
    "publick",
    "shew",
    "tho'",
    "encreasing",
    "Esqr.",
    "Wm.",
    "Hon'ble",
    "Honble",
)
FACT_BEARING_TERMS = {
    "secretary",
    "committee",
    "office",
    "officer",
    "governor",
    "captain",
    "colonel",
    "major",
    "lieutenant",
    "general",
    "president",
    "chairman",
    "commissioner",
}


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _normalize_text(value: str | None) -> str | None:
    """Normalize text for prompt context."""
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    return normalized or None


def _region_role(block_label: Optional[str]) -> str:
    """Map an OCR layout label to a stable historical region role."""
    normalized = re.sub(r"[^a-z0-9]+", "_", (block_label or "").lower()).strip("_")
    for role, keywords in REGION_ROLE_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return role
    if normalized in {"text", "paragraph", "body", "content"}:
        return "body"
    return "unknown"


def _trusted_corrected_text(block: Block) -> str | None:
    """Return a correction only when it exactly matches the current raw snapshot."""
    raw = getattr(block, "ocr_text_raw", None)
    source = getattr(block, "ocr_correction_source_text", None)
    corrected = _normalize_text(getattr(block, "ocr_text_corrected", None))
    return corrected if isinstance(raw, str) and source == raw and corrected else None


def _context_block(page: Page, block: Block) -> PageCorrectionContextBlockSchema | None:
    """Create provenance-preserving structured evidence for one block."""
    raw_value = getattr(block, "ocr_text_raw", None)
    raw = raw_value if isinstance(raw_value, str) and raw_value.strip() else None
    if not raw:
        return None
    return PageCorrectionContextBlockSchema(
        page_number=page.page_number,
        block_id=block.id,
        block_index=block.block_index,
        block_label=getattr(block, "block_label", None),
        region_role=_region_role(getattr(block, "block_label", None)),
        bbox=list(getattr(block, "bbox", None) or []),
        confidence=getattr(block, "confidence", None),
        original_ocr_text=raw,
        corrected_text=_trusted_corrected_text(block),
    )


def _assess_boundary(
    left_block: Optional[Block],
    right_block: Optional[Block],
) -> PageBoundaryEvidenceSchema | None:
    """Assess page-boundary continuation without joining block text."""
    if not left_block or not right_block:
        return None
    left_text = _normalize_text(getattr(left_block, "ocr_text_raw", None))
    right_text = _normalize_text(getattr(right_block, "ocr_text_raw", None))
    if not left_text or not right_text:
        return None

    left_role = _region_role(getattr(left_block, "block_label", None))
    right_role = _region_role(getattr(right_block, "block_label", None))
    non_body_roles = {
        "header",
        "footer",
        "title",
        "date",
        "signature",
        "marginalia",
        "page_number",
    }
    if left_role in non_body_roles or right_role in non_body_roles:
        return PageBoundaryEvidenceSchema(
            assessment="unlikely_continuation",
            reasons=[f"region transition: {left_role} to {right_role}"],
        )
    if HEADER_TEXT_PATTERN.fullmatch(right_text):
        return PageBoundaryEvidenceSchema(
            assessment="unlikely_continuation",
            reasons=["right block resembles pagination or a header"],
        )
    if SENTENCE_END_PATTERN.search(left_text):
        return PageBoundaryEvidenceSchema(
            assessment="unlikely_continuation",
            reasons=["left block ends with terminal punctuation"],
        )
    if CONTINUATION_START_PATTERN.search(right_text):
        reason = (
            "hyphenated left edge"
            if left_text.endswith("-")
            else "lowercase right edge"
        )
        return PageBoundaryEvidenceSchema(
            assessment="possible_continuation",
            reasons=[reason],
        )
    return PageBoundaryEvidenceSchema(
        assessment="indeterminate",
        reasons=["layout and punctuation do not establish continuation"],
    )


def _build_block_context(
    blocks: List[Block],
    current_index: int,
    current_page: Optional[Page],
    previous_page: Optional[Page],
    previous_blocks: Sequence[Block],
    next_page: Optional[Page],
    next_blocks: Sequence[Block],
) -> str | None:
    """Build region-aware evidence for single-block correction."""
    snippets: List[str] = []
    start = max(0, current_index - BLOCK_NEIGHBOR_WINDOW)
    end = min(len(blocks), current_index + BLOCK_NEIGHBOR_WINDOW + 1)
    for idx in range(start, end):
        block = blocks[idx]
        text = _normalize_text(getattr(block, "ocr_text_raw", None))
        if text:
            marker = "TARGET" if idx == current_index else "NEIGHBOR"
            snippets.append(
                f"{marker} page={getattr(current_page, 'page_number', '?')} "
                f"region={_region_role(getattr(block, 'block_label', None))}: {text}"
            )
    if previous_page and previous_blocks:
        block = previous_blocks[-1]
        text = _normalize_text(getattr(block, "ocr_text_raw", None))
        boundary = _assess_boundary(block, blocks[0] if blocks else None)
        if text:
            snippets.append(
                f"PREVIOUS_PAGE_EVIDENCE page={previous_page.page_number} "
                f"region={_region_role(getattr(block, 'block_label', None))} "
                f"boundary={boundary.model_dump() if boundary else None}: {text}"
            )
    if next_page and next_blocks:
        block = next_blocks[0]
        text = _normalize_text(getattr(block, "ocr_text_raw", None))
        boundary = _assess_boundary(blocks[-1] if blocks else None, block)
        if text:
            snippets.append(
                f"NEXT_PAGE_EVIDENCE page={next_page.page_number} "
                f"region={_region_role(getattr(block, 'block_label', None))} "
                f"boundary={boundary.model_dump() if boundary else None}: {text}"
            )
    return "\n".join(snippets) or None


def _bounded_context(
    page: Optional[Page],
    blocks: Sequence[Block],
    *,
    from_end: bool,
) -> List[PageCorrectionContextBlockSchema]:
    """Build a bounded ordered context without concatenating block text."""
    if not page:
        return []
    selected = (
        blocks[-ADJACENT_CONTEXT_BLOCKS:]
        if from_end
        else blocks[:ADJACENT_CONTEXT_BLOCKS]
    )
    return [
        context
        for block in selected
        if (context := _context_block(page, block)) is not None
    ]


def _document_references(
    page: Page,
    document_blocks: Sequence[Block],
    target_blocks: Sequence[Block],
) -> List[PageCorrectionContextBlockSchema]:
    """Select bounded, source-traceable document evidence related to targets."""
    target_terms = {
        term.lower()
        for block in target_blocks
        for term in re.findall(r"[A-Za-z]{4,}", block.ocr_text_raw or "")
    }
    scored: List[tuple[int, float, PageCorrectionContextBlockSchema]] = []
    for block in document_blocks:
        block_page = getattr(block, "page", None)
        if not block_page or block_page.id == page.id:
            continue
        context = _context_block(block_page, block)
        if not context:
            continue
        terms = set(re.findall(r"[a-z]{4,}", context.original_ocr_text.lower()))
        overlap = len(target_terms & terms)
        trusted = 1 if context.corrected_text else 0
        confidence = context.confidence or 0.0
        if overlap:
            scored.append((overlap + trusted, confidence, context))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in scored[:DOCUMENT_REFERENCE_LIMIT]]


def _build_page_request(
    page: Page,
    all_blocks: Sequence[Block],
    eligible_blocks: Sequence[Block],
    previous_page: Optional[Page],
    previous_blocks: Sequence[Block],
    next_page: Optional[Page],
    next_blocks: Sequence[Block],
    document_blocks: Sequence[Block],
) -> PageCorrectionRequestSchema:
    """Build a region-aware page request with explicit boundary evidence."""
    eligible_ids = {block.id for block in eligible_blocks}
    current_references = [
        context
        for block in all_blocks
        if block.id not in eligible_ids
        and (context := _context_block(page, block)) is not None
    ][:CURRENT_PAGE_REFERENCE_LIMIT]
    return PageCorrectionRequestSchema(
        page_number=page.page_number,
        previous_page_context=_bounded_context(
            previous_page, previous_blocks, from_end=True
        ),
        previous_boundary=_assess_boundary(
            previous_blocks[-1] if previous_blocks else None,
            all_blocks[0] if all_blocks else None,
        ),
        blocks=[
            PageCorrectionBlockInputSchema(
                block_id=block.id,
                block_index=block.block_index,
                block_label=getattr(block, "block_label", None),
                region_role=_region_role(getattr(block, "block_label", None)),
                bbox=list(getattr(block, "bbox", None) or []),
                ocr_text_raw=block.ocr_text_raw,
            )
            for block in eligible_blocks
        ],
        current_page_reference_blocks=current_references,
        document_reference_blocks=_document_references(
            page, document_blocks, eligible_blocks
        ),
        next_page_context=_bounded_context(next_page, next_blocks, from_end=False),
        next_boundary=_assess_boundary(
            all_blocks[-1] if all_blocks else None,
            next_blocks[0] if next_blocks else None,
        ),
    )


def _token_set(pattern: re.Pattern[str], text: str) -> set[str]:
    """Return normalized tokens matched by a compiled pattern."""
    return {match.group(0).lower() for match in pattern.finditer(text)}


def _has_source_neighbor(token: str, source_tokens: set[str]) -> bool:
    """Check whether a candidate token is a plausible correction of source text."""
    return any(
        SequenceMatcher(None, token, source).ratio() >= 0.72 for source in source_tokens
    )


def _select_correction_candidate(raw: str, candidate: str) -> str:
    """Choose the LLM candidate only when it preserves protected evidence."""
    return assess_correction(raw, candidate)["text"]


def _usage_dict(usage: TokenUsageSchema) -> Dict[str, int]:
    """Serialize token usage for task results."""
    return usage.model_dump()


def _add_usage(total: TokenUsageSchema, item: TokenUsageSchema) -> None:
    """Accumulate normalized token usage."""
    total.prompt_tokens += item.prompt_tokens
    total.completion_tokens += item.completion_tokens
    total.total_tokens += item.total_tokens
    total.calls += item.calls
    total.calls_with_usage += item.calls_with_usage


def _process_correction_page(
    block_repo: BlockRepository,
    page: Page,
    previous_page: Optional[Page],
    next_page: Optional[Page],
) -> Dict[str, Any]:
    """Correct one eligible page in one GPT call and one atomic write."""
    all_blocks = block_repo.get_by_page(page.id)
    eligible_blocks = [
        block
        for block in block_repo.get_unprocessed_by_page(page.id)
        if _normalize_text(block.ocr_text_raw)
    ]
    skipped_blocks = len(all_blocks) - len(eligible_blocks)
    if not eligible_blocks:
        return {
            "page_id": page.id,
            "page_number": page.page_number,
            "processed": 0,
            "skipped": skipped_blocks,
            "total": len(all_blocks),
            "page_skipped": True,
            "llm_calls": 0,
            "token_usage": _usage_dict(TokenUsageSchema()),
        }

    previous_blocks = block_repo.get_by_page(previous_page.id) if previous_page else []
    next_blocks = block_repo.get_by_page(next_page.id) if next_page else []
    document_blocks = block_repo.get_by_document(page.document_id)
    request = _build_page_request(
        page,
        all_blocks,
        eligible_blocks,
        previous_page,
        previous_blocks,
        next_page,
        next_blocks,
        document_blocks,
    )
    call_result = run_async(gpt_service.correct_ocr_page(request))
    source_by_id = {block.id: block.ocr_text_raw for block in eligible_blocks}
    reports = getattr(call_result, "quality_reports", {}) or {
        item.block_id: assess_correction(
            source_by_id[item.block_id], item.ocr_text_corrected
        )
        for item in call_result.blocks
    }
    corrections = {
        item.block_id: item.ocr_text_corrected
        for item in call_result.blocks
        if reports[item.block_id]["accepted"]
    }
    source_snapshots = {
        block.id: block.ocr_text_raw
        for block in eligible_blocks
        if block.id in corrections
    }
    if corrections:
        block_repo.update_page_corrections(page.id, corrections, source_snapshots)
    return {
        "page_id": page.id,
        "page_number": page.page_number,
        "processed": len(corrections),
        "skipped": skipped_blocks,
        "total": len(all_blocks),
        "page_skipped": False,
        "llm_calls": call_result.token_usage.calls,
        "block_ids": list(corrections),
        "quality_reports": reports,
        "held_for_review": sum(not r["accepted"] for r in reports.values()),
        "token_usage": _usage_dict(call_result.token_usage),
    }


@celery_app.task(bind=True, name="tasks.polish_block")
def polish_block_task(
    self,
    task_id: int,
    block_id: int,
    modes: List[str],
) -> dict:
    """
    Celery task for GPT processing a single block.

    Args:
        task_id: Database task ID
        block_id: Block ID to process
        modes: List of processing modes

    Returns:
        Task result dict
    """
    db = SessionLocal()
    task_repo = TaskRepository(db)
    block_repo = BlockRepository(db)
    page_repo = PageRepository(db)
    doc_repo = DocumentRepository(db)

    try:
        task_repo.update_status(
            task_id, TaskStatus.RUNNING, progress=0, result={"stage": "preparing_block"}
        )

        block = block_repo.get_by_id(block_id)
        if not block or not block.ocr_text_raw:
            raise ValueError(f"Block {block_id} not found or has no OCR text")

        if block.review_status == ReviewStatus.APPROVED:
            raise ValueError("人工已复核文本不执行自动润色；如需修改，请使用人工校订")
        source_snapshot = block.ocr_text_raw
        page = page_repo.get_by_id(block.page_id)
        document = doc_repo.get_by_id(page.document_id) if page else None
        page_blocks = block_repo.get_by_page(block.page_id) if page else []
        current_index = next(
            (idx for idx, item in enumerate(page_blocks) if item.id == block_id), 0
        )
        previous_page = (
            page_repo.get_by_document_and_number(page.document_id, page.page_number - 1)
            if page and page.page_number > 1
            else None
        )
        next_page = (
            page_repo.get_by_document_and_number(page.document_id, page.page_number + 1)
            if page
            else None
        )
        previous_blocks = (
            block_repo.get_by_page(previous_page.id) if previous_page else []
        )
        next_blocks = block_repo.get_by_page(next_page.id) if next_page else []
        context = _build_block_context(
            page_blocks,
            current_index,
            page,
            previous_page,
            previous_blocks,
            next_page,
            next_blocks,
        )

        task_repo.update_status(
            task_id,
            TaskStatus.RUNNING,
            progress=35,
            result={
                "stage": "processing_block",
                "page_number": getattr(page, "page_number", None),
                "block_index": block.block_index + 1,
            },
        )
        processing_result = run_async(
            gpt_service.process_block_with_usage(block.ocr_text_raw, modes, context)
        )
        results = processing_result.results
        if "ocr_text_corrected" in results:
            results["ocr_text_corrected"] = _select_correction_candidate(
                block.ocr_text_raw,
                results["ocr_text_corrected"],
            )

        quality_report = getattr(processing_result, "quality_report", {})
        if quality_report and not quality_report["accepted"]:
            results.pop("ocr_text_corrected", None)
        update_data = BlockUpdate(**results)
        block_repo.update_generated(block_id, update_data, source_snapshot)

        result = {
            "stage": "completed",
            "scope": "block",
            "page_number": getattr(page, "page_number", None),
            "block_index": block.block_index + 1,
            "token_usage": _usage_dict(processing_result.token_usage),
            **results,
            "quality_report": quality_report,
        }
        task_repo.update_status(
            task_id, TaskStatus.COMPLETED, progress=100, result=result
        )

        logger.info(f"Polish task completed for block {block_id}")
        return {"block_id": block_id, **result}

    except Exception as e:
        logger.error(f"Polish task failed for block {block_id}: {e}")
        task_repo.update_status(
            task_id,
            TaskStatus.FAILED,
            error_message=str(e),
            result={"stage": "failed", "scope": "block"},
        )
        raise

    finally:
        db.close()


@celery_app.task(bind=True, name="tasks.polish_page")
def polish_page_task(
    self,
    task_id: int,
    page_id: int,
    modes: List[str],
) -> dict:
    """
    Celery task for GPT processing all blocks in a page.

    Args:
        task_id: Database task ID
        page_id: Page ID to process
        modes: List of processing modes

    Returns:
        Task result dict
    """
    db = SessionLocal()
    task_repo = TaskRepository(db)
    block_repo = BlockRepository(db)
    page_repo = PageRepository(db)

    try:
        task_repo.update_status(
            task_id,
            TaskStatus.RUNNING,
            progress=0,
            result={"stage": "preparing_page", "scope": "page"},
        )
        if modes != ["ocr_correction"]:
            raise ValueError("Page polish supports only ocr_correction mode")
        page = page_repo.get_by_id(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")
        previous_page = (
            page_repo.get_by_document_and_number(page.document_id, page.page_number - 1)
            if page.page_number > 1
            else None
        )
        next_page = page_repo.get_by_document_and_number(
            page.document_id, page.page_number + 1
        )
        page_result = _process_correction_page(
            block_repo, page, previous_page, next_page
        )
        result = {
            "stage": "completed",
            "scope": "page",
            **page_result,
        }
        task_repo.update_status(
            task_id, TaskStatus.COMPLETED, progress=100, result=result
        )

        logger.info(
            f"Polish task completed for page {page_id}: "
            f"{page_result['processed']} blocks"
        )
        return result

    except Exception as e:
        logger.error(f"Polish task failed for page {page_id}: {e}")
        task_repo.update_status(
            task_id,
            TaskStatus.FAILED,
            error_message=str(e),
            result={"stage": "failed", "scope": "page"},
        )
        raise

    finally:
        db.close()


@celery_app.task(bind=True, name="tasks.polish_document")
def polish_document_task(
    self,
    task_id: int,
    document_id: int,
    modes: List[str],
) -> dict:
    """
    Celery task for GPT processing all blocks in a document.

    Args:
        task_id: Database task ID
        document_id: Document ID to process
        modes: List of processing modes

    Returns:
        Task result dict
    """
    db = SessionLocal()
    task_repo = TaskRepository(db)
    block_repo = BlockRepository(db)
    page_repo = PageRepository(db)
    doc_repo = DocumentRepository(db)

    usage = TokenUsageSchema()
    page_results: List[Dict[str, Any]] = []
    failed_pages: List[tuple[int, Page]] = []
    current_page_number: Optional[int] = None
    total_processed = 0
    total_skipped = 0

    try:
        task_repo.update_status(
            task_id,
            TaskStatus.RUNNING,
            progress=0,
            result={"stage": "preparing_document", "scope": "document"},
        )
        if modes != ["ocr_correction"]:
            raise ValueError("Document polish supports only ocr_correction mode")
        document = doc_repo.get_by_id(document_id)
        if not document:
            raise ValueError(f"Document {document_id} not found")
        pages = page_repo.get_by_document(document_id)
        total_pages = len(pages)

        # First pass: process all pages with per-page error isolation
        for page_position, page in enumerate(pages, start=1):
            current_page_number = page.page_number
            previous_page = pages[page_position - 2] if page_position > 1 else None
            next_page = pages[page_position] if page_position < total_pages else None

            try:
                page_result = _process_correction_page(
                    block_repo, page, previous_page, next_page
                )
                page_results.append(page_result)
                total_processed += int(page_result["processed"])
                total_skipped += int(page_result["skipped"])
                _add_usage(
                    usage,
                    TokenUsageSchema.model_validate(page_result["token_usage"]),
                )
            except Exception as page_exc:
                logger.warning(
                    "Page %s correction failed in first pass, will retry in second pass: %s",
                    current_page_number,
                    page_exc,
                )
                failed_pages.append((page_position, page))
                page_results.append(
                    {
                        "page_id": page.id,
                        "page_number": page.page_number,
                        "processed": 0,
                        "skipped": 0,
                        "total": 0,
                        "page_skipped": True,
                        "page_failed": True,
                        "error": str(page_exc),
                        "llm_calls": 0,
                        "token_usage": _usage_dict(TokenUsageSchema()),
                    }
                )

            processed_pages = sum(not item["page_skipped"] for item in page_results)
            skipped_pages = sum(
                item.get("page_skipped", False) and not item.get("page_failed", False)
                for item in page_results
            )
            failed_count = sum(item.get("page_failed", False) for item in page_results)
            task_repo.update_status(
                task_id,
                TaskStatus.RUNNING,
                progress=int((page_position / total_pages) * 85) if total_pages else 85,
                result={
                    "stage": "processing_document_first_pass",
                    "scope": "document",
                    "page_number": current_page_number,
                    "page_count": total_pages,
                    "pages_completed": page_position,
                    "processed_pages": processed_pages,
                    "skipped_pages": skipped_pages,
                    "failed_pages": failed_count,
                    "processed": total_processed,
                    "skipped": total_skipped,
                    "llm_calls": usage.calls,
                    "token_usage": _usage_dict(usage),
                },
            )

        # Second pass: retry failed pages
        if failed_pages:
            logger.info(
                "Starting second-pass retry for %s failed pages: %s",
                len(failed_pages),
                [page.page_number for _, page in failed_pages],
            )
            retry_success = 0
            for retry_idx, (page_position, page) in enumerate(failed_pages, start=1):
                current_page_number = page.page_number
                previous_page = pages[page_position - 2] if page_position > 1 else None
                next_page = (
                    pages[page_position] if page_position < total_pages else None
                )

                try:
                    page_result = _process_correction_page(
                        block_repo, page, previous_page, next_page
                    )
                    # Replace the failed placeholder with the real result
                    result_idx = page_position - 1
                    page_results[result_idx] = page_result
                    total_processed += int(page_result["processed"])
                    total_skipped += int(page_result["skipped"])
                    _add_usage(
                        usage,
                        TokenUsageSchema.model_validate(page_result["token_usage"]),
                    )
                    retry_success += 1
                    logger.info(
                        "Page %s correction succeeded in second pass (%s/%s retries)",
                        current_page_number,
                        retry_idx,
                        len(failed_pages),
                    )
                except Exception as retry_exc:
                    logger.error(
                        "Page %s correction failed again in second pass (%s/%s): %s",
                        current_page_number,
                        retry_idx,
                        len(failed_pages),
                        retry_exc,
                    )

                progress = 85 + int((retry_idx / len(failed_pages)) * 13)
                task_repo.update_status(
                    task_id,
                    TaskStatus.RUNNING,
                    progress=progress,
                    result={
                        "stage": "processing_document_second_pass",
                        "scope": "document",
                        "page_number": current_page_number,
                        "retry_progress": f"{retry_idx}/{len(failed_pages)}",
                        "retry_success": retry_success,
                    },
                )

        # Final status: FAILED if any pages still failed after second pass, otherwise COMPLETED
        final_failed_pages = [
            item for item in page_results if item.get("page_failed", False)
        ]
        final_status = TaskStatus.FAILED if final_failed_pages else TaskStatus.COMPLETED
        final_stage = (
            "completed" if not final_failed_pages else "completed_with_failures"
        )

        result = {
            "stage": final_stage,
            "scope": "document",
            "page_count": total_pages,
            "pages_completed": len(page_results),
            "processed_pages": sum(
                not item.get("page_skipped", False) or item.get("page_failed", False)
                for item in page_results
            ),
            "skipped_pages": sum(
                item.get("page_skipped", False) and not item.get("page_failed", False)
                for item in page_results
            ),
            "failed_pages": len(final_failed_pages),
            "failed_page_numbers": [item["page_number"] for item in final_failed_pages],
            "processed": total_processed,
            "skipped": total_skipped,
            "llm_calls": usage.calls,
            "token_usage": _usage_dict(usage),
            "pages": page_results,
        }

        error_message = None
        if final_failed_pages:
            error_message = (
                f"{len(final_failed_pages)} pages failed after retry: "
                f"{[item['page_number'] for item in final_failed_pages]}"
            )
            logger.warning(
                "Polish task completed with failures for document %s: %s",
                document_id,
                error_message,
            )
        else:
            logger.info(
                "Polish task completed successfully for document %s: %s blocks",
                document_id,
                total_processed,
            )

        task_repo.update_status(
            task_id,
            final_status,
            progress=100,
            error_message=error_message,
            result=result,
        )
        return {"document_id": document_id, **result}

    except Exception as e:
        # Fatal non-page-specific error (e.g., document not found, invalid modes)
        logger.error(f"Polish task failed fatally for document {document_id}: {e}")
        failure_result = {
            "stage": "fatal_error",
            "scope": "document",
            "fatal_error": str(e),
            "pages_completed": len(page_results),
            "processed_pages": sum(
                not item.get("page_skipped", False) for item in page_results
            ),
            "skipped_pages": sum(
                item.get("page_skipped", False) and not item.get("page_failed", False)
                for item in page_results
            ),
            "failed_pages": sum(
                item.get("page_failed", False) for item in page_results
            ),
            "processed": total_processed,
            "skipped": total_skipped,
            "llm_calls": usage.calls,
            "token_usage": _usage_dict(usage),
            "pages": page_results,
        }
        task_repo.update_status(
            task_id,
            TaskStatus.FAILED,
            error_message=str(e),
            result=failure_result,
        )
        raise

    finally:
        db.close()
