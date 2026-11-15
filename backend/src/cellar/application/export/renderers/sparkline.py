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
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from cellar.application.export.row_streams.base import ColumnSpec

SizePreset = Literal["small", "medium", "large"]
# PNG for Excel, which embeds only bitmaps; SVG for the PDF, which keeps it vector.
ImageFormat = Literal["png", "svg"]

SIZE_PRESETS: dict[str, tuple[int, int]] = {
    "small": (240, 140),
    "medium": (320, 180),
    "large": (480, 260),
}

# Mirrors FE chart-colors.ts
_FIT_COLOR = "#18974c"  # CURVE_QUALITY_COLORS.full (green)
_INACTIVE_MARKER_COLOR = "#707372"  # CURVE_DEFAULT_COLOR (neutral)
_MARKER_COLOR = "#18974c"  # same as fit so points line up visually
_AGGREGATE_LINE = "#f49e17"  # CHART_COLORS.warning (amber)
_INTERCEPT_LINE = "#f49e17"  # same amber, dotted
_AXIS_GRID = "#c0c4c3"  # CHART_CANVAS.grid (light bg)
_AXIS_TICK = "#707372"  # CHART_CANVAS.label

# Mirrors @structflo/components dose-response colors.ts: an overlay colours its
# curves with GROUP_PALETTE's first MAX_OVERLAY_CURVES entries, in group order,
# and a split with more groups than that stays side by side.
MAX_OVERLAY_CURVES = 8
OVERLAY_COLORS = (
    "#3b6fb6",
    "#18974c",
    "#f49e17",
    "#d41645",
    "#734595",
    "#0891b2",
    "#db2777",
    "#65a30d",
)


def _resolve_size(size: SizePreset | tuple[int, int] | None) -> tuple[int, int]:
    if size is None:
        return SIZE_PRESETS["medium"]
    if isinstance(size, str):
        return SIZE_PRESETS.get(size, SIZE_PRESETS["medium"])
    return size


def _sigmoid_xy(
    bottom: float, top: float, fv: float, hill: float, lo_log: float, hi_log: float, n: int = 80
) -> tuple[list[float], list[float]]:
    """Sample the 4PL sigmoid across log10(dose) from lo_log..hi_log."""
    if fv is None or fv <= 0:
        return [], []
    lf = math.log10(fv)
    step = (hi_log - lo_log) / max(1, n - 1)
    xs_log = [lo_log + i * step for i in range(n)]
    ys = [bottom + (top - bottom) / (1 + 10 ** ((lf - x) * hill)) for x in xs_log]
    return [10**x for x in xs_log], ys


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
    shape consumed by :func:`render_sparkline`.

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
        {
            "dose": pt["x"],
            "response": pt["y"],
            **{k: v for k, v in pt.items() if k not in ("x", "y")},
        }
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


def render_sparkline(
    curve_snapshot: dict | None,
    *,
    size: SizePreset | tuple[int, int] | None = None,
    fmt: ImageFormat = "png",
) -> bytes | None:
    """Render a dose-response sparkline as PNG or SVG bytes.

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
    if not _drawable(curve_snapshot):
        return None
    fig, ax = _figure(size, *_xrange_for(curve_snapshot))
    _draw_curve(ax, curve_snapshot)
    return _save(fig, fmt)


def render_overlay(
    snapshots: list[dict | None],
    *,
    size: SizePreset | tuple[int, int] | None = None,
    fmt: ImageFormat = "png",
) -> bytes | None:
    """Every split group's curve on one axis, curve ``i`` in ``OVERLAY_COLORS[i]``
    (the colour on its group's header), so a group with no curve keeps its slot.
    Mirrors the FE ``DoseResponseOverlay`` at cell size: no legend, no labels."""
    drawn = [(i, s) for i, s in enumerate(snapshots) if _drawable(s)]
    if not drawn:
        return None
    ranges = [_xrange_for(s) for _, s in drawn]
    fig, ax = _figure(size, min(r[0] for r in ranges), max(r[1] for r in ranges))
    for i, snapshot in drawn:
        _draw_curve(ax, snapshot, color=OVERLAY_COLORS[i % MAX_OVERLAY_CURVES])
    return _save(fig, fmt)


def column_plot(
    column: ColumnSpec,
    activity: dict,
    *,
    size: SizePreset | tuple[int, int] | None = None,
    fmt: ImageFormat = "png",
) -> bytes | None:
    """The plot an ``image_curve`` column shows for one row's activity: an
    overlay of each group's curve, or the one curve of ``drc:<rd>[@group]``."""
    if column.overlay_of:
        return render_overlay(
            [av_to_sparkline_snapshot(activity.get(key)) for key in column.overlay_of],
            size=size,
            fmt=fmt,
        )
    parent_token = column.key.rsplit("::", 1)[0]
    snapshot = av_to_sparkline_snapshot(activity.get(parent_token))
    return render_sparkline(snapshot, size=size, fmt=fmt)


def _drawable(curve_snapshot: dict | None) -> bool:
    if not curve_snapshot:
        return False
    points = curve_snapshot.get("data_points") or []
    fit = curve_snapshot.get("fit") or {}
    has_points = any(isinstance(p.get("dose"), (int, float)) and p["dose"] > 0 for p in points)
    return has_points or all(k in fit for k in ("top", "bottom", "ec50", "hill_slope"))


def _figure(size: SizePreset | tuple[int, int] | None, lo: float, hi: float):
    """Axes styled like the FE chart: log10 x with decade ticks, y at 0/50/100."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, LogLocator

    width, height = _resolve_size(size)
    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
    fig.patch.set_alpha(0)
    ax.set_facecolor("white")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(_AXIS_GRID)
        ax.spines[spine].set_linewidth(0.8)

    # X-axis: log scale with decade major ticks.
    ax.set_xscale("log")
    ax.set_xlim(lo, hi)
    ax.xaxis.set_major_locator(LogLocator(base=10.0, numticks=8))
    ax.xaxis.set_minor_locator(LogLocator(base=10.0, subs=tuple(range(2, 10)), numticks=80))
    ax.tick_params(axis="x", which="major", labelsize=7, colors=_AXIS_TICK, length=3, width=0.6)
    ax.tick_params(axis="x", which="minor", length=1.5, width=0.4, colors=_AXIS_GRID)

    # Y-axis: 0/50/100 fixed ticks, drawn even when data falls outside.
    ax.yaxis.set_major_locator(FixedLocator([0, 50, 100]))
    ax.tick_params(axis="y", labelsize=7, colors=_AXIS_TICK, length=3, width=0.6)
    ax.set_ylim(-15, 115)

    ax.grid(True, which="major", color=_AXIS_GRID, linewidth=0.4, alpha=0.6)
    return fig, ax


def _draw_curve(ax, curve_snapshot: dict, *, color: str | None = None) -> None:
    """One curve's points, fit and reference line. ``color`` paints every mark
    of an overlaid curve, as the FE overlay does; alone, a curve keeps the
    quality colours."""
    lo, hi = ax.get_xlim()
    points = curve_snapshot.get("data_points") or []
    fit = curve_snapshot.get("fit") or {}
    inactive = curve_snapshot.get("curve_class") == "inactive"
    additional = curve_snapshot.get("additional_curves") or []
    aggregate = curve_snapshot.get("aggregate")
    has_fit = all(k in fit for k in ("top", "bottom", "ec50", "hill_slope"))

    # Raw data markers (always drawn when present, both for active and
    # inactive curves — matches FE).
    marker_color = color or (_INACTIVE_MARKER_COLOR if inactive else _MARKER_COLOR)
    doses = [p for p in points if isinstance(p.get("dose"), (int, float)) and p["dose"] > 0]
    if doses:
        xs = [float(p["dose"]) for p in doses]
        ys = [float(p.get("response", 0)) for p in doses]
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
                math.log10(lo),
                math.log10(hi),
            )
            if sx:
                ax.plot(
                    sx,
                    sy,
                    color=color or _FIT_COLOR,
                    linewidth=0.8,
                    linestyle=(0, (2, 2)),
                    alpha=0.35,
                    zorder=1,
                )

    # Primary fit (only drawn when not inactive — matches FE showFit).
    if not inactive and has_fit:
        sx, sy = _sigmoid_xy(
            float(fit["bottom"]),
            float(fit["top"]),
            float(fit["ec50"]),
            float(fit["hill_slope"]),
            math.log10(lo),
            math.log10(hi),
        )
        if sx:
            ax.plot(sx, sy, color=color or _FIT_COLOR, linewidth=1.6, zorder=2)

    # Reference line:
    #   - Aggregate mode: solid amber at aggregate.marker_x (suppresses
    #     the per-curve dash — per-run fitted_values don't equal the
    #     aggregated cell value).
    #   - Active single-curve: dotted amber at fitted_value.
    #   - Inactive: no reference line.
    if aggregate and isinstance(aggregate.get("marker_x"), (int, float)):
        mx = float(aggregate["marker_x"])
        if mx > 0:
            ax.axvline(mx, color=color or _AGGREGATE_LINE, linewidth=1.4, alpha=0.95, zorder=2)
    elif not inactive and has_fit:
        fv = float(fit["ec50"])
        if fv > 0:
            ax.axvline(
                fv,
                color=color or _INTERCEPT_LINE,
                linewidth=0.9,
                linestyle=(0, (1.5, 1.5)),
                alpha=0.7,
                zorder=2,
            )


def _save(fig, fmt: ImageFormat) -> bytes:
    import matplotlib.pyplot as plt

    fig.tight_layout(pad=0.3)
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt, bbox_inches="tight", pad_inches=0.06, facecolor="white")
    plt.close(fig)
    return buf.getvalue()
