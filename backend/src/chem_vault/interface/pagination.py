"""Cursor-based pagination utilities for API endpoints."""

from __future__ import annotations

import uuid
from typing import Generic, TypeVar

from pydantic import BaseModel

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


DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def parse_cursor(cursor: str | None) -> uuid.UUID | None:
    """Parse a cursor string into a UUID, or return ``None``."""
    if cursor is None:
        return None
    try:
        return uuid.UUID(cursor)
    except ValueError:
        return None


def clamp_limit(limit: int | None) -> int:
    """Clamp a requested page size to [1, MAX_PAGE_SIZE], defaulting to DEFAULT_PAGE_SIZE."""
    if limit is None:
        return DEFAULT_PAGE_SIZE
    return max(1, min(limit, MAX_PAGE_SIZE))
