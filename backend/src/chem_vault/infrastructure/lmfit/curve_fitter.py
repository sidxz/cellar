"""LmfitCurveFitter — 4-Parameter Logistic (Hill) curve fitting via lmfit.

Implements the CurveFittingService protocol from the domain layer.
Hill equation: response = bottom + (top - bottom) / (1 + (c / EC50)^|hill_slope|)

The hill_slope is always kept positive internally (absolute value), then negated
in the output for inhibition assays (IC50, KI, LD50, TD50).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import lmfit
import numpy as np
from returns.result import Failure, Result, Success

from chem_vault.domain.screening_assay.curve_fitting import (
    ConcentrationResponsePoint,
    FittedCurveResult,
)
from chem_vault.domain.screening_assay.enums import (
    CurveClass,
    CurveType,
    HillSlopeConstraint,
)
from chem_vault.domain.shared.errors import DomainError, ValidationError

if TYPE_CHECKING:
    from chem_vault.domain.screening_assay.dose_response_config import DoseResponseConfig

# Assay types where the Hill slope is conventionally reported as negative
# (response decreases as concentration increases)
_INHIBITION_CURVE_TYPES = {CurveType.IC50, CurveType.KI, CurveType.LD50, CurveType.TD50}

# Thresholds for curve classification
_INACTIVE_THRESHOLD = 30.0  # max response < 30% → inactive
_FULL_R2_MIN = 0.8
_FULL_TOP_MIN = 80.0
_FULL_BOTTOM_MAX = 20.0
_PARTIAL_R2_MIN = 0.6
_MIN_FITTING_POINTS = 4


def _hill_equation(concentration: np.ndarray, bottom: float, top: float, ec50: float, abs_hill: float) -> np.ndarray:
    """4PL Hill equation. Uses absolute hill slope — always positive internally."""
    return bottom + (top - bottom) / (1.0 + (concentration / ec50) ** abs_hill)


class LmfitCurveFitter:
    """Concrete 4PL curve fitter backed by lmfit.

    Satisfies the CurveFittingService Protocol from the domain layer via structural
    subtyping — no import of the protocol in this file needed.
    """

    def fit(
        self,
        points: list[ConcentrationResponsePoint],
        config: DoseResponseConfig,
    ) -> Result[FittedCurveResult, DomainError]:
        """Fit a 4-Parameter Logistic (Hill) curve to the provided data points.

        Returns Success[FittedCurveResult] or Failure[ValidationError].
        """
        active_points = [p for p in points if not p.is_excluded]
        excluded_points = [p for p in points if p.is_excluded]

        # --- Validate minimum point count ---
        if len(active_points) < _MIN_FITTING_POINTS:
            return Failure(
                ValidationError(
                    f"Curve fitting requires at least 4 non-excluded data points; "
                    f"got {len(active_points)}"
                )
            )

        concentrations = np.array([p.concentration for p in active_points], dtype=float)
        responses = np.array([p.response for p in active_points], dtype=float)

        # --- Build raw_data / excluded_data output lists ---
        raw_data = [{"concentration": p.concentration, "response": p.response} for p in active_points]
        excluded_data = [{"concentration": p.concentration, "response": p.response} for p in excluded_points]

        # --- Inactive compound fast-path ---
        max_response = float(np.max(responses))
        if max_response < _INACTIVE_THRESHOLD:
            return Success(
                FittedCurveResult(
                    fitted_value=0.0,
                    hill_slope=0.0,
                    top=float(np.max(responses)),
                    bottom=float(np.min(responses)),
                    r_squared=0.0,
                    confidence_interval_low=0.0,
                    confidence_interval_high=0.0,
                    curve_class=CurveClass.INACTIVE,
                    num_points=len(active_points),
                    raw_data=raw_data,
                    excluded_points=excluded_data,
                )
            )

        # --- Initial parameter estimates ---
        top_init = float(np.max(responses))
        bottom_init = float(np.min(responses))
        # Geometric mean of mid-range concentrations as EC50 estimate
        sorted_concs = np.sort(concentrations)
        mid_concs = sorted_concs[len(sorted_concs) // 4 : 3 * len(sorted_concs) // 4]
        if len(mid_concs) == 0:
            mid_concs = sorted_concs
        positive_mids = mid_concs[mid_concs > 0]
        if len(positive_mids) == 0:
            positive_mids = sorted_concs[sorted_concs > 0]
        ec50_init = float(math.exp(np.mean(np.log(positive_mids)))) if len(positive_mids) > 0 else 1.0
        abs_hill_init = 1.0

        # --- Build lmfit model and parameters ---
        model = lmfit.Model(_hill_equation)
        params = model.make_params(
            bottom=bottom_init,
            top=top_init,
            ec50=ec50_init,
            abs_hill=abs_hill_init,
        )

        # EC50 must be positive
        params["ec50"].set(min=1e-12)

        # Apply hill slope constraints
        constraint = config.hill_slope_constraint
        if constraint == HillSlopeConstraint.FIXED_AT_ONE:
            params["abs_hill"].set(value=1.0, vary=False)
        elif constraint in (HillSlopeConstraint.POSITIVE_ONLY, HillSlopeConstraint.NEGATIVE_ONLY):
            # Both cases: internal abs_hill is always positive; sign is applied at output time
            params["abs_hill"].set(min=0.1, max=10.0)
        else:
            # UNCONSTRAINED — keep abs_hill positive but allow wide range
            params["abs_hill"].set(min=0.01, max=20.0)

        # Apply top / bottom constraints from config
        if config.top_constraint is not None:
            params["top"].set(value=config.top_constraint, vary=False)
        if config.bottom_constraint is not None:
            params["bottom"].set(value=config.bottom_constraint, vary=False)

        # --- Run fitting ---
        try:
            fit_result = model.fit(responses, params, concentration=concentrations, method="leastsq")
        except Exception as exc:
            return Failure(ValidationError(f"Curve fitting did not converge: {exc}"))

        if not fit_result.success and not fit_result.errorbars:
            return Failure(ValidationError("Curve fitting did not converge"))

        best = fit_result.params
        fitted_top = float(best["top"].value)
        fitted_bottom = float(best["bottom"].value)
        fitted_ec50 = float(best["ec50"].value)
        fitted_abs_hill = float(best["abs_hill"].value)

        # --- Apply sign convention for hill_slope output ---
        is_inhibition = config.curve_type in _INHIBITION_CURVE_TYPES
        if is_inhibition:
            hill_slope_out = -abs(fitted_abs_hill)
        else:
            hill_slope_out = abs(fitted_abs_hill)

        # --- R² ---
        predicted = _hill_equation(concentrations, fitted_bottom, fitted_top, fitted_ec50, fitted_abs_hill)
        ss_res = float(np.sum((responses - predicted) ** 2))
        ss_tot = float(np.sum((responses - np.mean(responses)) ** 2))
        r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

        # --- Confidence intervals (EC50 ± 1.96 * stderr) ---
        ec50_stderr = best["ec50"].stderr
        if ec50_stderr is not None and np.isfinite(ec50_stderr) and ec50_stderr > 0:
            ci_low = fitted_ec50 - 1.96 * ec50_stderr
            ci_high = fitted_ec50 + 1.96 * ec50_stderr
        else:
            # Fallback ±30%
            ci_low = fitted_ec50 * 0.70
            ci_high = fitted_ec50 * 1.30

        # Ensure CI_low > 0
        ci_low = max(ci_low, 1e-12)

        # --- Curve classification ---
        curve_class = _classify_curve(
            concentrations=concentrations,
            responses=responses,
            predicted=predicted,
            r_squared=r_squared,
            fitted_top=fitted_top,
            fitted_bottom=fitted_bottom,
        )

        return Success(
            FittedCurveResult(
                fitted_value=fitted_ec50,
                hill_slope=hill_slope_out,
                top=fitted_top,
                bottom=fitted_bottom,
                r_squared=r_squared,
                confidence_interval_low=ci_low,
                confidence_interval_high=ci_high,
                curve_class=curve_class,
                num_points=len(active_points),
                raw_data=raw_data,
                excluded_points=excluded_data,
            )
        )


def _classify_curve(
    *,
    concentrations: np.ndarray,
    responses: np.ndarray,
    predicted: np.ndarray,
    r_squared: float,
    fitted_top: float,
    fitted_bottom: float,
) -> CurveClass:
    """Classify fitted curve into FULL, PARTIAL, BELL_SHAPED, or INACTIVE.

    Classification logic (applied in order):
    1. INACTIVE  — max response < 30%
    2. BELL_SHAPED — non-monotonic (detected on predicted curve sorted by conc)
    3. FULL      — R² ≥ 0.8 AND fitted_top ≥ 80 AND fitted_bottom ≤ 20
    4. PARTIAL   — R² ≥ 0.6 (everything else with reasonable fit)
    5. INACTIVE  — poor fit fallback
    """
    max_response = float(np.max(responses))
    if max_response < _INACTIVE_THRESHOLD:
        return CurveClass.INACTIVE

    # Check monotonicity on the *predicted* values sorted by concentration
    sort_idx = np.argsort(concentrations)
    sorted_pred = predicted[sort_idx]
    diffs = np.diff(sorted_pred)
    is_monotonic = bool(np.all(diffs <= 0) or np.all(diffs >= 0))

    if not is_monotonic:
        return CurveClass.BELL_SHAPED

    if (
        r_squared >= _FULL_R2_MIN
        and fitted_top >= _FULL_TOP_MIN
        and fitted_bottom <= _FULL_BOTTOM_MAX
    ):
        return CurveClass.FULL

    if r_squared >= _PARTIAL_R2_MIN:
        return CurveClass.PARTIAL

    return CurveClass.INACTIVE
