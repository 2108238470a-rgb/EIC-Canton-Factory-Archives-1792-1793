"""Shared Pydantic helpers for the knowledge module."""
from typing import Generic, List, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base schema that reads SQLAlchemy attributes."""

    model_config = ConfigDict(from_attributes=True)


class ListResponse(BaseModel, Generic[T]):
    """Paginated list envelope."""

    items: List[T]
    total: int
    page: int = 1
    page_size: int = 20
