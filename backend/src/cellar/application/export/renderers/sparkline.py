from __future__ import annotations
import io
import math


def render_sparkline_png(curve_snapshot: dict | None, *, width: int = 240, height: int = 120) -> bytes | None:
    """Render a small sigmoid + data-point sparkline as PNG bytes.

    Returns None if the snapshot has no usable fit / points (e.g. inactive
    curve in points-only mode — the renderer falls back to no image).

    Reuses the same convention as the FE `DoseResponseFigure`:
      - log10(dose) on the x-axis
      - response on the y-axis
      - 4PL fit traced only when curve_class != "inactive"
      - intercept dashed line at the snapshot's primary intercept
    """
    if not curve_snapshot:
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    points = curve_snapshot.get("data_points") or []
    fit = curve_snapshot.get("fit") or {}
    inactive = curve_snapshot.get("curve_class") == "inactive"

    if not points and not fit:
        return None

    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    xs = [math.log10(p["dose"]) for p in points if p.get("dose", 0) > 0]
    ys = [p["response"] for p in points if p.get("dose", 0) > 0]
    if xs:
        ax.scatter(xs, ys, s=8, color="#1f77b4")

    if not inactive and fit:
        bottom = fit.get("bottom", 0)
        top = fit.get("top", 100)
        ec50 = fit.get("ec50", 1.0)
        hill = fit.get("hill_slope", 1.0)
        if ec50 > 0:
            xs_fit = [math.log10(ec50) + i * 0.1 for i in range(-30, 31)]
            ys_fit = [bottom + (top - bottom) / (1 + 10 ** ((math.log10(ec50) - x) * hill)) for x in xs_fit]
            ax.plot(xs_fit, ys_fit, color="#1f77b4", linewidth=1.0)
            ax.axvline(math.log10(ec50), color="#888", linestyle="--", linewidth=0.6)

    ax.set_xticks([])
    ax.set_yticks([])
    buf = io.BytesIO()
    fig.tight_layout(pad=0)
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    return buf.getvalue()
