"""Shared point-reconstruction helper for dose-response refit paths.

Both the commit path (``RefitDoseResponseCurve``) and the compute-only preview
path (``RefitDoseResponseCurvePreview``) must reconstruct the candidate
``ConcentrationResponsePoint`` list from a stored curve's ``raw_data`` +
``excluded_points`` blobs in EXACTLY the same way — otherwise the FE will see
a different fit on Save than during edit. This module is the single source of
truth for that reconstruction.

Leading underscore = package-private; not part of the public application API.
"""

from __future__ import annotations

from cellar.domain.screening_assay.curve_fitting import ConcentrationResponsePoint
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve


def build_points_with_exclusions(
    curve: DoseResponseCurve, excluded_indices: list[int]
) -> list[ConcentrationResponsePoint]:
    """Reconstruct ascending-by-concentration points from raw_data + flag exclusions.

    The points are sorted ASCENDING by concentration so that client-supplied
    ``excluded_indices`` line up with the UI's display order (low → high dose).

    Args:
        curve: The persisted curve aggregate whose ``raw_data`` +
            ``excluded_points`` blobs carry every original measurement.
        excluded_indices: Zero-based indices (into the ascending-by-dose
            ordering) the client wants excluded from the fit.

    Returns:
        A list of ``ConcentrationResponsePoint`` ready to feed to the fitter,
        with ``is_excluded=True`` set on positions matching ``excluded_indices``.
    """
    all_points_raw = list(curve.raw_data or []) + list(curve.excluded_points or [])
    all_points_raw.sort(key=lambda p: p.get("concentration", 0))

    excluded_set = set(excluded_indices)
    return [
        ConcentrationResponsePoint(
            concentration=pt["concentration"],
            response=pt["response"],
            is_excluded=(i in excluded_set),
        )
        for i, pt in enumerate(all_points_raw)
    ]
