"""Cursor-based pagination utilities for API endpoints.

Constants and helpers (``DEFAULT_PAGE_SIZE``, ``MAX_PAGE_SIZE``,
``parse_cursor``, ``clamp_limit``) are re-exported from
``cellar.application.shared.pagination`` so the API layer and application
layer agree on a single source of truth. The Pydantic response wrapper
``PaginatedResponse`` is API-specific and stays here.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

from cellar.application.shared.pagination import (
    COLLECTION_FETCH_MAX_PAGE_SIZE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    clamp_limit,
    parse_cursor,
)

__all__ = [
    "COLLECTION_FETCH_MAX_PAGE_SIZE",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "PaginatedResponse",
    "clamp_limit",
    "parse_cursor",
]

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper.

    Attributes:
        items: The page of results.
        next_cursor: Opaque cursor for fetching the next page, or ``None``
            when there are no more results.
        total_count: Optional total count (only provided when feasible).
    """

    items: list[T]
    next_cursor: str | None = None
    total_count: int | None = None
