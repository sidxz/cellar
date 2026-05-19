"""Dose-response curve fitting protocol and domain data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from returns.result import Result

from cellar.domain.screening_assay.dose_response_config import (
    DoseResponseConfig,
    InterceptSpec,
)
from cellar.domain.screening_assay.enums import CurveClass
from cellar.domain.screening_assay.outlier_suggestion import OutlierSuggestion
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True)
class ConcentrationResponsePoint:
    """A single concentration-response measurement for curve fitting."""

    concentration: float
    response: float
    is_excluded: bool = False


@dataclass(frozen=True)
class InterceptValue:
    """One computed intercept derived from the same Hill fit.

    ``value`` is the concentration in linear space (not log) at which the
    curve crosses the response threshold defined by ``spec``. ``at_bound``
    is True when the response threshold is outside ``[bottom, top]`` — the
    curve never reaches it; ``value`` is NaN in that case.
    """

    spec: InterceptSpec
    value: float
    confidence_interval_low: float | None
    confidence_interval_high: float | None
    at_bound: bool = False


@dataclass(frozen=True)
class FittedCurveResult:
    """Output of 4PL curve fitting — all parameters needed to create a DoseResponseCurve.

    ``fit_quality_warnings`` holds machine-readable codes flagged by the fitter
    when the result deserves a caveat — e.g. ``ec50_at_bound`` (the optimizer
    pushed EC50 against its bound, IC50 unreliable), ``ec50_outside_dose_range``
    (extrapolation), ``low_r_squared``. The frontend renders each as an amber
    badge on the curve summary.

    ``intercept_values`` are the per-spec results when the config asks for
    multiple intercepts (e.g. IC50 + IC90). The first entry's ``value``
    matches the headline ``fitted_value`` for back-compat.

    ``outlier_suggestions`` are auto-detected candidate outliers from the
    3σ pass. The fitter NEVER removes them silently — it only nominates them.
    The use-case layer decides what to persist (typically as
    ``ExcludedPointDetail`` with ``excluded=False``, which the FE renders
    as yellow-halo "suggested for exclusion" markers). Empty when
    ``config.outlier_sigma is None``.
    """

    fitted_value: float
    hill_slope: float
    top: float
    bottom: float
    r_squared: float
    # ``None`` when the fit hit a bound or stderr is unavailable / so wide it
    # would imply more than 10 decades of uncertainty — no meaningful CI to
    # report.
    confidence_interval_low: float | None
    confidence_interval_high: float | None
    curve_class: CurveClass
    num_points: int
    raw_data: list[dict[str, Any]]
    excluded_points: list[dict[str, Any]] = field(default_factory=list)
    fit_quality_warnings: list[str] = field(default_factory=list)
    intercept_values: tuple[InterceptValue, ...] = ()
    outlier_suggestions: tuple[OutlierSuggestion, ...] = ()


@runtime_checkable
class CurveFittingService(Protocol):
    """Protocol for dose-response curve fitting — implemented by infrastructure layer."""

    def fit(
        self,
        points: list[ConcentrationResponsePoint],
        config: DoseResponseConfig,
    ) -> Result[FittedCurveResult, DomainError]: ...
