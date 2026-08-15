"""Schemas for structured GPT processing."""
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


HistoricalRegionRole = Literal[
    "body", "header", "footer", "title", "date", "signature",
    "marginalia", "page_number", "table", "unknown",
]
BoundaryAssessment = Literal[
    "possible_continuation", "unlikely_continuation", "indeterminate",
]


class TokenUsageSchema(BaseModel):
    """Token usage returned by an LLM provider."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    calls_with_usage: int = 0


class GPTCompletionResultSchema(BaseModel):
    """Text completion with normalized token usage."""

    text: str
    token_usage: TokenUsageSchema


class GPTBlockProcessingResultSchema(BaseModel):
    """Processed block fields with aggregate token usage."""

    results: Dict[str, str]
    token_usage: TokenUsageSchema


class PageCorrectionBlockInputSchema(BaseModel):
    """One OCR block submitted for page-level correction."""

    model_config = ConfigDict(extra="forbid")

    block_id: int
    block_index: int
    block_label: Optional[str] = None
    region_role: HistoricalRegionRole = "unknown"
    bbox: List[float] = Field(default_factory=list)
    ocr_text_raw: str = Field(min_length=1)


class PageCorrectionContextBlockSchema(BaseModel):
    """A non-target documentary evidence block."""

    model_config = ConfigDict(extra="forbid")

    page_number: int
    block_id: int
    block_index: int
    block_label: Optional[str] = None
    region_role: HistoricalRegionRole = "unknown"
    bbox: List[float] = Field(default_factory=list)
    confidence: Optional[float] = None
    original_ocr_text: str = Field(min_length=1)
    corrected_text: Optional[str] = None


class PageBoundaryEvidenceSchema(BaseModel):
    """Evidence-based assessment of one page boundary."""

    model_config = ConfigDict(extra="forbid")

    assessment: BoundaryAssessment
    reasons: List[str] = Field(default_factory=list)


class PageCorrectionRequestSchema(BaseModel):
    """One page of targets and bounded documentary context."""

    model_config = ConfigDict(extra="forbid")

    page_number: int
    previous_page_context: List[PageCorrectionContextBlockSchema] = Field(
        default_factory=list
    )
    previous_boundary: Optional[PageBoundaryEvidenceSchema] = None
    blocks: List[PageCorrectionBlockInputSchema] = Field(min_length=1)
    current_page_reference_blocks: List[PageCorrectionContextBlockSchema] = Field(
        default_factory=list
    )
    document_reference_blocks: List[PageCorrectionContextBlockSchema] = Field(
        default_factory=list
    )
    next_page_context: List[PageCorrectionContextBlockSchema] = Field(
        default_factory=list
    )
    next_boundary: Optional[PageBoundaryEvidenceSchema] = None


class PageCorrectionBlockOutputSchema(BaseModel):
    """Corrected text for one requested OCR block."""

    model_config = ConfigDict(extra="forbid")

    block_id: int
    ocr_text_corrected: str = Field(min_length=1)


class PageCorrectionResponseSchema(BaseModel):
    """Strict page-level correction response."""

    model_config = ConfigDict(extra="forbid")

    blocks: List[PageCorrectionBlockOutputSchema]


class PageCorrectionCallResultSchema(BaseModel):
    """Validated page corrections with provider token usage."""

    blocks: List[PageCorrectionBlockOutputSchema]
    token_usage: TokenUsageSchema
