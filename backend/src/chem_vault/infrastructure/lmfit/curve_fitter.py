"""LmfitCurveFitter — 4-Parameter Logistic (Hill) curve fitting via lmfit.

Implements the CurveFittingService protocol from the domain layer using the
industry-standard Prism parametrization:

    y = bottom + (top - bottom) / (1 + 10^((logEC50 - log(c)) * hill))

Conventions (match GraphPad Prism / CDD):
- ``top`` and ``bottom`` are the upper and lower plateaus on the Y axis,
  independent of curve direction.
- ``hill`` is signed: positive for rising curves (response increases with
  dose, e.g. % inhibition vs inhibitor concentration), negative for falling.
- EC50 is fit in log10 space for numerical stability across multi-decade
  dose ranges.

Output ``hill_slope`` carries the signed value directly; the legacy
"flip-sign-for-inhibition" hack is gone.
"""

from __future__ import annotations

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
    HillSlopeConstraint,
)
from chem_vault.domain.shared.errors import DomainError, ValidationError

if TYPE_CHECKING:
    from chem_vault.domain.screening_assay.dose_response_config import DoseResponseConfig


# Thresholds for curve classification
_INACTIVE_THRESHOLD = 30.0  # max response < 30% → inactive (skipped when constraints are set)
_FULL_R2_MIN = 0.8
_FULL_TOP_MIN = 80.0
_FULL_BOTTOM_MAX = 20.0
_PARTIAL_R2_MIN = 0.6
_MIN_FITTING_POINTS = 4

# Outlier detection thresholds
_MIN_POINTS_FOR_OUTLIER_DETECTION = 6   # need at least 6 points to run 3σ detection
_OUTLIER_SIGMA = 3.0                    # flag residuals > 3 * SD

# Bound-detection epsilon for log_ec50 (in log10 units)
_BOUND_EPSILON_LOG10 = 0.05


def _hill_equation(
    log_c: np.ndarray, top: float, bottom: float, log_ec50: float, hill: float
) -> np.ndarray:
    """Industry-standard 4PL (Prism convention).

    Top and bottom are the upper and lower plateaus on the Y axis,
    independent of curve direction. Hill is signed.

    The exponent is clipped to ±300 before ``10**`` to prevent benign
    numpy overflow warnings during optimizer probes deep in the bound region;
    the result there is asymptotically top or bottom either way.
    """
    exponent = np.clip((log_ec50 - log_c) * hill, -300.0, 300.0)
    return bottom + (top - bottom) / (1.0 + 10.0 ** exponent)


def _detect_outliers(residuals: np.ndarray, sigma: float = 3.0) -> np.ndarray:
    """Single-outlier leave-one-out (Grubbs-like) test.

    For the point with the largest absolute residual, compute the SD of the
    remaining n-1 residuals. If the candidate's residual exceeds ``sigma``
    times that SD, it is flagged.
    """
    n = len(residuals)
    if n < 2:  # pragma: no cover
        return np.zeros(n, dtype=bool)

    abs_res = np.abs(residuals)
    max_idx = int(np.argmax(abs_res))
    others = np.delete(residuals, max_idx)
    sd_others = float(np.std(others, ddof=1))

    mask = np.zeros(n, dtype=bool)
    if sd_others > 0 and abs_res[max_idx] > sigma * sd_others:
        mask[max_idx] = True
    return mask


class LmfitCurveFitter:
    """Concrete 4PL curve fitter backed by lmfit (Prism parametrization)."""

    def fit(
        self,
        points: list[ConcentrationResponsePoint],
        config: DoseResponseConfig,
    ) -> Result[FittedCurveResult, DomainError]:
        """Fit a direction-agnostic 4PL curve to the provided data points."""
        active_points = [p for p in points if not p.is_excluded]
        excluded_points = [p for p in points if p.is_excluded]

        if len(active_points) < _MIN_FITTING_POINTS:
            return Failure(
                ValidationError(
                    f"Curve fitting requires at least 4 non-excluded data points; "
                    f"got {len(active_points)}"
                )
            )

        concentrations = np.array([p.concentration for p in active_points], dtype=float)
        responses = np.array([p.response for p in active_points], dtype=float)

        # All concentrations must be positive (we fit in log space).
        if not np.all(concentrations > 0):
            return Failure(
                ValidationError(
                    "All concentrations must be > 0 for log-space dose-response fitting"
                )
            )

        raw_data = [
            {"concentration": p.concentration, "response": p.response}
            for p in active_points
        ]
        excluded_data = [
            {"concentration": p.concentration, "response": p.response}
            for p in excluded_points
        ]

        # ──────────────────────────────────────────────────────────────────
        # INACTIVE fast-path — skipped when the user set any explicit
        # constraint (the constrained fit still deserves a chance).
        # ──────────────────────────────────────────────────────────────────
        max_response = float(np.max(responses))
        has_constraints = (
            config.top_constraint is not None
            or config.bottom_constraint is not None
            or config.hill_slope_constraint != HillSlopeConstraint.UNCONSTRAINED
            or config.top_constraint_min is not None
            or config.top_constraint_max is not None
            or config.bottom_constraint_min is not None
            or config.bottom_constraint_max is not None
            or config.hill_slope_min is not None
            or config.hill_slope_max is not None
        )
        if max_response < _INACTIVE_THRESHOLD and not has_constraints:
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
                    fit_quality_warnings=[],
                )
            )

        log_concentrations = np.log10(concentrations)

        # ──────────────────────────────────────────────────────────────────
        # First-pass fit
        # ──────────────────────────────────────────────────────────────────
        params, log_ec50_min, log_ec50_max = _build_params(
            log_concentrations, responses, config
        )

        try:
            fit_result = lmfit.Model(_hill_equation).fit(
                responses, params, log_c=log_concentrations, method="leastsq"
            )
        except Exception as exc:
            return Failure(ValidationError(f"Curve fitting did not converge: {exc}"))

        if not fit_result.success and not fit_result.errorbars:
            return Failure(ValidationError("Curve fitting did not converge"))

        best = fit_result.params
        fitted_top = float(best["top"].value)
        fitted_bottom = float(best["bottom"].value)
        fitted_log_ec50 = float(best["log_ec50"].value)
        fitted_hill = float(best["hill"].value)
        log_ec50_stderr = best["log_ec50"].stderr

        predicted = _hill_equation(
            log_concentrations, fitted_top, fitted_bottom, fitted_log_ec50, fitted_hill
        )
        r_squared = _r_squared(responses, predicted)

        # ──────────────────────────────────────────────────────────────────
        # Outlier detection + second-pass refit on clean subset.
        # Threshold comes from the protocol's ``outlier_sigma`` (default 3.0,
        # CDD-equivalent). ``None`` disables auto-detection.
        # ──────────────────────────────────────────────────────────────────
        if (
            config.outlier_sigma is not None
            and len(active_points) >= _MIN_POINTS_FOR_OUTLIER_DETECTION
        ):
            residuals = responses - predicted
            outlier_mask = _detect_outliers(residuals, sigma=config.outlier_sigma)

            if np.any(outlier_mask):
                clean_log_c = log_concentrations[~outlier_mask]
                clean_responses = responses[~outlier_mask]

                if len(clean_log_c) >= _MIN_FITTING_POINTS:
                    params2, log_ec50_min, log_ec50_max = _build_params(
                        clean_log_c, clean_responses, config
                    )
                    try:
                        fit_result2 = lmfit.Model(_hill_equation).fit(
                            clean_responses,
                            params2,
                            log_c=clean_log_c,
                            method="leastsq",
                        )
                        if fit_result2.success or fit_result2.errorbars:
                            best = fit_result2.params
                            fitted_top = float(best["top"].value)
                            fitted_bottom = float(best["bottom"].value)
                            fitted_log_ec50 = float(best["log_ec50"].value)
                            fitted_hill = float(best["hill"].value)
                            log_ec50_stderr = best["log_ec50"].stderr

                            predicted = _hill_equation(
                                clean_log_c,
                                fitted_top,
                                fitted_bottom,
                                fitted_log_ec50,
                                fitted_hill,
                            )
                            r_squared = _r_squared(clean_responses, predicted)

                            # Move outliers to excluded_data; rebuild raw_data
                            for i, is_outlier in enumerate(outlier_mask):
                                if is_outlier:
                                    excluded_data.append(
                                        {
                                            "concentration": float(active_points[i].concentration),
                                            "response": float(active_points[i].response),
                                            "reason": "auto_3sigma",
                                            "residual": float(residuals[i]),
                                        }
                                    )
                            raw_data = [
                                {
                                    "concentration": float(active_points[i].concentration),
                                    "response": float(active_points[i].response),
                                }
                                for i, is_outlier in enumerate(outlier_mask)
                                if not is_outlier
                            ]

                            # Update the working arrays for downstream classification
                            log_concentrations = clean_log_c
                            responses = clean_responses
                            concentrations = 10.0 ** clean_log_c
                    except Exception:
                        # Second-pass failed — keep first-pass results as-is.
                        pass

        # ──────────────────────────────────────────────────────────────────
        # Convert log_ec50 → ec50 and compute log-space CI
        # ──────────────────────────────────────────────────────────────────
        fitted_ec50 = float(10.0 ** fitted_log_ec50)
        if (
            log_ec50_stderr is not None
            and np.isfinite(log_ec50_stderr)
            and log_ec50_stderr > 0
        ):
            # Cap the half-width at 10 decades to avoid 10**huge overflow when
            # the fit hits a bound (lmfit can return absurd stderrs in that
            # regime). The matching ec50_at_bound warning still fires.
            half_width = min(1.96 * log_ec50_stderr, 10.0)
            ci_low = float(10.0 ** (fitted_log_ec50 - half_width))
            ci_high = float(10.0 ** (fitted_log_ec50 + half_width))
        else:
            # Fallback ±0.5 decades — better than ±30% linear when stderr is unavailable.
            ci_low = float(10.0 ** (fitted_log_ec50 - 0.5))
            ci_high = float(10.0 ** (fitted_log_ec50 + 0.5))

        # ──────────────────────────────────────────────────────────────────
        # Fit quality warnings
        # ──────────────────────────────────────────────────────────────────
        warnings: list[str] = []
        if (
            abs(fitted_log_ec50 - log_ec50_min) < _BOUND_EPSILON_LOG10
            or abs(log_ec50_max - fitted_log_ec50) < _BOUND_EPSILON_LOG10
        ):
            warnings.append("ec50_at_bound")
        log_min_c = float(np.min(log_concentrations))
        log_max_c = float(np.max(log_concentrations))
        if not (log_min_c <= fitted_log_ec50 <= log_max_c):
            warnings.append("ec50_outside_dose_range")
        if r_squared < 0.5:
            warnings.append("low_r_squared")

        curve_class = _classify_curve(
            responses=responses,
            predicted=predicted,
            r_squared=r_squared,
            fitted_top=fitted_top,
            fitted_bottom=fitted_bottom,
        )

        return Success(
            FittedCurveResult(
                fitted_value=fitted_ec50,
                hill_slope=fitted_hill,
                top=fitted_top,
                bottom=fitted_bottom,
                r_squared=r_squared,
                confidence_interval_low=ci_low,
                confidence_interval_high=ci_high,
                curve_class=curve_class,
                num_points=len(active_points) - len(
                    [e for e in excluded_data if e.get("reason") == "auto_3sigma"]
                ),
                raw_data=raw_data,
                excluded_points=excluded_data,
                fit_quality_warnings=warnings,
            )
        )


def _build_params(
    log_concentrations: np.ndarray,
    responses: np.ndarray,
    config: DoseResponseConfig,
) -> tuple[lmfit.Parameters, float, float]:
    """Build lmfit Parameters with direction-aware initial guesses, log-space
    EC50 bounds tied to the observed dose range, and Prism-style top/bottom/hill
    constraints from ``config``.

    Returns ``(params, log_ec50_min, log_ec50_max)`` so callers can detect
    whether the converged log_ec50 sits at a bound.
    """
    # Direction inference from data — average the lowest- and highest-concentration
    # quartiles to estimate plateau levels.
    sort_idx = np.argsort(log_concentrations)
    y_sorted = responses[sort_idx]
    n_tail = max(1, len(y_sorted) // 4)
    y_low_plateau = float(np.mean(y_sorted[:n_tail]))
    y_high_plateau = float(np.mean(y_sorted[-n_tail:]))

    is_rising = y_high_plateau > y_low_plateau
    top_init = y_high_plateau if is_rising else y_low_plateau
    bottom_init = y_low_plateau if is_rising else y_high_plateau
    hill_sign = 1.0 if is_rising else -1.0
    hill_init = hill_sign * 1.0

    log_min_c = float(np.min(log_concentrations))
    log_max_c = float(np.max(log_concentrations))
    log_range = max(log_max_c - log_min_c, 1.0)
    log_ec50_init = (log_min_c + log_max_c) / 2.0
    log_ec50_min = log_min_c - log_range
    log_ec50_max = log_max_c + log_range

    model = lmfit.Model(_hill_equation)
    params = model.make_params(
        top=top_init,
        bottom=bottom_init,
        log_ec50=log_ec50_init,
        hill=hill_init,
    )
    params["log_ec50"].set(value=log_ec50_init, min=log_ec50_min, max=log_ec50_max)

    # Hill slope: lock > explicit range > enum > free.
    constraint = config.hill_slope_constraint
    hill_has_range = (
        config.hill_slope_min is not None or config.hill_slope_max is not None
    )
    if constraint == HillSlopeConstraint.FIXED_AT_ONE:
        # "Magnitude exactly 1, sign matches data direction" — chemist's
        # natural "no cooperativity" Hill = 1.
        params["hill"].set(value=hill_sign * 1.0, vary=False)
    elif hill_has_range:
        # Explicit range overrides enum-implicit bounds. Cross-validation
        # against the enum already happened in DoseResponseConfig.
        h_min = config.hill_slope_min if config.hill_slope_min is not None else -20.0
        h_max = config.hill_slope_max if config.hill_slope_max is not None else 20.0
        params["hill"].set(
            value=_clamp(hill_init, h_min, h_max), min=h_min, max=h_max
        )
    elif constraint == HillSlopeConstraint.POSITIVE_ONLY:
        params["hill"].set(value=max(hill_init, 0.5), min=0.01, max=20.0)
    elif constraint == HillSlopeConstraint.NEGATIVE_ONLY:
        params["hill"].set(value=min(hill_init, -0.5), min=-20.0, max=-0.01)
    else:
        params["hill"].set(value=hill_init, min=-20.0, max=20.0)

    # Top: lock > range > free.
    if config.top_constraint is not None:
        params["top"].set(value=config.top_constraint, vary=False)
    elif config.top_constraint_min is not None or config.top_constraint_max is not None:
        t_min = (
            config.top_constraint_min
            if config.top_constraint_min is not None
            else -np.inf
        )
        t_max = (
            config.top_constraint_max
            if config.top_constraint_max is not None
            else np.inf
        )
        params["top"].set(
            value=_clamp(top_init, t_min, t_max), min=t_min, max=t_max
        )

    # Bottom: lock > range > free.
    if config.bottom_constraint is not None:
        params["bottom"].set(value=config.bottom_constraint, vary=False)
    elif (
        config.bottom_constraint_min is not None
        or config.bottom_constraint_max is not None
    ):
        b_min = (
            config.bottom_constraint_min
            if config.bottom_constraint_min is not None
            else -np.inf
        )
        b_max = (
            config.bottom_constraint_max
            if config.bottom_constraint_max is not None
            else np.inf
        )
        params["bottom"].set(
            value=_clamp(bottom_init, b_min, b_max), min=b_min, max=b_max
        )

    return params, log_ec50_min, log_ec50_max


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp ``value`` into ``[lo, hi]``. Either bound may be ±inf."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _r_squared(observed: np.ndarray, predicted: np.ndarray) -> float:
    ss_res = float(np.sum((observed - predicted) ** 2))
    ss_tot = float(np.sum((observed - np.mean(observed)) ** 2))
    if ss_tot <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - ss_res / ss_tot))


def _classify_curve(
    *,
    responses: np.ndarray,
    predicted: np.ndarray,
    r_squared: float,
    fitted_top: float,
    fitted_bottom: float,
) -> CurveClass:
    """Classify a fitted curve. FULL/PARTIAL thresholds assume a normalized
    (% inhibition / % activation / % control) Y axis; raw-signal protocols
    will land in PARTIAL by R² alone, which is acceptable until the
    classification refactor lands (Phase B)."""
    max_response = float(np.max(responses))
    if max_response < _INACTIVE_THRESHOLD:
        return CurveClass.INACTIVE

    # Bell-shaped detection on predicted curve; with the new Prism param this
    # is a single-direction sigmoid, so non-monotonicity is impossible from
    # the fit itself. Keep the check as a defensive fallback.
    if len(predicted) >= 3:
        diffs = np.diff(predicted)
        is_monotonic = bool(np.all(diffs <= 0) or np.all(diffs >= 0))
        if not is_monotonic:
            return CurveClass.BELL_SHAPED

    # FULL: clean fit AND chemist-bounded plateaus (works for % readouts;
    # raw-signal protocols won't hit this branch because top/bottom are
    # in raw units).
    if (
        r_squared >= _FULL_R2_MIN
        and fitted_top >= _FULL_TOP_MIN
        and fitted_bottom <= _FULL_BOTTOM_MAX
    ):
        return CurveClass.FULL

    if r_squared >= _PARTIAL_R2_MIN:
        return CurveClass.PARTIAL

    return CurveClass.INACTIVE
