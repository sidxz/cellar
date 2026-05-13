"""CascadeAction — domain-level enum for cascade outcome semantics."""

from __future__ import annotations

from enum import StrEnum


class CascadeAction(StrEnum):
    CASCADE = "cascade"
    SET_NULL = "set_null"
    BLOCK = "block"
    WARN = "warn"
