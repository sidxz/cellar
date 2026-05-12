"""Application-layer pagination primitives.

Re-exports domain pagination types and adds application-level utilities.
"""

from __future__ import annotations

import uuid

from cellar.domain.shared.pagination import EnrichedPageResult, PageResult

# Re-export domain types so existing application-layer imports continue to work.
__all__ = [
    "EnrichedPageResult",
    "PageResult",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "clamp_limit",
    "parse_cursor",
]

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
