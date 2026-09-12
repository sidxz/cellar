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


class StageKind(StrEnum):
    """How a stage decides its outcome.

    CRITERIA — the AND of its numeric criteria over the campaign's channels.
    MANUAL — no criteria at all: every compound in the stage's population sits
    at `StageOutcome.PENDING` until a chemist promotes (override -> hit) or
    demotes (override -> miss) it.
    """

    CRITERIA = "criteria"
    MANUAL = "manual"


class StageOutcome(StrEnum):
    """Per-(result, stage) verdict computed by `stage_evaluation.evaluate_stages`."""

    HIT = "hit"
    MISS = "miss"
    UNTESTED = "untested"
    NOT_IN_STAGE = "not_in_stage"
    PENDING = "pending"


class CheckVerdict(StrEnum):
    """Per-(result, criterion) verdict — one component of a StageOutcome."""

    PASS = "pass"
    FAIL = "fail"
    UNTESTED = "untested"


# Re-exports — the canonical definitions live in domain.shared.aggregation_types
# (consumed by both research_organization and screening_assay; the bounded-
# context-independence contract requires the canonical home to be in shared).
# A screening-side ergonomic alias also exists at
# domain.screening_assay.aggregation_types. Campaign code still imports these
# names from here; declare them in __all__ so the re-export is explicit (and
# so F401 doesn't flag the import block).
__all__ = [
    "CampaignStatus",
    "ChannelSourceKind",
    "CheckVerdict",
    "CollectionBooleanOp",
    "CollectionType",
    "CollectionVisibility",
    "ProjectStatus",
    "QualifierHandling",
    "SearchVisibility",
    "SelectionRule",
    "StageKind",
    "StageOutcome",
    "ValueQualifier",
]
