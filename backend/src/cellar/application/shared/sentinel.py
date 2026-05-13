"""Application-layer sentinel value for partial update commands.

Use ``UNSET`` as the default for optional command fields that distinguish
"not provided" from "explicitly set to None". Domain entities have their
own private sentinel — this one lives in the application layer so that
interface code never imports a domain implementation detail.
"""

from __future__ import annotations

from typing import Any


class _UnsetType:
    """Singleton sentinel — ``field is UNSET`` means the caller did not supply it."""

    _instance: _UnsetType | None = None

    def __new__(cls) -> _UnsetType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> bool:
        return False


UNSET: Any = _UnsetType()
"""Sentinel value — use as default for optional command/query fields."""
