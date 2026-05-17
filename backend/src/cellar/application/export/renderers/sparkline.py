"""Dose-response sparkline renderer for exports.

This module mirrors the FE `DoseResponseFigure` (Plotly) so XLSX and PDF
exports show the same chart the chemist sees on screen:

  - Log10 x-axis with decade ticks (1e-3 .. 1e3 as fits the range)
  - Y-axis with 0/50/100 ticks
  - Green 4PL sigmoid for active curves, points-only for inactive
  - Dotted vertical line at fitted_value (single-curve / non-aggregate)
  - Aggregate mode: muted dashed sibling sigmoids + solid amber marker
    line at aggregate.marker_x

The PNG output is sized by caller; default 320x180 sits well in an XLSX
cell at default row height. ``size`` accepts a preset name ("small",
"medium", "large") matching ``reportConfig.imageSize``.
"""

from __future__ import annotations
import io
import math
from typing import Literal

SizePreset = Literal["small", "medium", "large"]

SIZE_PRESETS: dict[str, tuple[int, int]] = {
    "small": (240, 140),
    "medium": (320, 180),
    "large": (480, 260),
}

# Mirrors FE chart-colors.ts
_FIT_COLOR = "#18974c"             # CURVE_QUALITY_COLORS.full (green)
_INACTIVE_MARKER_COLOR = "#707372"  # CURVE_DEFAULT_COLOR (neutral)
_MARKER_COLOR = "#18974c"          # same as fit so points line up visually
_AGGREGATE_LINE = "#f49e17"        # CHART_COLORS.warning (amber)
_INTERCEPT_LINE = "#f49e17"        # same amber, dotted
_AXIS_GRID = "#c0c4c3"             # CHART_CANVAS.grid (light bg)
_AXIS_TICK = "#707372"             # CHART_CANVAS.label


def _resolve_size(size: SizePreset | tuple[int, int] | None) -> tuple[int, int]:
    if size is None:
        return SIZE_PRESETS["medium"]
    if isinstance(size, str):
        return SIZE_PRESETS.get(size, SIZE_PRESETS["medium"])
    return size


def _sigmoid_xy(bottom: float, top: float, fv: float, hill: float,
                lo_log: float, hi_log: float, n: int = 80) -> tuple[list[float], list[float]]:
    """Sample the 4PL sigmoid across log10(dose) from lo_log..hi_log."""
    if fv is None or fv <= 0:
        return [], []
    lf = math.log10(fv)
    step = (hi_log - lo_log) / max(1, n - 1)
    xs_log = [lo_log + i * step for i in range(n)]
    ys = [bottom + (top - bottom) / (1 + 10 ** ((lf - x) * hill)) for x in xs_log]
    return [10 ** x for x in xs_log], ys


def _xrange_for(curve_snapshot: dict) -> tuple[float, float]:
    """One-decade padding past raw-data extremes; falls back to FV*0.01..FV*100.

    Folds in additional_curves' raw_data + fitted_values so an aggregate
    overlay isn't truncated when a sibling sits outside the rep's range.
    Mirrors FE ``computeXRange``.
    """
    xs: list[float] = []
    for p in curve_snapshot.get("data_points") or []:
        d = p.get("dose")
        if isinstance(d, (int, float)) and d > 0:
            xs.append(float(d))
    for ac in curve_snapshot.get("additional_curves") or []:
        fv = ac.get("fitted_value")
        if isinstance(fv, (int, float)) and fv > 0:
            xs.append(float(fv))
        for p in ac.get("raw_data") or []:
            d = p.get("x") if "x" in p else p.get("dose")
            if isinstance(d, (int, float)) and d > 0:
                xs.append(float(d))
    if xs:
        mn, mx = min(xs), max(xs)
        return max(mn * 0.1, 1e-12), mx * 10
    fit = curve_snapshot.get("fit") or {}
    fv = fit.get("ec50") or fit.get("fitted_value") or 1.0
    return max(fv * 0.01, 1e-12), fv * 100


def av_to_sparkline_snapshot(av: dict) -> dict | None:
    """Build a sparkline-renderer-compatible snapshot dict from an ActivityValue dict.

    ``ActivityValue`` (via ``dataclasses.asdict``) carries raw_data,
    curve_params, value (the fitted primary intercept), curve_class via
    curve_params, plus aggregate-mode extras (``additional_curves`` +
    ``aggregate``).  This helper maps those fields onto the snapshot
    shape consumed by :func:`render_sparkline_png`.

    Returns None when there is not enough shape information to render
    (e.g. a readout_data source, or a curve missing fit params).
    """
    if not av:
        return None
    curve_params = av.get("curve_params") or {}
    top = curve_params.get("top")
    bottom = curve_params.get("bottom")
    hill_slope = curve_params.get("hill_slope")
    if top is None or bottom is None or hill_slope is None:
        return None

    raw_data = av.get("raw_data") or []
    data_points = [
        {"dose": pt["x"], "response": pt["y"], **{k: v for k, v in pt.items() if k not in ("x", "y")}}
        for pt in raw_data
        if isinstance(pt, dict) and "x" in pt and "y" in pt
    ]

    ec50 = av.get("value")
    fit: dict = {"bottom": bottom, "top": top, "hill_slope": hill_slope}
    if ec50 is not None:
        fit["ec50"] = ec50

    return {
        "data_points": data_points,
        "fit": fit,
        "curve_class": curve_params.get("curve_class"),
        "additional_curves": av.get("additional_curves") or [],
        "aggregate": av.get("aggregate"),
    }


def render_sparkline_png(
    curve_snapshot: dict | None,
    *,
    size: SizePreset | tuple[int, int] | None = None,
) -> bytes | None:
    """Render a dose-response sparkline as PNG bytes.

    ``curve_snapshot`` shape (built by ``_av_to_sparkline_snapshot`` in the
    XLSX renderer or directly from a ``CurveSnapshot`` in the PDF renderer):

      {
        "data_points": [{"dose": float, "response": float, ...}, ...],
        "fit": {"bottom": float, "top": float, "ec50": float, "hill_slope": float},
        "curve_class": "full" | "partial" | "inactive" | None,
        "additional_curves": [
          {"fitted_value": float, "top": float, "bottom": float,
           "hill_slope": float, "curve_class": str | None,
           "raw_data": [{"x": float, "y": float}, ...]} ...
        ],
        "aggregate": {"marker_x": float, "marker_label": str, "unit": str} | None,
      }

    Returns None if there's nothing usable to draw (no points + no fit).
    """
    if not curve_snapshot:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import LogLocator, FixedLocator

    width, height = _resolve_size(size)
    points = curve_snapshot.get("data_points") or []
    fit = curve_snapshot.get("fit") or {}
    inactive = curve_snapshot.get("curve_class") == "inactive"
    additional = curve_snapshot.get("additional_curves") or []
    aggregate = curve_snapshot.get("aggregate")

    has_points = any(isinstance(p.get("dose"), (int, float)) and p["dose"] > 0
                     for p in points)
    has_fit = all(k in fit for k in ("top", "bottom", "ec50", "hill_slope"))
    if not has_points and not has_fit:
        return None

    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
    fig.patch.set_alpha(0)
    ax.set_facecolor("white")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(_AXIS_GRID)
        ax.spines[spine].set_linewidth(0.8)

    # X-axis: log scale with decade major ticks.
    lo, hi = _xrange_for(curve_snapshot)
    ax.set_xscale("log")
    ax.set_xlim(lo, hi)
    ax.xaxis.set_major_locator(LogLocator(base=10.0, numticks=8))
    ax.xaxis.set_minor_locator(LogLocator(base=10.0, subs=tuple(range(2, 10)), numticks=80))
    ax.tick_params(axis="x", which="major", labelsize=7, colors=_AXIS_TICK,
                   length=3, width=0.6)
    ax.tick_params(axis="x", which="minor", length=1.5, width=0.4,
                   colors=_AXIS_GRID)

    # Y-axis: 0/50/100 fixed ticks, drawn even when data falls outside.
    ax.yaxis.set_major_locator(FixedLocator([0, 50, 100]))
    ax.tick_params(axis="y", labelsize=7, colors=_AXIS_TICK,
                   length=3, width=0.6)
    ax.set_ylim(-15, 115)

    ax.grid(True, which="major", color=_AXIS_GRID, linewidth=0.4, alpha=0.6)

    # Raw data markers (always drawn when present, both for active and
    # inactive curves — matches FE).
    marker_color = _INACTIVE_MARKER_COLOR if inactive else _MARKER_COLOR
    if has_points:
        xs = [float(p["dose"]) for p in points if isinstance(p.get("dose"), (int, float)) and p["dose"] > 0]
        ys = [float(p.get("response", 0)) for p in points if isinstance(p.get("dose"), (int, float)) and p["dose"] > 0]
        ax.scatter(xs, ys, s=10, color=marker_color, zorder=3, edgecolors="none")

    # Aggregate-mode sibling sigmoids (muted dashed) — drawn under the
    # primary so the primary stays prominent. Mirrors FE additional_curves.
    if aggregate and additional:
        for ac in additional:
            if ac.get("curve_class") == "inactive":
                continue
            fv = ac.get("fitted_value")
            if not isinstance(fv, (int, float)) or fv <= 0:
                continue
            sx, sy = _sigmoid_xy(
                ac.get("bottom", 0.0),
                ac.get("top", 100.0),
                float(fv),
                ac.get("hill_slope", 1.0),
                math.log10(lo), math.log10(hi),
            )
            if sx:
                ax.plot(sx, sy, color=_FIT_COLOR, linewidth=0.8,
                        linestyle=(0, (2, 2)), alpha=0.35, zorder=1)

    # Primary fit (only drawn when not inactive — matches FE showFit).
    if not inactive and has_fit:
        sx, sy = _sigmoid_xy(
            float(fit["bottom"]),
            float(fit["top"]),
            float(fit["ec50"]),
            float(fit["hill_slope"]),
            math.log10(lo), math.log10(hi),
        )
        if sx:
            ax.plot(sx, sy, color=_FIT_COLOR, linewidth=1.6, zorder=2)

    # Reference line:
    #   - Aggregate mode: solid amber at aggregate.marker_x (suppresses
    #     the per-curve dash — per-run fitted_values don't equal the
    #     aggregated cell value).
    #   - Active single-curve: dotted amber at fitted_value.
    #   - Inactive: no reference line.
    if aggregate and isinstance(aggregate.get("marker_x"), (int, float)):
        mx = float(aggregate["marker_x"])
        if mx > 0:
            ax.axvline(mx, color=_AGGREGATE_LINE, linewidth=1.4, alpha=0.95, zorder=2)
    elif not inactive and has_fit:
        fv = float(fit["ec50"])
        if fv > 0:
            ax.axvline(fv, color=_INTERCEPT_LINE, linewidth=0.9,
                       linestyle=(0, (1.5, 1.5)), alpha=0.7, zorder=2)

    fig.tight_layout(pad=0.3)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.06,
                facecolor="white")
    plt.close(fig)
    return buf.getvalue()
