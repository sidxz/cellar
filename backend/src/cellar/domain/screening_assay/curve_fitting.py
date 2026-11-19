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
from cellar.domain.shared.aggregation_types import ValueQualifier
from cellar.domain.shared.errors import DomainError, ValidationError

# Fit-quality code for points left out of a fit because their dose is zero or negative (no
# place on a log-dose axis), suffixed with how many: ``"dose_zero_left_out:2"``.
DOSE_ZERO_LEFT_OUT = "dose_zero_left_out"


@dataclass(frozen=True)
class ConcentrationResponsePoint:
    """A single concentration-response measurement for curve fitting."""

    concentration: float
    response: float
    is_excluded: bool = False


@dataclass(frozen=True)
class ResponseScale:
    """The scale a fitted layer is read on: the response of no effect (``zero``) and of the
    full effect (``full``). The effect rises with the response when ``full > zero``.

    A curve whose plateaus show no transition is judged against it: a flat line at 95 % on a
    0-100 % scale is past its 50 % level at every dose. Layers with no such scale (raw
    signal, Z-score) pass none.
    """

    zero: float = 0.0
    full: float = 100.0

    def __post_init__(self) -> None:
        if self.full == self.zero:
            raise ValidationError("ResponseScale full must differ from zero")


@dataclass(frozen=True)
class InterceptValue:
    """One computed intercept derived from the same Hill fit, read against the tested doses.

    ``qualifier`` says how ``value`` (a concentration, linear space) reads:

    * ``=``: the fitted curve crosses the intercept's level at ``value``, inside the doses;
    * ``<``: it is past the level already at the lowest dose, ``value``;
    * ``>``: it has not reached the level at the highest dose, ``value``;
    * ``nd``: a flat curve whose band holds the level, so no crossing can be read from
      it; ``value`` is NaN.

    ``None`` marks an intercept stored before qualifiers existed: readers apply today's rules.
    ``at_bound`` is True exactly when the qualifier is ``>``, so readers that only know
    ``at_bound`` show "> highest dose" and never a wrong one.
    """

    spec: InterceptSpec
    value: float
    confidence_interval_low: float | None
    confidence_interval_high: float | None
    at_bound: bool = False
    qualifier: ValueQualifier | None = None


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
        scale: ResponseScale | None = None,
    ) -> Result[FittedCurveResult, DomainError]: ...
