"""Grouping key for readout names, shared across bounded contexts.

Used to match readout-defs by name across protocols (any-protocol search)
and to build a protocol's structural fingerprint. A controlled readout
vocabulary would replace this string key.
"""

from __future__ import annotations


def normalize_readout_name(name: str) -> str:
    """Lowercase, trimmed, internal whitespace collapsed to one space."""
    return " ".join(name.strip().lower().split())
