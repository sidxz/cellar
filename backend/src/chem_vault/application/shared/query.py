"""Query base — markers for read operations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class Query:
    """Base class for read-side queries.

    Queries are immutable value objects carrying the input data
    for a read-only use case.
    """
