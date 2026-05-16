"""Aggregation primitives shared across bounded contexts.

The selection-rule enums originally lived in
``domain/research_organization/enums.py`` because campaigns were the
first user. They describe a screening-domain concept (how to collapse
multi-run measurements) but are now consumed by both
``research_organization`` (campaign channels) and ``screening_assay``
(search-grid + Activity tabs) — and the bounded-context-independence
contract forbids one context's domain module importing from another.
Promoted to ``domain/shared`` here so both contexts depend on the same
single source of truth without crossing context boundaries.

Member sets and string values are preserved verbatim from the prior
location to avoid DB migrations and back-compat breaks.

``AggregateStats`` is the chemistry-honest variance summary — defined
once so the application-layer aggregator and the wire-shape
``ActivityValue`` use the same type, no duplication.

The single net-new symbol is ``SelectionRule.BEST_R_SQUARED`` — the
search toolbar's "show me the best fit" mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SelectionRule(StrEnum):
    """How to collapse multiple runs of the same (compound, intercept) pair."""

    LATEST_APPROVED_RUN = "latest_approved_run"
    MEAN_ACROSS_RUNS = "mean_across_runs"
    GEOMETRIC_MEAN = "geometric_mean"
    MANUAL_PICK = "manual_pick"
    BEST_R_SQUARED = "best_r_squared"


class QualifierHandling(StrEnum):
    """Whether to drop or carry through GT/LT/ND-qualified candidates.

    Three members preserved verbatim from the prior research_organization
    location — TREAT_AS_LIMIT is used by some campaign code paths and
    must not be removed.
    """

    INCLUDE_QUALIFIED = "include_qualified"
    EXCLUDE_QUALIFIED = "exclude_qualified"
    TREAT_AS_LIMIT = "treat_as_limit"


class ValueQualifier(StrEnum):
    """Cell-level qualifier on a resolved measurement.

    Five members preserved verbatim — the chemistry-symbol string values
    (``"="``, ``"<"``, ``">"``) are persisted to DB on
    ``campaign_measurement.value_qualifier``; changing them would
    require a data migration. ``EXCLUDED`` is set when a chemist
    explicitly excluded a measurement on the campaign grid.
    """

    EQ = "="
    LT = "<"
    GT = ">"
    ND = "nd"
    EXCLUDED = "excluded"


@dataclass(frozen=True)
class AggregateStats:
    """Variance summary across the EQ-qualified runs for one intercept.

    ``log_value_mean`` is mean of ``log10(value_in_dose_unit)``. The FE
    composes the chemistry label (pIC50, pEC50) by combining with the
    cell's dose unit. All four fields are ``None`` when no EQ run
    contributed (e.g. the cell collapsed to ND).
    """

    geometric_mean: float | None
    fold_range: float | None
    log_value_mean: float | None
    log_value_sd: float | None
