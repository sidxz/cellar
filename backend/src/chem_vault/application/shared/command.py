"""Command base — markers for write operations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class Command:
    """Base class for write-side commands.

    Commands are immutable value objects carrying the input data
    for a state-changing use case.
    """
