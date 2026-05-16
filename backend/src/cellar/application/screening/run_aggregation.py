"""Shared aggregator for collapsing N runs of a (compound, intercept) cell.

Single source of truth for two screening contexts:
- Campaign channel resolution (``application/research_organization/channel_resolution.py``)
- Search & molecule-activity grids (``application/screening/molecule_activity_service.py``)

Both adapt their domain rows into a ``ResolvedRun`` value object, then
call into pure functions here. Selection rules, intercept resolution,
and chemistry-honest variance statistics live in one place.

The intercept-resolution rules (Inactive -> ND, at_bound -> GT max_dose)
match industry convention (CDD / Genedata / ChEMBL); see
``feedback_drc_identity.md`` and ``feedback_chemistry_industry_practice.md``
in long-lived memory for context.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date

from cellar.domain.screening_assay.aggregation_types import (
    AggregateStats,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.shared.hit_criterion import InterceptKey


@dataclass(frozen=True)
class ResolvedRun:
    """A single run's contribution to a (compound, intercept) cell.

    Generic over both campaign and search contexts. Built by adapters
    in either place from ``DoseResponseCurve`` (+ owning Run) or from a
    SQL-side projection. Once constructed, the aggregator treats every
    instance uniformly.
    """

    run_id: uuid.UUID
    run_date: date | None
    run_approved: bool
    curve_id: uuid.UUID | None
    value: float | None
    qualifier: ValueQualifier
    unit: str
    z_prime: float | None
    protocol_name: str
    protocol_version: int
    readout_id: uuid.UUID | None
    curve_class: str | None = None
    curve_top: float | None = None
    curve_bottom: float | None = None
    curve_hill_slope: float | None = None
    curve_r_squared: float | None = None
    curve_raw_data: list[dict] | None = None
    # Per-point exclusion flags carried separately from raw_data so the
    # campaign's expand-dialog can draw the excluded markers. The search /
    # molecule-activity adapters don't populate this (None is fine — the
    # campaign-side _build_curve_snapshot guards on truthiness).
    curve_excluded_points: list[dict] | None = None
    intercept_values: list[dict] | None = None
    curve_type: str | None = None
    curve_confidence_interval_low: float | None = None
    curve_confidence_interval_high: float | None = None
    curve_fit_quality_warnings: list[str] | None = None


@dataclass(frozen=True)
class AggregateResult:
    """Output of ``apply_selection_rule``.

    ``representative_run`` is ``None`` only when:
    - The input run list was empty after qualifier filtering, OR
    - ``MANUAL_PICK`` was the rule (campaign-only path).

    For every other ND case (e.g. all runs Inactive under
    LATEST_APPROVED_RUN), ``representative_run`` is the latest-by-date
    run from the (non-empty) filtered input — so callers always have
    *something* to render as a curve thumbnail on the ND cell.
    """

    value: float | None
    qualifier: ValueQualifier
    contributing_run_ids: list[uuid.UUID]
    representative_run: ResolvedRun | None  # for snapshot/curve display


# ---------------------------------------------------------------------------
# Intercept resolution — public versions of the formerly private helpers in
# channel_resolution.py.
# ---------------------------------------------------------------------------


def _max_dose_from_raw(raw_data: list[dict] | None) -> float | None:
    """Largest positive concentration on a candidate's raw_data.

    Used to phrase the upper-bound qualifier on at_bound rows
    (``> {max_dose}``). Accepts the persisted ``{concentration, response}``
    shape as well as the chart-normalized ``{x, y}`` shape; ignores
    non-positive / non-finite x.
    """
    if not raw_data:
        return None
    best: float | None = None
    for pt in raw_data:
        raw = pt.get("concentration") if "concentration" in pt else pt.get("x")
        if not isinstance(raw, (int, float)):
            continue
        x = float(raw)
        if not math.isfinite(x) or x <= 0:
            continue
        if best is None or x > best:
            best = x
    return best


def resolve_intercept(
    run: ResolvedRun, intercept_key: InterceptKey | None
) -> tuple[float | None, ValueQualifier]:
    """Resolve one run's intercept to a (value, qualifier) cell.

    See ``channel_resolution._resolve_intercept`` (now removed) for the
    historical docstring. Three outcomes: (value, EQ), (max_dose, GT) for
    at_bound, (None, ND) for Inactive / missing intercept / at_bound
    without max_dose.
    """
    if run.curve_class == "inactive":
        return None, ValueQualifier.ND

    if intercept_key is None:
        ivs = run.intercept_values
        if ivs:
            primary = ivs[0]
            if primary.get("at_bound") is True:
                max_dose = _max_dose_from_raw(run.curve_raw_data)
                if max_dose is not None:
                    return max_dose, ValueQualifier.GT
                return None, ValueQualifier.ND
        return run.value, ValueQualifier.EQ

    ivs = run.intercept_values
    if not ivs:
        return None, ValueQualifier.ND
    target_kind = intercept_key.kind
    target_level = intercept_key.level
    for iv in ivs:
        spec = iv.get("spec") or {}
        if spec.get("kind") == target_kind and spec.get("level") == target_level:
            if iv.get("at_bound") is True:
                max_dose = _max_dose_from_raw(run.curve_raw_data)
                if max_dose is not None:
                    return max_dose, ValueQualifier.GT
                return None, ValueQualifier.ND
            val = iv.get("value")
            if isinstance(val, (int, float)):
                return float(val), ValueQualifier.EQ
            return None, ValueQualifier.ND
    return None, ValueQualifier.ND


def intercept_scalar(
    run: ResolvedRun, intercept_key: InterceptKey | None
) -> float | None:
    """Numeric scalar suitable for aggregation. Returns None for non-EQ."""
    value, qualifier = resolve_intercept(run, intercept_key)
    return value if qualifier == ValueQualifier.EQ else None


# ---------------------------------------------------------------------------
# Selection rules.
# ---------------------------------------------------------------------------


def _is_qualified(run: ResolvedRun) -> bool:
    """True when the run's wire-level qualifier is GT or LT (a detection-limit cell)."""
    return run.qualifier in {ValueQualifier.LT, ValueQualifier.GT}


def _filter_by_qualifier_handling(
    runs: list[ResolvedRun], handling: QualifierHandling
) -> list[ResolvedRun]:
    """Drop or carry through GT/LT-qualified runs based on the handling rule."""
    if handling == QualifierHandling.EXCLUDE_QUALIFIED:
        return [r for r in runs if not _is_qualified(r)]
    if handling == QualifierHandling.INCLUDE_QUALIFIED:
        return list(runs)
    if handling == QualifierHandling.TREAT_AS_LIMIT:
        raise NotImplementedError(
            "TREAT_AS_LIMIT semantics aren't defined in the shared aggregator yet "
            "(channel_resolution may handle this differently). "
            "Pass EXCLUDE_QUALIFIED or INCLUDE_QUALIFIED until search/campaign agree on a unified rule."
        )
    raise NotImplementedError(f"Unknown QualifierHandling: {handling!r}")


def _eq_runs(
    runs: list[ResolvedRun], intercept_key: InterceptKey | None
) -> list[ResolvedRun]:
    """Subset of runs whose intercept resolves to an EQ scalar."""
    return [
        r for r in runs if resolve_intercept(r, intercept_key)[1] == ValueQualifier.EQ
    ]


def _resolvable_runs(
    runs: list[ResolvedRun], intercept_key: InterceptKey | None
) -> list[ResolvedRun]:
    """Subset of runs whose intercept resolves to a numeric value.

    Includes both EQ (healthy fit) and GT (at_bound → >max_dose) outcomes;
    excludes ND (inactive, missing intercept, at_bound with no max_dose).

    Used by the "pick one" rules (LATEST_APPROVED_RUN, BEST_R_SQUARED)
    where an at_bound row IS a real measurement and should surface as a
    GT-qualified cell. The aggregating rules (MEAN, GEOMETRIC_MEAN) use
    ``intercept_scalar`` instead, which keeps only EQ rows — non-scalar
    rows can't participate honestly in an arithmetic / log-space average.
    """
    return [
        r for r in runs if resolve_intercept(r, intercept_key)[0] is not None
    ]


def _latest_by_date(runs: list[ResolvedRun]) -> ResolvedRun:
    """Pick the run with the largest run_date; treats missing dates as date.min."""
    return max(runs, key=lambda r: r.run_date or date.min)


def _pick_one_eq(
    runs: list[ResolvedRun],
    intercept_key: InterceptKey | None,
    key_fn,
) -> AggregateResult:
    """Pick the single resolvable run that maximizes ``key_fn``; ND otherwise.

    Used by LATEST_APPROVED_RUN (key_fn = run_date) and BEST_R_SQUARED
    (key_fn = curve_r_squared). Both EQ and GT-from-at_bound runs are
    eligible — an at_bound run carries a real upper-bound measurement
    and should win on date / r² over an EQ run if it sorts that way.
    Only ND-resolving runs (Inactive, missing intercept) are filtered.
    """
    resolvable = _resolvable_runs(runs, intercept_key)
    if not resolvable:
        return AggregateResult(
            value=None,
            qualifier=ValueQualifier.ND,
            contributing_run_ids=[],
            representative_run=_latest_by_date(runs),
        )
    pick = max(resolvable, key=key_fn)
    value, qualifier = resolve_intercept(pick, intercept_key)
    return AggregateResult(
        value=value,
        qualifier=qualifier,
        contributing_run_ids=[pick.run_id],
        representative_run=pick,
    )


def _aggregate_eq(
    runs: list[ResolvedRun],
    intercept_key: InterceptKey | None,
    *,
    require_positive: bool,
    agg_fn,
) -> AggregateResult:
    """Aggregate EQ-resolving scalars via ``agg_fn``; ND if none qualify.

    Used by MEAN_ACROSS_RUNS (require_positive=False, agg_fn=mean) and
    GEOMETRIC_MEAN (require_positive=True, agg_fn=geomean).
    """
    pairs = [(r, intercept_scalar(r, intercept_key)) for r in runs]
    qualifying = [
        (r, s) for r, s in pairs if s is not None and (s > 0 or not require_positive)
    ]
    if not qualifying:
        return AggregateResult(
            value=None,
            qualifier=ValueQualifier.ND,
            contributing_run_ids=[],
            representative_run=_latest_by_date(runs),
        )
    eq_runs = [r for r, _ in qualifying]
    scalars = [s for _, s in qualifying]
    return AggregateResult(
        value=agg_fn(scalars),
        qualifier=ValueQualifier.EQ,
        contributing_run_ids=[r.run_id for r in eq_runs],
        representative_run=_latest_by_date(eq_runs),
    )


def _arithmetic_mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _geometric_mean(values: list[float]) -> float:
    return math.exp(sum(math.log(v) for v in values) / len(values))


def apply_selection_rule(
    runs: list[ResolvedRun],
    rule: SelectionRule,
    qualifier_handling: QualifierHandling,
    intercept_key: InterceptKey | None,
) -> AggregateResult:
    """Collapse multiple runs into a single (value, qualifier) cell."""
    filtered = _filter_by_qualifier_handling(runs, qualifier_handling)

    if not filtered:
        return AggregateResult(
            value=None,
            qualifier=ValueQualifier.ND,
            contributing_run_ids=[],
            representative_run=None,
        )

    if rule == SelectionRule.LATEST_APPROVED_RUN:
        return _pick_one_eq(
            filtered, intercept_key, key_fn=lambda r: r.run_date or date.min
        )

    if rule == SelectionRule.BEST_R_SQUARED:
        # `r.curve_r_squared if not None else -inf` (not `or -inf`) so a
        # legal r²=0.0 (a flat trace) doesn't tie with `None` runs and
        # lose to whatever order Python's `max` happens to pick.
        return _pick_one_eq(
            filtered,
            intercept_key,
            key_fn=lambda r: r.curve_r_squared if r.curve_r_squared is not None else -math.inf,
        )

    if rule == SelectionRule.MEAN_ACROSS_RUNS:
        return _aggregate_eq(
            filtered, intercept_key, require_positive=False, agg_fn=_arithmetic_mean
        )

    if rule == SelectionRule.GEOMETRIC_MEAN:
        return _aggregate_eq(
            filtered, intercept_key, require_positive=True, agg_fn=_geometric_mean
        )

    if rule == SelectionRule.MANUAL_PICK:
        # Search context has no chemist picker; campaigns handle MANUAL_PICK
        # via a separate code path that doesn't go through this aggregator.
        return AggregateResult(
            value=None,
            qualifier=ValueQualifier.ND,
            contributing_run_ids=[],
            representative_run=None,
        )

    raise NotImplementedError(f"Unknown SelectionRule: {rule!r}")


# ---------------------------------------------------------------------------
# Variance / disagreement.
# ---------------------------------------------------------------------------

DISAGREEMENT_LOG_THRESHOLD: float = 1.0
"""log10-units of spread above which the cell shows a disagreement glyph.
v1 is fixed; later revisits may make this per-protocol if chemists ask."""


def compute_aggregate_stats(
    runs: list[ResolvedRun], intercept_key: InterceptKey | None
) -> AggregateStats:
    """Geometric mean + fold-range + log-value mean ± sample SD over EQ runs only.

    Uses sample SD (Bessel's correction, ``n-1`` divisor) — the
    chemistry convention for replicate variance. Single-EQ-run cells
    return ``log_value_sd=0.0`` by special-case so the public API never
    surfaces ``NaN``.

    ``log_value`` is ``log10(value_in_dose_unit)``. The FE composes the
    pX label (pIC50 = -log10(value_M) = 6 - log10(value_uM)) by reading
    the cell's dose unit alongside.
    """
    scalars = [
        v
        for v in (intercept_scalar(r, intercept_key) for r in runs)
        if v is not None and v > 0
    ]
    if not scalars:
        return AggregateStats(
            geometric_mean=None,
            fold_range=None,
            log_value_mean=None,
            log_value_sd=None,
        )

    log_values = [math.log10(v) for v in scalars]
    log_mean = sum(log_values) / len(log_values)
    # Sample standard deviation (Bessel's correction, n-1) — the chemistry
    # convention for variability across replicates. With n=1 the spread is
    # undefined by formula; we return 0.0 so the UI doesn't have to special-case.
    log_sd = (
        math.sqrt(sum((lv - log_mean) ** 2 for lv in log_values) / (len(log_values) - 1))
        if len(log_values) > 1
        else 0.0
    )

    return AggregateStats(
        geometric_mean=10**log_mean,
        fold_range=max(scalars) / min(scalars) if len(scalars) > 1 else 1.0,
        log_value_mean=log_mean,
        log_value_sd=log_sd,
    )


def detect_disagreement(
    runs: list[ResolvedRun], intercept_key: InterceptKey | None
) -> bool:
    """True when the cell deserves a disagreement glyph.

    Two triggers:
    - log10-range across EQ-qualified runs > ``DISAGREEMENT_LOG_THRESHOLD``
    - mixed: at least one EQ run AND at least one non-EQ run (Inactive/at_bound)
    """
    qualifiers = [resolve_intercept(r, intercept_key)[1] for r in runs]
    eq_count = sum(1 for q in qualifiers if q == ValueQualifier.EQ)
    non_eq_count = len(qualifiers) - eq_count

    if eq_count >= 1 and non_eq_count >= 1:
        return True

    scalars = [
        v
        for v in (intercept_scalar(r, intercept_key) for r in runs)
        if v is not None and v > 0
    ]
    if len(scalars) < 2:
        return False
    log_range = math.log10(max(scalars)) - math.log10(min(scalars))
    return log_range > DISAGREEMENT_LOG_THRESHOLD
