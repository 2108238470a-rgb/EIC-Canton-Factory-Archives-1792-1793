from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, model_validator

FIELDS = {
    "person": "人名",
    "name_form": "人名形式",
    "honorific": "敬称或称号",
    "nationality": "国籍",
    "occupation": "职业",
    "organization": "人物所属机构",
    "event": "事件",
    "location": "地点",
    "related_event": "相关事件",
    "notes": "备注",
    "role": "参与角色",
    "title": "当时职务",
    "document_date": "文书日期",
    "event_date": "事件日期",
}


class ResearchScope(BaseModel):
    document_id: int | None = None
    document_ids: list[int] = Field(default_factory=list, max_length=100)
    corpus_id: int | None = None
    date_start: date | None = None
    date_end: date | None = None
    entity_id: int | None = None
    unit_type: str | None = None
    mode: Literal["verified", "explore"] = "verified"

    @model_validator(mode="after")
    def date_order(self):
        if self.date_start and self.date_end and self.date_start > self.date_end:
            raise ValueError("起始日期不能晚于结束日期")
        return self


class EvidenceCreate(BaseModel):
    block_id: int
    text_field: (
        Literal[
            "ocr_text_raw", "ocr_text_corrected", "modern_english", "translation_zh"
        ]
        | None
    ) = None
    expected_text: str
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)


class AnnotationCreate(BaseModel):
    document_id: int
    source_unit_id: int | None = None
    evidence_ids: list[int] = Field(min_length=1, max_length=50)
    fields: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def known_fields(self):
        if set(self.fields) - FIELDS.keys():
            raise ValueError("包含未知标注字段")
        if not any(v.strip() for v in self.fields.values()):
            raise ValueError("至少填写一项标注")
        if any(len(v) > 5000 for v in self.fields.values()):
            raise ValueError("标注字段过长")
        return self


class ReviewRequest(BaseModel):
    expected_version: int = Field(ge=1)
    field: str
    decision: Literal["approved", "rejected", "pending"]
    value: str | None = Field(None, max_length=5000)
    reason: str = Field("", max_length=5000)
    reviewer: str = Field("研究者", min_length=1, max_length=255)
    entity_id: int | None = None


class SegmentPart(BaseModel):
    block_id: int
    revision_id: int
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)


class SourceUnitCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    unit_type: Literal[
        "letter_incoming",
        "letter_outgoing",
        "diary_entry",
        "meeting_minutes",
        "report",
        "attachment",
        "title",
        "other",
    ] = "other"
    original_date_text: str | None = None
    normalized_date_start: date | None = None
    normalized_date_end: date | None = None
    date_precision: Literal["unknown", "year", "month", "day", "approximate"] = (
        "unknown"
    )
    spans: list[SegmentPart] = Field(min_length=1, max_length=200)


class ExtractionRequest(BaseModel):
    page_start: int = Field(1, ge=1)
    page_end: int | None = Field(None, ge=1)
    force_new: bool = False


class IdentityRequest(BaseModel):
    annotation_version: int
    entity_id: int | None = None
    reason: str = Field(min_length=1)
