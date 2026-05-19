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

import math

from cellar.domain.screening_assay.curve_fitting import (
    ConcentrationResponsePoint,
    FittedCurveResult,
    InterceptValue,
)
from cellar.domain.screening_assay.enums import (
    CurveClass,
    HillSlopeConstraint,
    InterceptBasis,
)
from cellar.domain.screening_assay.outlier_suggestion import OutlierSuggestion
from cellar.domain.shared.errors import DomainError, ValidationError

if TYPE_CHECKING:
    from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig


_MIN_FITTING_POINTS = 4

_MIN_POINTS_FOR_OUTLIER_DETECTION = 6  # need at least 6 points to run 3σ detection

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
    return bottom + (top - bottom) / (1.0 + 10.0**exponent)


def _detect_outliers(residuals: np.ndarray, sigma: float) -> np.ndarray:
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


def _hill_inverse_log10(
    *,
    top: float,
    bottom: float,
    log_ec50: float,
    hill: float,
    y_target: float,
) -> float | None:
    """Solve the 4PL for log10(x) at a given y_target.

    Returns ``log10(x)`` such that ``y(x) == y_target`` on the curve, or
    ``None`` when y_target is outside the response window
    ``[min(top, bottom), max(top, bottom)]`` (the curve never reaches it).

    Derivation: from y = bottom + (top - bottom) / (1 + 10^(hill*(log_ec50 - x))),
        x = log_ec50 - log10((top - y) / (y - bottom)) / hill
    """
    y_lo, y_hi = min(top, bottom), max(top, bottom)
    if not (y_lo < y_target < y_hi):
        return None
    if hill == 0.0 or top == bottom:
        return None
    ratio = (top - y_target) / (y_target - bottom)
    if ratio <= 0:
        return None
    return log_ec50 - math.log10(ratio) / hill


def _response_target(spec, top: float, bottom: float) -> float:
    """Translate an ``InterceptSpec`` into the absolute y-value the curve
    must cross.

    For ``RELATIVE_PERCENT``, the level is interpreted as a percentage of
    the response window from bottom to top — symmetric for IC and EC.
    The "kind" label (IC vs EC) is a naming convention (decreasing vs
    increasing assay readout); on a normalized %inhibition curve where
    bottom=0, top=100, both produce ``y_target = level`` directly.

    For ``ABSOLUTE``, the level is an absolute Y value.
    """
    if spec.basis == InterceptBasis.ABSOLUTE:
        return float(spec.level)
    return bottom + (spec.level / 100.0) * (top - bottom)


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
            bad = [float(c) for c in concentrations if not (c > 0)]
            return Failure(
                ValidationError(
                    f"Cannot fit dose-response: {len(bad)} point(s) have "
                    f"non-positive concentration (e.g., {bad[0]}). Dose-response "
                    f"curves require all doses > 0."
                )
            )

        raw_data = [
            {"concentration": p.concentration, "response": p.response} for p in active_points
        ]
        excluded_data = [
            {"concentration": p.concentration, "response": p.response} for p in excluded_points
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
        if max_response < config.inactive_threshold and not has_constraints:
            return Success(
                FittedCurveResult(
                    fitted_value=0.0,
                    hill_slope=0.0,
                    top=float(np.max(responses)),
                    bottom=float(np.min(responses)),
                    r_squared=0.0,
                    confidence_interval_low=None,
                    confidence_interval_high=None,
                    curve_class=CurveClass.INACTIVE,
                    num_points=len(active_points),
                    raw_data=raw_data,
                    excluded_points=excluded_data,
                    fit_quality_warnings=[],
                    outlier_suggestions=(),
                )
            )

        log_concentrations = np.log10(concentrations)

        # ──────────────────────────────────────────────────────────────────
        # First-pass fit
        # ──────────────────────────────────────────────────────────────────
        params, log_ec50_min, log_ec50_max = _build_params(log_concentrations, responses, config)

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
        # Outlier detection — emit SUGGESTIONS only, never silently exclude.
        #
        # The legacy "detect + refit on clean subset" cascade is gone:
        # excluding one point manually used to shift the fit and trigger N
        # more silent auto-exclusions on every refit, leaving chemists
        # with no idea why their data was vanishing. Now the fitter does
        # the detection once on the first-pass fit and returns the
        # candidates as ``OutlierSuggestion`` entries — the FE renders them
        # as yellow-halo markers; the chemist explicitly accepts or rejects.
        #
        # ``config.outlier_sigma is None`` skips detection entirely; this is
        # used by the Sprint-2 commit/preview paths where the chemist has
        # hand-curated the exclusion set.
        # ──────────────────────────────────────────────────────────────────
        outlier_suggestions: tuple[OutlierSuggestion, ...] = ()
        if (
            config.outlier_sigma is not None
            and len(active_points) >= _MIN_POINTS_FOR_OUTLIER_DETECTION
        ):
            residuals = responses - predicted
            outlier_mask = _detect_outliers(residuals, sigma=config.outlier_sigma)
            if np.any(outlier_mask):
                # SD of the full residual set; used to report per-point
                # severity (residual_z_full_sd) so the FE can rank
                # suggestions. This is a presentation-time hint distinct
                # from the per-point leave-one-out SD inside
                # ``_detect_outliers`` that actually flagged the candidate
                # — the docstring on ``OutlierSuggestion.residual_z_full_sd``
                # spells out the distinction.
                if len(residuals) >= 2:
                    full_sd = float(np.std(residuals, ddof=1))
                else:  # pragma: no cover — guarded by min-points check above
                    full_sd = 0.0
                suggestions: list[OutlierSuggestion] = []
                for i, is_outlier in enumerate(outlier_mask):
                    if not is_outlier:
                        continue
                    pt = active_points[i]
                    residual_z_full_sd = (
                        abs(float(residuals[i])) / full_sd if full_sd > 0 else 0.0
                    )
                    suggestions.append(
                        OutlierSuggestion(
                            idx=i,
                            concentration=float(pt.concentration),
                            response=float(pt.response),
                            residual_z_full_sd=residual_z_full_sd,
                        )
                    )
                outlier_suggestions = tuple(suggestions)

        # ──────────────────────────────────────────────────────────────────
        # Fit quality warnings — compute first so CI logic can consult them
        # ──────────────────────────────────────────────────────────────────
        warnings: list[str] = []
        ec50_at_bound = (
            abs(fitted_log_ec50 - log_ec50_min) < _BOUND_EPSILON_LOG10
            or abs(log_ec50_max - fitted_log_ec50) < _BOUND_EPSILON_LOG10
        )
        if ec50_at_bound:
            warnings.append("ec50_at_bound")
        log_min_c = float(np.min(log_concentrations))
        log_max_c = float(np.max(log_concentrations))
        if not (log_min_c <= fitted_log_ec50 <= log_max_c):
            warnings.append("ec50_outside_dose_range")
        if r_squared < 0.5:
            warnings.append("low_r_squared")

        # ──────────────────────────────────────────────────────────────────
        # Convert log_ec50 → ec50 and compute log-space CI.
        #
        # When the fit hits a bound or the stderr is unavailable / clamped to
        # the 10-decade cap, ``log_ec50_stderr`` is not a meaningful estimate
        # of uncertainty. Reporting a synthetic "±10 decades" or "±0.5 decade"
        # range would mislead the user into thinking the fitter has any
        # confidence in those bounds. Return None instead so the UI can show
        # "—" rather than a fake interval.
        # ──────────────────────────────────────────────────────────────────
        fitted_ec50 = float(10.0**fitted_log_ec50)
        ci_low: float | None
        ci_high: float | None
        if (
            ec50_at_bound
            or log_ec50_stderr is None
            or not np.isfinite(log_ec50_stderr)
            or log_ec50_stderr <= 0
        ):
            ci_low = None
            ci_high = None
        else:
            half_width = 1.96 * log_ec50_stderr
            if half_width >= 10.0:
                # stderr is so large the CI is meaningless — still degenerate.
                ci_low = None
                ci_high = None
            else:
                ci_low = float(10.0 ** (fitted_log_ec50 - half_width))
                ci_high = float(10.0 ** (fitted_log_ec50 + half_width))

        curve_class = _classify_curve(
            responses=responses,
            predicted=predicted,
            r_squared=r_squared,
            fitted_top=fitted_top,
            fitted_bottom=fitted_bottom,
            config=config,
        )

        # Compute the per-spec intercepts. ``config.intercepts`` is non-empty
        # by construction (DoseResponseConfig.__post_init__ defaults to a
        # single 50% intercept derived from curve_type when none are set).
        intercept_values: list[InterceptValue] = []
        for spec in config.intercepts:
            y_target = _response_target(spec, fitted_top, fitted_bottom)
            log_x = _hill_inverse_log10(
                top=fitted_top,
                bottom=fitted_bottom,
                log_ec50=fitted_log_ec50,
                hill=fitted_hill,
                y_target=y_target,
            )
            if log_x is None:
                intercept_values.append(
                    InterceptValue(
                        spec=spec,
                        value=float("nan"),
                        confidence_interval_low=None,
                        confidence_interval_high=None,
                        at_bound=True,
                    )
                )
                continue
            value = float(10.0**log_x)
            # CI: the offset (log_x - log_ec50) is constant for fixed
            # (top, bottom, hill, y_target), so log-space stderr propagates
            # unchanged. Reuse the same gating as the headline CI.
            i_ci_low: float | None
            i_ci_high: float | None
            if (
                ec50_at_bound
                or log_ec50_stderr is None
                or not np.isfinite(log_ec50_stderr)
                or log_ec50_stderr <= 0
            ):
                i_ci_low = None
                i_ci_high = None
            else:
                half_width = 1.96 * float(log_ec50_stderr)
                if half_width >= 10.0:
                    i_ci_low = None
                    i_ci_high = None
                else:
                    i_ci_low = float(10.0 ** (log_x - half_width))
                    i_ci_high = float(10.0 ** (log_x + half_width))
            intercept_values.append(
                InterceptValue(
                    spec=spec,
                    value=value,
                    confidence_interval_low=i_ci_low,
                    confidence_interval_high=i_ci_high,
                    at_bound=False,
                )
            )

        # Headline ``fitted_value`` stays as the primary intercept's value
        # for back-compat with all existing readers (grids, sparkline,
        # exports). For a default single-50%-intercept config this equals
        # the legacy log_ec50 → 10**log_ec50 conversion.
        primary_value = (
            intercept_values[0].value
            if intercept_values and not intercept_values[0].at_bound
            else fitted_ec50
        )

        return Success(
            FittedCurveResult(
                fitted_value=primary_value,
                hill_slope=fitted_hill,
                top=fitted_top,
                bottom=fitted_bottom,
                r_squared=r_squared,
                confidence_interval_low=ci_low,
                confidence_interval_high=ci_high,
                curve_class=curve_class,
                # All active points contributed to the fit — no silent auto-
                # exclusion. Suggested outliers ride along separately on
                # ``outlier_suggestions``.
                num_points=len(active_points),
                raw_data=raw_data,
                excluded_points=excluded_data,
                fit_quality_warnings=warnings,
                intercept_values=tuple(intercept_values),
                outlier_suggestions=outlier_suggestions,
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
    hill_has_range = config.hill_slope_min is not None or config.hill_slope_max is not None
    if constraint == HillSlopeConstraint.FIXED_AT_ONE:
        # "Magnitude exactly 1, sign matches data direction" — chemist's
        # natural "no cooperativity" Hill = 1.
        params["hill"].set(value=hill_sign * 1.0, vary=False)
    elif hill_has_range:
        # Explicit range overrides enum-implicit bounds. Cross-validation
        # against the enum already happened in DoseResponseConfig.
        h_min = config.hill_slope_min if config.hill_slope_min is not None else -20.0
        h_max = config.hill_slope_max if config.hill_slope_max is not None else 20.0
        params["hill"].set(value=_clamp(hill_init, h_min, h_max), min=h_min, max=h_max)
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
        t_min = config.top_constraint_min if config.top_constraint_min is not None else -np.inf
        t_max = config.top_constraint_max if config.top_constraint_max is not None else np.inf
        params["top"].set(value=_clamp(top_init, t_min, t_max), min=t_min, max=t_max)

    # Bottom: lock > range > free.
    if config.bottom_constraint is not None:
        params["bottom"].set(value=config.bottom_constraint, vary=False)
    elif config.bottom_constraint_min is not None or config.bottom_constraint_max is not None:
        b_min = (
            config.bottom_constraint_min if config.bottom_constraint_min is not None else -np.inf
        )
        b_max = (
            config.bottom_constraint_max if config.bottom_constraint_max is not None else np.inf
        )
        params["bottom"].set(value=_clamp(bottom_init, b_min, b_max), min=b_min, max=b_max)

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
    config: DoseResponseConfig,
) -> CurveClass:
    """Classify a fitted curve using thresholds from ``config``.

    Defaults are calibrated for normalized (%) Y axes. Raw-signal protocols
    must override ``inactive_threshold``/``full_top_min``/``full_bottom_max``
    on the protocol's ``DoseResponseConfig`` to classify correctly.
    """
    max_response = float(np.max(responses))
    if max_response < config.inactive_threshold:
        return CurveClass.INACTIVE

    # Bell-shaped detection on predicted curve; with the new Prism param this
    # is a single-direction sigmoid, so non-monotonicity is impossible from
    # the fit itself. Keep the check as a defensive fallback.
    if len(predicted) >= 3:
        diffs = np.diff(predicted)
        is_monotonic = bool(np.all(diffs <= 0) or np.all(diffs >= 0))
        if not is_monotonic:
            return CurveClass.BELL_SHAPED

    if (
        r_squared >= config.full_r2_min
        and fitted_top >= config.full_top_min
        and fitted_bottom <= config.full_bottom_max
    ):
        return CurveClass.FULL

    if r_squared >= config.partial_r2_min:
        return CurveClass.PARTIAL

    return CurveClass.INACTIVE
