"""Enums for the Research Organization bounded context."""

from __future__ import annotations

from enum import StrEnum


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class CollectionVisibility(StrEnum):
    PRIVATE = "private"
    SHARED = "shared"


class CollectionBooleanOp(StrEnum):
    UNION = "union"
    INTERSECT = "intersect"
    DIFFERENCE = "difference"
    SYMMETRIC_DIFFERENCE = "symmetric_difference"


class SearchVisibility(StrEnum):
    PRIVATE = "private"
    PROJECT = "project"
