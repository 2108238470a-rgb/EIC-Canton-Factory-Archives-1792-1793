"""Page repository."""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Page
from app.schemas import PageCreate, PageUpdate


class PageRepository:
    """Repository for page operations."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, data: PageCreate) -> Page:
        """Create a new page."""
        page = Page(**data.model_dump())
        self.db.add(page)
        self.db.commit()
        self.db.refresh(page)
        return page

    def create_many(self, pages_data: List[PageCreate]) -> List[Page]:
        """Create multiple pages."""
        pages = [Page(**data.model_dump()) for data in pages_data]
        self.db.add_all(pages)
        self.db.commit()
        for page in pages:
            self.db.refresh(page)
        return pages

    def get_by_id(self, page_id: int) -> Optional[Page]:
        """Get page by ID."""
        return self.db.query(Page).filter(Page.id == page_id).first()

    def get_by_document(self, document_id: int) -> List[Page]:
        """Get all pages for a document."""
        return (
            self.db.query(Page)
            .filter(Page.document_id == document_id)
            .order_by(Page.page_number)
            .all()
        )

    def get_by_document_and_number(self, document_id: int, page_number: int) -> Optional[Page]:
        """Get page by document ID and page number."""
        return (
            self.db.query(Page)
            .filter(Page.document_id == document_id, Page.page_number == page_number)
            .first()
        )

    def update(self, page_id: int, data: PageUpdate) -> Optional[Page]:
        """Update page."""
        page = self.get_by_id(page_id)
        if not page:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(page, field, value)

        self.db.commit()
        self.db.refresh(page)
        return page

    def delete_by_document(self, document_id: int) -> int:
        """Delete all pages for a document."""
        count = self.db.query(Page).filter(Page.document_id == document_id).delete()
        self.db.commit()
        return count
