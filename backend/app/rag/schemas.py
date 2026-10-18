"""Shared scope and stable, versioned evidence contracts."""

from typing import Any, Literal
from pydantic import BaseModel, Field
from app.workbench.schemas import ResearchScope


class IndexRequestSchema(BaseModel):
    document_id: int | None = Field(default=None, gt=0)
    document_ids: list[int] = Field(default_factory=list, max_length=200)


class IndexJobSchema(BaseModel):
    task_id: str
    state: str
    info: dict[str, Any] | None = None


class IndexStatusSchema(BaseModel):
    eligible: int
    indexed: int
    pending: int
    embedding_model: str
    vector_pending: int = 0


class SearchRequestSchema(ResearchScope):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(20, ge=1, le=100)
    retrieval: Literal["keyword", "semantic", "hybrid"] = "hybrid"


class ConversationTurnSchema(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(max_length=6000)


class QuestionRequestSchema(ResearchScope):
    history: list[ConversationTurnSchema] = Field(default_factory=list, max_length=6)
    question: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(8, ge=1, le=20)
    selected_chunk_ids: list[int] = Field(default_factory=list, max_length=20)
    retrieval: Literal["keyword", "semantic", "hybrid"] = "hybrid"


class SearchHitSchema(BaseModel):
    chunk_id: int
    block_id: int
    document_id: int
    document_title: str
    page_number: int
    content: str
    score: float
    viewer_path: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    review_state: str = "pending"
    content_type: str = "ocr_block_temporary"
    source_unit_id: int | None = None


class SearchResponseSchema(BaseModel):
    query: str
    items: list[SearchHitSchema]
    warnings: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    returned: int = 0
    exhaustive: bool = False


class CitationSchema(SearchHitSchema):
    index: int
    cited: bool


class AnswerClaim(BaseModel):
    category: Literal["context", "person", "event", "other"] = "other"
    text: str
    citations: list[int] = Field(min_length=1)
    quotes: list[str] = Field(min_length=1)


class AnswerSection(BaseModel):
    title: str
    content: str


class AnswerResponseSchema(BaseModel):
    sections: list[AnswerSection] = Field(default_factory=list)
    outcome: str = "answered"
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    question: str
    answer: str
    insufficient_evidence: bool
    citations: list[CitationSchema]
    model: str
    claims: list[AnswerClaim] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
