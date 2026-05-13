"""Screening & Assay application use cases."""

from __future__ import annotations


def _condense_raw_data(
    raw: list[dict],
) -> list[dict[str, float]]:
    """Convert raw_data JSONB [{concentration, response}] to [{x, y}].

    Handles both key conventions (concentration/response and x/y).
    Uses ``is not None`` checks to avoid dropping zero-value data points.
    """
    points: list[dict[str, float]] = []
    for pt in raw:
        conc = pt.get("concentration")
        if conc is None:
            conc = pt.get("x")
        resp = pt.get("response")
        if resp is None:
            resp = pt.get("y")
        if isinstance(conc, (int, float)) and isinstance(resp, (int, float)):
            points.append({"x": float(conc), "y": float(resp)})
    return points
