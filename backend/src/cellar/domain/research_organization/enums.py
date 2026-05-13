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


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    CLOSED = "closed"
    SUPERSEDED = "superseded"


class SelectionRule(StrEnum):
    LATEST_APPROVED_RUN = "latest_approved_run"
    MEAN_ACROSS_RUNS = "mean_across_runs"
    GEOMETRIC_MEAN = "geometric_mean"
    MANUAL_PICK = "manual_pick"


class ChannelSourceKind(StrEnum):
    READOUT_DATA = "readout_data"
    DOSE_RESPONSE_CURVE = "dose_response_curve"


class ValueQualifier(StrEnum):
    EQ = "="
    LT = "<"
    GT = ">"
    ND = "nd"
    EXCLUDED = "excluded"


class HitCall(StrEnum):
    HIT = "hit"
    MISS = "miss"
    INCONCLUSIVE = "inconclusive"


class CampaignDecision(StrEnum):
    SELECTED = "selected"
    DEFERRED = "deferred"
    REJECTED = "rejected"


class QualifierHandling(StrEnum):
    INCLUDE_QUALIFIED = "include_qualified"
    EXCLUDE_QUALIFIED = "exclude_qualified"
    TREAT_AS_LIMIT = "treat_as_limit"
