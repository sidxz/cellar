"""Enums for the Research Organization bounded context."""

from __future__ import annotations

from enum import StrEnum

from cellar.domain.shared.aggregation_types import (
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class CollectionVisibility(StrEnum):
    PRIVATE = "private"
    SHARED = "shared"


class CollectionType(StrEnum):
    GENERIC = "generic"
    REFERENCE_SET = "reference_set"
    LIBRARY = "library"
    HIT_LIST = "hit_list"
    SERIES = "series"
    DISTRIBUTION_SET = "distribution_set"


class CollectionBooleanOp(StrEnum):
    UNION = "union"
    INTERSECT = "intersect"
    DIFFERENCE = "difference"
    SYMMETRIC_DIFFERENCE = "symmetric_difference"


class SearchVisibility(StrEnum):
    PRIVATE = "private"
    PROJECT = "project"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    CLOSED = "closed"
    SUPERSEDED = "superseded"


class ChannelSourceKind(StrEnum):
    READOUT_DATA = "readout_data"
    DOSE_RESPONSE_CURVE = "dose_response_curve"


class HitCall(StrEnum):
    HIT = "hit"
    MISS = "miss"
    INCONCLUSIVE = "inconclusive"


class CampaignDecision(StrEnum):
    SELECTED = "selected"
    DEFERRED = "deferred"
    REJECTED = "rejected"


# Re-exports — the canonical definitions live in domain.shared.aggregation_types
# (consumed by both research_organization and screening_assay; the bounded-
# context-independence contract requires the canonical home to be in shared).
# A screening-side ergonomic alias also exists at
# domain.screening_assay.aggregation_types. Campaign code still imports these
# names from here; declare them in __all__ so the re-export is explicit (and
# so F401 doesn't flag the import block).
__all__ = [
    "CampaignDecision",
    "CampaignStatus",
    "ChannelSourceKind",
    "CollectionBooleanOp",
    "CollectionType",
    "CollectionVisibility",
    "HitCall",
    "ProjectStatus",
    "QualifierHandling",
    "SearchVisibility",
    "SelectionRule",
    "ValueQualifier",
]
