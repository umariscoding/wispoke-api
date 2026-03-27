"""
Shared pagination utilities — both DB-level and in-memory.
"""

from pydantic import BaseModel
from typing import Generic, TypeVar, List

T = TypeVar("T")

MAX_PAGE_SIZE = 100


class PaginationParams:
    """Normalise and clamp page/page_size from query parameters."""

    def __init__(self, page: int = 1, page_size: int = 20):
        self.page = max(1, page)
        self.page_size = min(max(1, page_size), MAX_PAGE_SIZE)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size

    @property
    def range_start(self) -> int:
        """0-based inclusive start for Supabase .range()."""
        return self.offset

    @property
    def range_end(self) -> int:
        """0-based inclusive end for Supabase .range()."""
        return self.offset + self.page_size - 1


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int


def paginate(items: list, page: int = 1, page_size: int = 20) -> dict:
    """In-memory pagination — use only when the full list is already loaded."""
    p = PaginationParams(page, page_size)
    total = len(items)
    total_pages = (total + p.page_size - 1) // p.page_size if total > 0 else 1
    sliced = items[p.offset: p.offset + p.page_size]
    return {
        "items": sliced,
        "total": total,
        "page": p.page,
        "page_size": p.page_size,
        "total_pages": total_pages,
    }


def make_paginated_result(items: list, total: int, page: int, page_size: int) -> dict:
    """Build a paginated result dict from pre-sliced items and a total count."""
    p = PaginationParams(page, page_size)
    total_pages = (total + p.page_size - 1) // p.page_size if total > 0 else 1
    return {
        "items": items,
        "total": total,
        "page": p.page,
        "page_size": p.page_size,
        "total_pages": total_pages,
    }
