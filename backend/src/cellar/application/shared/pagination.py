"""Application-layer pagination primitives.

Re-exports domain pagination types and adds application-level utilities.
"""

from __future__ import annotations

import uuid

from cellar.domain.shared.pagination import EnrichedPageResult, PageResult

# Re-export domain types so existing application-layer imports continue to work.
__all__ = [
    "COLLECTION_FETCH_MAX_PAGE_SIZE",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "EnrichedPageResult",
    "PageResult",
    "clamp_limit",
    "parse_cursor",
]

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
# For collection-scoped fetches (a single {type:"collection"} criterion) the
# chemist is asking for ALL members — pagination is wrong UX. We still cap so
# pathological 50K-mol collections don't blow up the response, but the limit
# is large enough to atomically load every realistic curated collection.
COLLECTION_FETCH_MAX_PAGE_SIZE = 10_000


def parse_cursor(cursor: str | None) -> uuid.UUID | None:
    """Parse a cursor string into a UUID, or return ``None``."""
    if cursor is None:
        return None
    try:
        return uuid.UUID(cursor)
    except ValueError:
        return None


def clamp_limit(limit: int | None, *, max_size: int = MAX_PAGE_SIZE) -> int:
    """Clamp a requested page size to [1, max_size], defaulting to DEFAULT_PAGE_SIZE.

    Pass ``max_size=COLLECTION_FETCH_MAX_PAGE_SIZE`` for collection-scoped
    fetches where the chemist expects to see every member of the set.
    """
    if limit is None:
        return DEFAULT_PAGE_SIZE
    return max(1, min(limit, max_size))
