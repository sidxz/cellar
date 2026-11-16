"""Shared point-reconstruction helper for dose-response refit paths.

Both the commit path (``RefitDoseResponseCurve``) and the compute-only preview
path (``RefitDoseResponseCurvePreview``) must reconstruct the candidate
``ConcentrationResponsePoint`` list from a stored curve's ``raw_data`` +
``excluded_points`` blobs in EXACTLY the same way — otherwise the FE will see
a different fit on Save than during edit. This module is the single source of
truth for that reconstruction, and for the one order every point index of a
curve addresses.

Leading underscore = package-private; not part of the public application API.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from cellar.domain.screening_assay.curve_fitting import ConcentrationResponsePoint
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.excluded_point_detail import (
    ExcludedPointDetail,
    ExclusionSource,
)

CapturedPoint = tuple[float, float, ExcludedPointDetail | None]


def captured_set(
    raw_data: list[dict[str, Any]] | None, entries: list[ExcludedPointDetail] | None
) -> list[CapturedPoint]:
    """A curve's points in the one order every point index of the curve addresses.

    ``raw_data`` holds the points in the fit; an excluded entry is a point outside it (a
    suggestion — not excluded — is one of the raw_data points, so it is not added again).
    Stably sorted by dose, raw_data first: an entry's ``idx``, a client's
    ``excluded_indices`` and the editor's chart and point inventory all count positions here.
    """
    captured: list[CapturedPoint] = [
        (p["concentration"], p["response"], None) for p in raw_data or []
    ] + [
        (e.concentration, e.response, e)
        for e in entries or []
        if e.excluded and e.concentration is not None and e.response is not None
    ]
    captured.sort(key=lambda p: p[0])
    return captured


def is_well_flag(entry: ExcludedPointDetail | None) -> bool:
    """The point's well is flagged as an outlier on the run: it stays out of every fit."""
    return entry is not None and entry.source == ExclusionSource.WELL_FLAG and entry.excluded


def build_points_with_exclusions(
    curve: DoseResponseCurve, excluded_indices: list[int]
) -> list[ConcentrationResponsePoint]:
    """Reconstruct the captured set as fitter points, ``excluded_indices`` left out.

    A point of a well flagged as an outlier is left out whatever the indices say: only
    removing the flag on the plate brings it back.
    """
    excluded_set = set(excluded_indices)
    return [
        ConcentrationResponsePoint(
            concentration=c, response=r, is_excluded=i in excluded_set or is_well_flag(e)
        )
        for i, (c, r, e) in enumerate(captured_set(curve.raw_data, curve.excluded_points))
    ]


def with_captured_positions(
    raw_data: list[dict[str, Any]], entries: list[ExcludedPointDetail]
) -> list[ExcludedPointDetail]:
    """``entries`` with each ``idx`` set to its point's position in the captured set they
    form with ``raw_data``: an excluded entry is its own point, a suggestion names the
    raw_data point with its coordinates. An entry with no such point keeps its idx."""
    captured = captured_set(raw_data, entries)
    own = {id(e): k for k, (_, _, e) in enumerate(captured) if e is not None}
    raw: dict[tuple[float | None, float | None], int] = {}
    for k, (c, r, e) in enumerate(captured):
        if e is None:
            raw.setdefault((c, r), k)
    out = []
    for e in entries:
        k = own.get(id(e)) if e.excluded else raw.get((e.concentration, e.response))
        out.append(e if k is None else replace(e, idx=k))
    return out
