"""Shared SQL helpers for SQLAlchemy repositories."""

from __future__ import annotations


def escape_like(value: str) -> str:
    """Escape SQL LIKE/ILIKE metacharacters so they match literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
