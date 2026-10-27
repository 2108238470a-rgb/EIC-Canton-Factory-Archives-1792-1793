"""Evidence span application service."""
from typing import List, Optional
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Block, Page
from app.knowledge.enums import TextVersion
from app.knowledge.models import EvidenceSpan
from app.knowledge.repositories import EvidenceRepository
from app.knowledge.schemas import EvidenceLocatorResponse, EvidenceSpanCreate, EvidenceSpanResponse


class EvidenceService:
    """Copy an OCR text layer into an immutable evidence span."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = EvidenceRepository(db)

    def create_from_block(self, data: EvidenceSpanCreate) -> EvidenceSpan:
        """Create a span from a block without mutating OCR fields.

        Args:
            data: Block ID, text version, and optional character offsets.

        Returns:
            New evidence span.

        Raises:
            HTTPException: If the block, text layer, offsets, or parent are invalid.
        """
        block = self.db.query(Block).filter(Block.id == data.block_id).first()
        if not block:
            raise HTTPException(status_code=404, detail="Block not found")

        source_text = self._text_for_version(block, data.text_version)
        if source_text is None or source_text == "":
            raise HTTPException(
                status_code=400,
                detail=f"Block {block.id} has no text for version {data.text_version.value}",
            )

        char_start = 0 if data.char_start is None else data.char_start
        char_end = len(source_text) if data.char_end is None else data.char_end
        if char_start >= char_end or char_end > len(source_text):
            raise HTTPException(
                status_code=400,
                detail="Evidence offsets must satisfy 0 <= start < end <= len(text)",
            )

        if data.parent_span_id is not None and not self.repo.get_by_id(data.parent_span_id):
            raise HTTPException(status_code=404, detail="Parent evidence span not found")

        span = EvidenceSpan(
            public_id=str(uuid4()),
            document_id=self._document_id(block),
            page_id=block.page_id,
            block_id=block.id,
            text_version=data.text_version,
            parent_span_id=data.parent_span_id,
            char_start=char_start,
            char_end=char_end,
            line_start=data.line_start,
            line_end=data.line_end,
            excerpt=source_text[char_start:char_end],
            quality_flag=data.quality_flag,
            ocr_risk=data.ocr_risk,
            extraction_source=data.extraction_source,
            created_by=data.created_by,
        )
        return self.repo.create(span)

    def get(self, span_id: int) -> EvidenceSpan:
        """Load a span by ID."""
        span = self.repo.get_by_id(span_id)
        if not span:
            raise HTTPException(status_code=404, detail="Evidence span not found")
        return span

    def list_recent(self, page: int, page_size: int) -> tuple[List[EvidenceSpan], int]:
        """List recent spans."""
        items = self.repo.list_recent(skip=(page - 1) * page_size, limit=page_size)
        return items, self.repo.count()

    def locator(self, span_id: int) -> EvidenceLocatorResponse:
        """Build a viewer locator for a span."""
        span = self.get(span_id)
        page = self.db.query(Page).filter(Page.id == span.page_id).first()
        block = self.db.query(Block).filter(Block.id == span.block_id).first()
        page_number = page.page_number if page else None
        viewer_path = f"/viewer/{span.document_id}"
        if page_number is not None:
            viewer_path += f"?page={page_number}&block={span.block_id}"
        return EvidenceLocatorResponse(
            evidence_span=EvidenceSpanResponse.model_validate(span),
            page_number=page_number,
            bbox=list(block.bbox) if block and block.bbox is not None else None,
            image_path=page.image_path if page else None,
            viewer_path=viewer_path,
        )

    def _document_id(self, block: Block) -> int:
        page = self.db.query(Page).filter(Page.id == block.page_id).first()
        if not page:
            raise HTTPException(status_code=400, detail="Block is missing its page")
        return page.document_id

    def _text_for_version(self, block: Block, version: TextVersion) -> Optional[str]:
        mapping = {
            TextVersion.OCR_RAW: block.ocr_text_raw,
            TextVersion.OCR_AUTO_CORRECTED: block.ocr_text_corrected,
            TextVersion.OCR_HUMAN_CORRECTED: block.ocr_text_corrected,
            TextVersion.MODERN_ENGLISH: block.modern_english,
            TextVersion.TRANSLATION_ZH: block.translation_zh,
        }
        return mapping[version]
