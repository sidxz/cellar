"""Dose-response curve fitting protocol and domain data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from returns.result import Result

from chem_vault.domain.screening_assay.dose_response_config import DoseResponseConfig
from chem_vault.domain.screening_assay.enums import CurveClass
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True)
class ConcentrationResponsePoint:
    """A single concentration-response measurement for curve fitting."""

    concentration: float
    response: float
    is_excluded: bool = False


@dataclass(frozen=True)
class FittedCurveResult:
    """Output of 4PL curve fitting — all parameters needed to create a DoseResponseCurve."""

    fitted_value: float
    hill_slope: float
    top: float
    bottom: float
    r_squared: float
    confidence_interval_low: float
    confidence_interval_high: float
    curve_class: CurveClass
    num_points: int
    raw_data: list[dict[str, Any]]
    excluded_points: list[dict[str, Any]] = field(default_factory=list)


@runtime_checkable
class CurveFittingService(Protocol):
    """Protocol for dose-response curve fitting — implemented by infrastructure layer."""

    def fit(
        self,
        points: list[ConcentrationResponsePoint],
        config: DoseResponseConfig,
    ) -> Result[FittedCurveResult, DomainError]: ...
