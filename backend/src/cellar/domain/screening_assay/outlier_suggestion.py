"""Outlier suggestions emitted by the curve fitter.

A chemist accepts or rejects each suggestion in edit mode. The fitter never
removes these points silently; it only nominates candidates. The use-case
layer decides how to persist them (typically as ``ExcludedPointDetail`` with
``excluded=False``, which the FE renders as yellow-halo "suggested for
exclusion" markers).

This replaces the legacy "auto-3σ + silent refit" cascade where excluding
one point manually could trigger N more silent exclusions on every refit.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutlierSuggestion:
    """One auto-detected candidate outlier from the 3σ pass.

    ``idx`` is the position of the suggested point in the original list
    passed to ``CurveFittingService.fit``. Callers that pass a fully-active
    point list (e.g. initial-fit on a freshly imported run) can use this
    directly to index into ``raw_data``. Callers that mix excluded points
    into the input must remap if they care about post-active indexing.

    ``residual_z_full_sd``: ``|residual|`` divided by the sample standard
    deviation of ALL residuals (full-set, ``ddof=1``). Always positive.
    Note: this is a presentation-time severity hint; the leave-one-out
    test that flagged the point as a candidate uses a per-point SD and
    may report slightly different magnitudes for the same residual.
    """

    idx: int
    concentration: float
    response: float
    residual_z_full_sd: float
