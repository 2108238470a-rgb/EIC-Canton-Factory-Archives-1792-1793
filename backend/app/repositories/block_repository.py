"""Block repository."""
from typing import List, Mapping, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Block, ReviewStatus
from app.schemas import BlockCreate, BlockUpdate


class BlockRepository:
    """Repository for block operations."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, data: BlockCreate) -> Block:
        """Create a new block."""
        block = Block(**data.model_dump())
        self.db.add(block)
        self.db.commit()
        self.db.refresh(block)
        return block

    def create_many(self, blocks_data: List[BlockCreate]) -> List[Block]:
        """Create multiple blocks."""
        blocks = [Block(**data.model_dump()) for data in blocks_data]
        self.db.add_all(blocks)
        self.db.commit()
        for block in blocks:
            self.db.refresh(block)
        return blocks

    def get_by_id(self, block_id: int) -> Optional[Block]:
        """Get block by ID."""
        return self.db.query(Block).filter(Block.id == block_id).first()

    def get_by_page(self, page_id: int) -> List[Block]:
        """Get all blocks for a page."""
        return (
            self.db.query(Block)
            .filter(Block.page_id == page_id)
            .order_by(Block.block_index)
            .all()
        )

    def get_by_document(self, document_id: int) -> List[Block]:
        """Get all blocks for a document (via pages)."""
        from app.models import Page
        return (
            self.db.query(Block)
            .join(Page)
            .filter(Page.document_id == document_id)
            .order_by(Page.page_number, Block.block_index)
            .all()
        )

    def get_unprocessed_by_page(self, page_id: int) -> List[Block]:
        """Get blocks without a correction for their current raw OCR snapshot."""
        return (
            self.db.query(Block)
            .filter(
                Block.page_id == page_id,
                Block.ocr_text_raw.isnot(None),
                or_(
                    Block.ocr_text_corrected.is_(None),
                    Block.ocr_correction_source_text.is_(None),
                    Block.ocr_correction_source_text != Block.ocr_text_raw,
                ),
            )
            .order_by(Block.block_index)
            .all()
        )

    def update(self, block_id: int, data: BlockUpdate) -> Optional[Block]:
        """Update block."""
        block = self.get_by_id(block_id)
        if not block:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(block, field, value)
        if "ocr_text_corrected" in update_data:
            block.ocr_correction_source_text = block.ocr_text_raw

        self.db.commit()
        self.db.refresh(block)
        return block

    def update_text_fields(
        self,
        block_id: int,
        ocr_text_corrected: Optional[str] = None,
        modern_english: Optional[str] = None,
        translation_zh: Optional[str] = None
    ) -> Optional[Block]:
        """Update block text fields."""
        block = self.get_by_id(block_id)
        if not block:
            return None

        if ocr_text_corrected is not None:
            block.ocr_text_corrected = ocr_text_corrected
            block.ocr_correction_source_text = block.ocr_text_raw
        if modern_english is not None:
            block.modern_english = modern_english
        if translation_zh is not None:
            block.translation_zh = translation_zh

        self.db.commit()
        self.db.refresh(block)
        return block

    def update_page_corrections(
        self,
        page_id: int,
        corrections: Mapping[int, str],
        expected_raw_texts: Mapping[int, str],
    ) -> List[Block]:
        """Atomically persist corrections after exact source-text revalidation.

        Args:
            page_id: Page whose blocks are being corrected.
            corrections: Corrected OCR text keyed by block ID.
            expected_raw_texts: Exact OCR snapshots used for the GPT request.

        Returns:
            Updated blocks in page order.

        Raises:
            ValueError: If IDs differ, a block changed, or correction text is blank.
        """
        correction_ids = set(corrections)
        if not correction_ids or correction_ids != set(expected_raw_texts):
            raise ValueError("Correction IDs must exactly match source snapshot IDs")
        if any(not isinstance(text, str) or not text.strip() for text in corrections.values()):
            raise ValueError("Page corrections cannot contain blank text")

        try:
            blocks = (
                self.db.query(Block)
                .filter(Block.page_id == page_id, Block.id.in_(correction_ids))
                .with_for_update()
                .populate_existing()
                .order_by(Block.block_index)
                .all()
            )
            if {block.id for block in blocks} != correction_ids:
                raise ValueError("One or more correction blocks no longer exist on the page")

            for block in blocks:
                expected_raw = expected_raw_texts[block.id]
                if block.ocr_text_raw != expected_raw:
                    raise ValueError(
                        f"OCR source changed while correcting block {block.id}"
                    )
                block.ocr_text_corrected = corrections[block.id]
                block.ocr_correction_source_text = expected_raw

            self.db.commit()
            for block in blocks:
                self.db.refresh(block)
            return blocks
        except Exception:
            self.db.rollback()
            raise

    def count_by_page(self, page_id: int) -> int:
        """Count blocks for a page."""
        return self.db.query(Block).filter(Block.page_id == page_id).count()

    def delete_by_page(self, page_id: int) -> int:
        """Delete all blocks for a page."""
        count = self.db.query(Block).filter(Block.page_id == page_id).delete()
        self.db.commit()
        return count
