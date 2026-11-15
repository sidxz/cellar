"""The run report's figures, as vector SVG: the traces with the windows marked,
and each window's shift plot (shift-plot.tsx), drawn in the page's colours."""

from __future__ import annotations

import io

from cellar.application.export.run_report import RunReport, RunSignal, RunWindow

_REFERENCE = "#6d5bd0"  # the Traces tab's reference violet
_UP, _DOWN = "#3b82f6", "#ef4444"  # shift-figure.ts: a hit is blue up, red down
_NEUTRAL = "#a1a1aa"
_GRID = "#e4e4e7"
_TICK = "#71717a"


def traces_svg(report: RunReport) -> str | None:
    """Every position's derivative of the analysis signal (the measured
    signal when there is none): references violet, hits blue, the rest grey,
    each window shaded with its reference Tm dashed."""
    signal = _analysis_signal(report)
    if signal is None or not signal.traces:
        return None
    fig, ax = _axes(9.6, 3.2)
    order = sorted(signal.traces, key=lambda t: (t.role == "reference", bool(t.hit)))
    for t in order:  # references and hits drawn last, on top
        if t.role == "reference":
            ax.plot(t.x, t.y, color=_REFERENCE, linewidth=1.6, zorder=3)
        elif t.hit:
            ax.plot(t.x, t.y, color=_UP, linewidth=1.0, zorder=2)
        else:
            ax.plot(t.x, t.y, color=_NEUTRAL, linewidth=0.6, alpha=0.7, zorder=1)
    for i, w in enumerate(report.windows):
        # Alternating shades, so neighbouring windows read as two.
        ax.axvspan(w.low, w.high, color=("#f4f4f5", "#e9e9ec")[i % 2], zorder=0)
        ax.annotate(
            w.name,
            xy=(w.low, 1),
            xycoords=("data", "axes fraction"),
            xytext=(3, -10),
            textcoords="offset points",
            fontsize=7,
            color=_TICK,
        )
        if w.reference_tm is not None:
            ax.axvline(w.reference_tm, color=_REFERENCE, linewidth=0.8, linestyle=(0, (3, 2)))
    ax.set_xlabel(signal.x_label, fontsize=8, color=_TICK)
    ax.set_ylabel(signal.y_label, fontsize=8, color=_TICK)
    return _svg(fig)


def shift_svg(report: RunReport, window: RunWindow) -> str | None:
    """Each sample's ΔTm in a window, smallest first, the rule's band or line and
    the zero line drawn; a hit is blue up or red down, the rest grey."""
    rows = [r for r in report.rows if r.role == "sample" and _delta(r, window.name) is not None]
    if not rows:
        return None
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.sample] = counts.get(r.sample, 0) + 1
    points = sorted(
        (
            (
                _delta(r, window.name),
                f"{r.sample} · {r.position}" if counts[r.sample] > 1 else r.sample,
                r.hit,
            )
            for r in rows
        ),
        key=lambda p: p[0],
    )
    fig, ax = _axes(6.4, max(1.6, 0.2 * len(points) + 0.7))
    if window.band:
        ax.axvspan(*window.band, color="#f4f4f5", zorder=0)
    if window.line is not None:
        ax.axvline(window.line, color=_TICK, linewidth=0.8, linestyle=(0, (3, 2)))
    ax.axvline(0, color=_TICK, linewidth=0.8)
    ys = range(len(points))
    colours = [
        (_UP if d > 0 else _DOWN if d < 0 else _NEUTRAL) if hit else _NEUTRAL
        for d, _, hit in points
    ]
    ax.scatter([d for d, _, _ in points], list(ys), s=18, color=colours, zorder=3)
    ax.set_yticks(list(ys), [label for _, label, _ in points], fontsize=7)
    ax.set_ylim(-0.7, len(points) - 0.3)
    ax.set_xlabel("ΔTm (°C)", fontsize=8, color=_TICK)
    return _svg(fig)


def _delta(row, window: str) -> float | None:
    cell = row.cells.get(window)
    return cell.delta_tm if cell else None


def _analysis_signal(report: RunReport) -> RunSignal | None:
    label = report.analysis_signal
    for view in ("derivative", "measured"):
        for s in report.signals:
            if s.view == view and (label is None or s.label == label):
                return s
    return report.signals[0] if report.signals else None


def _axes(width_in: float, height_in: float):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=100)
    ax.set_facecolor("white")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(_GRID)
    ax.tick_params(labelsize=7, colors=_TICK, length=3, width=0.6)
    ax.grid(True, color=_GRID, linewidth=0.5)
    return fig, ax


def _svg(fig) -> str:
    import matplotlib.pyplot as plt

    fig.tight_layout(pad=0.4)
    buf = io.StringIO()
    fig.savefig(buf, format="svg", facecolor="white")
    plt.close(fig)
    return buf.getvalue()
