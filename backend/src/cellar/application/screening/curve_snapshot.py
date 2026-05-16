"""Curve-snapshot builders — freeze a DR curve's drawable shape into JSONB.

Single source of truth for the JSONB shape stored on campaign measurements
*and* sent on the wire for search / molecule-activity grids in aggregate
modes. The FE's shared ``DoseResponseFigure`` / ``DoseResponseChart``
components read these dicts directly, so the snapshot is what makes a
curve reproducible without a live FK lookup back to the underlying
``DoseResponseCurve`` row.

Two builders, both pure functions over ``ResolvedRun``:

- ``build_curve_snapshot`` — single curve (latest_approved_run / best_r²).
- ``build_aggregate_curve_snapshot`` — representative curve + every other
  contributor as ``additional_curves[]`` + an explicit ``aggregate`` marker
  carrying the cell value (used when the per-curve intercept dashed line
  would mislead, e.g. mean / gmean cells).

Lifted from ``application/research_organization/channel_resolution.py``
so that ``application/screening/molecule_activity_service.py`` can produce
the same overlay shape for search grids without a cross-context import.
"""

from __future__ import annotations

from datetime import date

from cellar.application.screening.run_aggregation import ResolvedRun


def condense_curve_points(
    raw: list[dict] | None,
) -> list[dict] | None:
    """Convert raw_data items to ``{x, y, ...}`` for FE consumption.

    Accepts both legacy ``{concentration, response}`` and modern ``{x, y}``
    shapes; preserves every other field (is_excluded, is_outlier,
    replicate_count, …) so the campaign rendering matches what the
    protocol Activity tab draws.
    """
    if not raw:
        return None
    out: list[dict] = []
    for pt in raw:
        if not isinstance(pt, dict):
            continue
        item: dict = dict(pt)  # shallow copy so we don't mutate the JSONB
        if "x" not in item and "concentration" in item:
            item["x"] = item.pop("concentration")
        if "y" not in item and "response" in item:
            item["y"] = item.pop("response")
        out.append(item)
    return out


def build_curve_snapshot(c: ResolvedRun) -> dict | None:
    """Freeze a DR candidate's full curve shape into a JSONB-able dict.

    Returns None when the candidate has no curve shape (readout_data
    sources, or a defensive fallback when the SQL didn't populate the
    extra columns). The shape mirrors what the frontend's shared
    DoseResponseFigure component expects, so the drawing is reproducible
    from this dict alone without a live FK lookup.
    """
    if c.curve_top is None or c.curve_bottom is None or c.curve_hill_slope is None:
        return None
    snap: dict = {
        "fitted_value": c.value,
        "top": c.curve_top,
        "bottom": c.curve_bottom,
        "hill_slope": c.curve_hill_slope,
        "r_squared": c.curve_r_squared,
        "curve_class": c.curve_class,
        "raw_data": condense_curve_points(c.curve_raw_data) or [],
    }
    excluded = condense_curve_points(c.curve_excluded_points)
    if excluded:
        snap["excluded_points"] = excluded
    # Extra fields the FE <DoseResponseChart> reads. Without these the
    # campaign's expand-dialog would lose the secondary intercept chips,
    # CI strip, and fit-warning badges that the search + protocol-runs
    # surfaces already show. None values are preserved on the wire so the
    # FE can distinguish "not yet fit" from "0".
    if c.curve_type is not None:
        snap["curve_type"] = c.curve_type
    if c.curve_confidence_interval_low is not None:
        snap["confidence_interval_low"] = c.curve_confidence_interval_low
    if c.curve_confidence_interval_high is not None:
        snap["confidence_interval_high"] = c.curve_confidence_interval_high
    if c.intercept_values:
        snap["intercept_values"] = c.intercept_values
    if c.curve_fit_quality_warnings:
        snap["fit_quality_warnings"] = c.curve_fit_quality_warnings
    return snap


def build_aggregate_curve_snapshot(
    candidates: list[ResolvedRun],
    *,
    aggregate_value: float,
    aggregate_label: str,
) -> dict | None:
    """Build a curve_snapshot for an aggregate-mode cell.

    Top-level keys mirror the representative (latest-by-date) candidate's
    snapshot. ``additional_curves`` carries the other contributors so the
    chart can overlay them muted; each carries ``run_date`` + ``run_id``
    so the chart can key + label per-run on hover. ``aggregate`` carries
    the marker position the chart draws (in aggregate modes, the per-curve
    intercept dashed lines don't represent the cell value; the chart should
    suppress them and fall back to this single marker).

    Returns ``None`` when the representative candidate has no curve shape
    (e.g. readout_data sources) — same fallback as ``build_curve_snapshot``
    so the measurement carries no snapshot at all and the FE renders "—"
    in the curve column.
    """
    if not candidates:
        return None
    rep = max(candidates, key=lambda c: c.run_date or date.min)
    rep_snap = build_curve_snapshot(rep)
    if rep_snap is None:
        return None  # readout_data source — no curves to overlay

    additional: list[dict] = []
    for c in sorted(
        (c for c in candidates if c.run_id != rep.run_id),
        key=lambda c: c.run_date or date.min,
        reverse=True,
    ):
        snap = build_curve_snapshot(c)
        if snap is None:
            continue
        snap["run_date"] = c.run_date.isoformat() if c.run_date else None
        snap["run_id"] = str(c.run_id)
        additional.append(snap)

    rep_snap["additional_curves"] = additional
    rep_snap["aggregate"] = {
        "marker_x": aggregate_value,
        "marker_label": aggregate_label,
        "unit": rep.unit or "",
    }
    return rep_snap
