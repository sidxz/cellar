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

import math
from typing import TYPE_CHECKING

import lmfit
import numpy as np
from returns.result import Failure, Result, Success

from cellar.domain.screening_assay.curve_fitting import (
    DOSE_ZERO_LEFT_OUT,
    ConcentrationResponsePoint,
    FittedCurveResult,
    InterceptValue,
    ResponseScale,
)
from cellar.domain.screening_assay.enums import (
    CurveClass,
    HillSlopeConstraint,
    InterceptBasis,
)
from cellar.domain.screening_assay.outlier_suggestion import OutlierSuggestion
from cellar.domain.shared.aggregation_types import ValueQualifier
from cellar.domain.shared.errors import DomainError, ValidationError

if TYPE_CHECKING:
    from lmfit.model import ModelResult

    from cellar.domain.screening_assay.dose_response_config import (
        DoseResponseConfig,
        InterceptSpec,
    )


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


def _response_target(spec, top: float, bottom: float, hill: float) -> float:
    """Translate an ``InterceptSpec`` into the absolute y-value the curve
    must cross.

    For ``RELATIVE_PERCENT``, the level is the share of the way from the
    curve's low-dose (no-compound) plateau to its high-dose one, as
    ``InterceptKind`` defines it: ICN on a decreasing curve is where the
    response has dropped N % below the upper plateau, ECN on an increasing
    one where it has risen N % above the lower plateau. With a positive
    Hill the low-dose plateau is ``bottom`` (bottom + N % of the window), with
    a negative one ``top`` (top - N %); a 50 % level is the midpoint either
    way, and a 90 % level always lies past it in dose.

    For ``ABSOLUTE``, the level is an absolute Y value.
    """
    if spec.basis == InterceptBasis.ABSOLUTE:
        return float(spec.level)
    start, end = (bottom, top) if hill > 0 else (top, bottom)
    return start + (spec.level / 100.0) * (end - start)


class LmfitCurveFitter:
    """Concrete 4PL curve fitter backed by lmfit (Prism parametrization)."""

    def fit(
        self,
        points: list[ConcentrationResponsePoint],
        config: DoseResponseConfig,
        scale: ResponseScale | None = None,
    ) -> Result[FittedCurveResult, DomainError]:
        """Fit a direction-agnostic 4PL curve to the provided data points.

        A point at dose <= 0 (a vehicle well in a titration) has no place on the log-dose
        axis: it is left out of the fit and counted in a ``DOSE_ZERO_LEFT_OUT`` note.

        ``scale`` is the % scale of the fitted layer, if it has one: a curve with no
        transition is judged against it (see ``_read_intercept``).
        """
        left_out = sum(1 for p in points if not p.concentration > 0)
        notes = [f"{DOSE_ZERO_LEFT_OUT}:{left_out}"] if left_out else []
        points = [p for p in points if p.concentration > 0]
        active_points = [p for p in points if not p.is_excluded]
        excluded_points = [p for p in points if p.is_excluded]

        if len(active_points) < _MIN_FITTING_POINTS:
            return Failure(
                ValidationError(
                    f"Curve fitting requires at least 4 non-excluded data points; "
                    f"got {len(active_points)}"
                )
            )

        # Replicates stacked at fewer doses than the 4PL has parameters (a control
        # column at one dose) are never a curve, however many points they hold.
        doses = len({p.concentration for p in active_points})
        if doses < _MIN_FITTING_POINTS:
            return Failure(
                ValidationError(
                    f"Curve fitting requires at least {_MIN_FITTING_POINTS} distinct doses; "
                    f"got {doses}"
                )
            )

        concentrations = np.array([p.concentration for p in active_points], dtype=float)
        responses = np.array([p.response for p in active_points], dtype=float)

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
                    fit_quality_warnings=notes,
                    intercept_values=tuple(
                        _censored(spec, ValueQualifier.GT, float(np.max(concentrations)))
                        for spec in config.intercepts
                    ),
                    outlier_suggestions=(),
                )
            )

        log_concentrations = np.log10(concentrations)

        # ──────────────────────────────────────────────────────────────────
        # First-pass fit: the best of several starting points
        # ──────────────────────────────────────────────────────────────────
        fitted = _fit_multi_start(log_concentrations, responses, config)
        if isinstance(fitted, Failure):
            return Failure(fitted.failure())

        best = fitted.unwrap().params
        log_ec50_min = float(best["log_ec50"].min)
        log_ec50_max = float(best["log_ec50"].max)
        fitted_top = float(best["top"].value)
        fitted_bottom = float(best["bottom"].value)
        fitted_log_ec50 = float(best["log_ec50"].value)
        fitted_hill = float(best["hill"].value)
        log_ec50_stderr = best["log_ec50"].stderr
        if fitted_top < fitted_bottom:
            # The same 4PL with its plateaus named the other way round: (bottom, top, -Hill).
            # Classes and relative levels read ``top`` as the upper plateau.
            fitted_top, fitted_bottom, fitted_hill = fitted_bottom, fitted_top, -fitted_hill

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
                # 0.0 branch guarded by min-points check above (no cover)
                full_sd = float(np.std(residuals, ddof=1)) if len(residuals) >= 2 else 0.0
                suggestions: list[OutlierSuggestion] = []
                for i, is_outlier in enumerate(outlier_mask):
                    if not is_outlier:
                        continue
                    pt = active_points[i]
                    residual_z_full_sd = abs(float(residuals[i])) / full_sd if full_sd > 0 else 0.0
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
        warnings: list[str] = list(notes)
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
        ci_half_width: float | None = None
        if (
            not ec50_at_bound
            and log_ec50_stderr is not None
            and np.isfinite(log_ec50_stderr)
            and 0 < 1.96 * log_ec50_stderr < 10.0  # a 10-decade interval says nothing
        ):
            ci_half_width = 1.96 * float(log_ec50_stderr)
        ci_low, ci_high = _log_interval(fitted_log_ec50, ci_half_width)

        # Each intercept, read against the tested doses. ``config.intercepts`` is non-empty
        # by construction (DoseResponseConfig.__post_init__ defaults to a single 50%
        # intercept derived from curve_type when none are set).
        doses = (float(np.min(concentrations)), float(np.max(concentrations)))
        intercept_values = [
            _read_intercept(
                spec,
                curve=(fitted_top, fitted_bottom, fitted_log_ec50, fitted_hill),
                doses=doses,
                transition_threshold=config.inactive_threshold,
                scale=scale,
                ci_half_width=ci_half_width,
            )
            for spec in config.intercepts
        ]
        # A flat curve with no scale has nothing to show it active at the lowest dose: its "<"
        # only says where its own crossing falls, so it never makes the curve active at all doses.
        f_lo, f_hi = _hill_equation(
            np.log10(doses), fitted_top, fitted_bottom, fitted_log_ec50, fitted_hill
        )
        judged = scale is not None or abs(float(f_hi - f_lo)) >= config.inactive_threshold

        curve_class = _classify_curve(
            responses=responses,
            # In dose order: the points arrive in well order, which says nothing about shape.
            predicted=predicted[np.argsort(log_concentrations, kind="stable")],
            r_squared=r_squared,
            fitted_top=fitted_top,
            fitted_bottom=fitted_bottom,
            primary=intercept_values[0].qualifier if judged else None,
            config=config,
        )

        # Headline ``fitted_value``: the primary intercept's value when it is exact, else
        # the fitted midpoint. Charts draw the sigmoid from it, so it is never a bound dose;
        # displayed values come from the intercepts' qualifiers.
        primary = intercept_values[0]
        primary_value = primary.value if primary.qualifier == ValueQualifier.EQ else fitted_ec50

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


def _read_intercept(
    spec: InterceptSpec,
    *,
    curve: tuple[float, float, float, float],
    doses: tuple[float, float],
    transition_threshold: float,
    scale: ResponseScale | None,
    ci_half_width: float | None,
) -> InterceptValue:
    """One intercept of the fitted ``curve`` (top, bottom, log EC50, Hill), read against the
    lowest and highest tested ``doses``.

    A transition is a change of at least ``transition_threshold`` that the fitted curve makes
    across the doses; plateaus extrapolated past them (a steep step at the last dose, a
    shallow curve's far ends) are not one.

    With a transition, the level sits at its % of the way from the fitted curve's low-dose
    plateau to its high-dose one (``_response_target``) and the effect runs the way the curve
    does; on a flat curve read on a ``scale``,
    the level sits at its % of the scale and the effect runs the scale's way.
    Then: past the level at the lowest dose is "<" the lowest dose, short of it at the
    highest dose is ">" the highest; otherwise the curve crosses it inside the doses ("="),
    or, when flat, the level lies inside a band whose shape is noise ("nd").

    A flat curve with no scale (raw signal, Z-score) has nothing to judge it by and keeps
    its own crossing, read against the doses as any value is: "=" inside them, "<" the lowest
    dose below them, ">" the highest above them (or when it has no crossing).
    """
    top, bottom, log_ec50, hill = curve
    lo, hi = doses
    f_lo, f_hi = _hill_equation(np.log10([lo, hi]), top, bottom, log_ec50, hill)
    flat = abs(float(f_hi - f_lo)) < transition_threshold
    if flat and scale is None:
        log_x = _hill_inverse_log10(
            top=top,
            bottom=bottom,
            log_ec50=log_ec50,
            hill=hill,
            y_target=_response_target(spec, top, bottom, hill),
        )
        if log_x is None or 10.0**log_x > hi:
            return _censored(spec, ValueQualifier.GT, hi)
        if 10.0**log_x < lo:
            return _censored(spec, ValueQualifier.LT, lo)
        return _exact(spec, log_x, ci_half_width)

    if flat and scale is not None:
        target = (
            float(spec.level)
            if spec.basis == InterceptBasis.ABSOLUTE
            else scale.zero + spec.level / 100.0 * (scale.full - scale.zero)
        )
        rising = scale.full > scale.zero
    else:
        target = _response_target(spec, top, bottom, hill)
        rising = bool(f_hi > f_lo)

    def reached(response: float) -> bool:
        return response >= target if rising else response <= target

    if reached(f_lo):
        return _censored(spec, ValueQualifier.LT, lo)
    if not reached(f_hi):
        return _censored(spec, ValueQualifier.GT, hi)
    if flat:
        return InterceptValue(
            spec=spec,
            value=float("nan"),
            confidence_interval_low=None,
            confidence_interval_high=None,
            qualifier=ValueQualifier.ND,
        )
    log_x = _hill_inverse_log10(
        top=top, bottom=bottom, log_ec50=log_ec50, hill=hill, y_target=target
    )
    # Short of the level at ``lo`` and at it at ``hi``: the crossing is in (lo, hi], and
    # only exactly at a saturated ``hi`` can the inverse miss it.
    return _exact(spec, math.log10(hi) if log_x is None else log_x, ci_half_width)


def _exact(spec: InterceptSpec, log_x: float, ci_half_width: float | None) -> InterceptValue:
    # The offset log_x - log_ec50 is constant for a fixed curve and level, so the log EC50's
    # interval carries over unchanged.
    ci_low, ci_high = _log_interval(log_x, ci_half_width)
    return InterceptValue(
        spec=spec,
        value=float(10.0**log_x),
        confidence_interval_low=ci_low,
        confidence_interval_high=ci_high,
        qualifier=ValueQualifier.EQ,
    )


def _censored(spec: InterceptSpec, qualifier: ValueQualifier, dose: float) -> InterceptValue:
    return InterceptValue(
        spec=spec,
        value=dose,
        confidence_interval_low=None,
        confidence_interval_high=None,
        at_bound=qualifier == ValueQualifier.GT,
        qualifier=qualifier,
    )


def _log_interval(log_x: float, half_width: float | None) -> tuple[float | None, float | None]:
    if half_width is None:
        return None, None
    return float(10.0 ** (log_x - half_width)), float(10.0 ** (log_x + half_width))


def _leastsq(
    model: lmfit.Model,
    params: lmfit.Parameters,
    log_c: np.ndarray,
    responses: np.ndarray,
    max_nfev: int | None = None,
) -> Result[ModelResult, DomainError]:
    try:
        return Success(
            model.fit(responses, params, log_c=log_c, method="leastsq", max_nfev=max_nfev)
        )
    except Exception as exc:
        return Failure(ValidationError(f"Curve fitting did not converge: {exc}"))


def _converged(fit: Result[ModelResult, DomainError]) -> Result[ModelResult, DomainError]:
    """A fit counts once leastsq has stopped on its own with finite parameters: it succeeded,
    or it could refine them no further ("tolerance seems to be too small", as when a plateau
    ends on its bound), which leaves no covariance, so no error bars and no CI. A fit cut off
    at its evaluation budget (``aborted``) has not converged."""
    if isinstance(fit, Success):
        result = fit.unwrap()
        values = [p.value for p in result.params.values()] + [result.chisqr]
        if result.aborted or not np.all(np.isfinite(values)):
            return Failure(ValidationError("Curve fitting did not converge"))
    return fit


def _fit_single_start(
    log_c: np.ndarray, responses: np.ndarray, config: DoseResponseConfig, inset: float = 0.01
) -> Result[ModelResult, DomainError]:
    """The fit from ``_build_params``'s start alone (``inset=0``: the fitter before multi-start,
    plateaus clamped onto their bounds), kept so tests can hold the multi-start against it."""
    params, _, _ = _build_params(log_c, responses, config, inset)
    return _converged(_leastsq(lmfit.Model(_hill_equation), params, log_c, responses))


def _fit_multi_start(
    log_c: np.ndarray, responses: np.ndarray, config: DoseResponseConfig
) -> Result[ModelResult, DomainError]:
    """Fit from the starts in ``_starting_points`` and keep the converged fit with the lowest
    residual sum of squares.

    From one start, leastsq settles in whatever minimum lies next to it, and a plateau start
    clamped onto its bound can leave the optimizer where it began.

    The first start (``_build_params``'s) is fitted in full, so the result is never worse
    than it, a tie keeps it, and when nothing converges its failure is the one reported. When
    its fit leaves no room for a better one (``_settled``), it is the result. Otherwise so is
    the start the fitter used before multi-start, with plateaus clamped onto their bounds
    (``inset=0``), so the result is never worse than that fitter's either. The others are
    screened on a tenth of lmfit's evaluation budget: each that converges in it stays a
    candidate, and when the best of them has not, it alone is carried on to convergence. A
    start that reaches a minimum of a real curve does so in a few hundred evaluations, while
    on flat, noise-only data every start crawls towards a bound for the full budget, twelve
    times over.
    """
    params, _, _ = _build_params(log_c, responses, config)
    model = lmfit.Model(_hill_equation)
    first, *others = _starting_points(params, log_c, responses)
    fits = [_converged(_leastsq(model, first, log_c, responses))]
    if isinstance(fits[0], Success) and _settled(fits[0].unwrap(), responses):
        return fits[0]
    clamped, _, _ = _build_params(log_c, responses, config, inset=0.0)
    if [p.value for p in clamped.values()] != [p.value for p in first.values()]:
        fits.append(_converged(_leastsq(model, clamped, log_c, responses)))

    budget = 200 * (sum(p.vary for p in params.values()) + 1)  # lmfit's default: 2000·(n + 1)
    screened = [_leastsq(model, start, log_c, responses, budget) for start in others]
    fits += [_converged(fit) for fit in screened]
    finished = [
        fit.unwrap()
        for fit in screened
        if isinstance(fit, Success) and np.isfinite(fit.unwrap().chisqr)
    ]
    if finished:
        lead = min(finished, key=lambda result: result.chisqr)
        if lead.aborted:
            fits.append(_converged(_leastsq(model, lead.params, log_c, responses)))

    converged = [fit.unwrap() for fit in fits if isinstance(fit, Success)]
    if not converged:
        return fits[0]
    return Success(min(converged, key=lambda result: result.chisqr))


def _settled(result: ModelResult, responses: np.ndarray) -> bool:
    """Whether a converged fit leaves no room for a better one from another start: no free
    parameter ends within 2 % of a bound (of its range's width, or of the response span when
    the range is half-open), and no free plateau lies past the observed responses. Other
    minima live there: on a bound the optimizer may have been stopped short, and an
    extrapolated plateau is barely pinned by the points."""
    span = _response_span(responses)
    for name, p in result.params.items():
        if not p.vary:
            continue
        width = p.max - p.min if np.isfinite(p.max - p.min) else span
        if min(p.value - p.min, p.max - p.value) <= 0.02 * width:
            return False
        if name in ("top", "bottom") and not np.min(responses) <= p.value <= np.max(responses):
            return False
    return True


def _starting_points(
    params: lmfit.Parameters, log_c: np.ndarray, responses: np.ndarray
) -> list[lmfit.Parameters]:
    """``params`` (``_build_params``'s start) first, then every pairing of
    - log EC50 at 5 evenly spaced points across the tested log doses, and at the dose where the
      responses cross the midpoint of their range (``_crossing_log_dose``);
    - plateaus at the lowest-/highest-dose quarter means (``params``'s) and at the data's
      max / min.
    Each value is clamped into its parameter's bounds and a locked parameter keeps its own;
    Hill keeps ``params``'s start. Starts that come out identical are fitted once.
    """
    lo, hi = float(np.min(log_c)), float(np.max(log_c))
    step = (hi - lo) / 4.0
    log_ec50s = (
        params["log_ec50"].value,  # the middle of the 5
        lo,
        lo + step,
        hi - step,
        hi,
        _crossing_log_dose(log_c, responses),
    )
    plateaus = (
        (params["top"].value, params["bottom"].value),
        (float(np.max(responses)), float(np.min(responses))),
    )
    span = _response_span(responses)
    seen: set[tuple[float, ...]] = set()
    starts: list[lmfit.Parameters] = []
    for top, bottom in plateaus:
        for log_ec50 in log_ec50s:
            start = params.copy()
            for name, value in (("top", top), ("bottom", bottom), ("log_ec50", log_ec50)):
                p = start[name]
                if p.vary:
                    p.set(value=_start_inside(value, p.min, p.max, open_width=span))
            key = tuple(start[name].value for name in ("top", "bottom", "log_ec50"))
            if key not in seen:
                seen.add(key)
                starts.append(start)
    return starts


def _crossing_log_dose(log_c: np.ndarray, responses: np.ndarray) -> float:
    """Log dose where the per-dose mean responses cross the midpoint of their own range,
    interpolated on the steepest step that crosses it; the middle of the doses when the
    responses are all equal."""
    doses, inverse = np.unique(log_c, return_inverse=True)
    means = np.bincount(inverse, weights=responses) / np.bincount(inverse)
    offset = means - (np.min(means) + np.max(means)) / 2.0
    crossings = np.flatnonzero(np.sign(offset[:-1]) != np.sign(offset[1:]))
    if not len(crossings):
        return float((doses[0] + doses[-1]) / 2.0)
    i = crossings[np.argmax(np.abs(np.diff(means)[crossings]))]
    fraction = -offset[i] / (offset[i + 1] - offset[i])
    return float(doses[i] + fraction * (doses[i + 1] - doses[i]))


def _build_params(
    log_concentrations: np.ndarray,
    responses: np.ndarray,
    config: DoseResponseConfig,
    inset: float = 0.01,
) -> tuple[lmfit.Parameters, float, float]:
    """Build lmfit Parameters with direction-aware initial guesses, log-space
    EC50 bounds tied to the observed dose range, and Prism-style top/bottom/hill
    constraints from ``config``. Starts keep ``inset`` off their bounds (``_start_inside``).

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
        params["hill"].set(
            value=_start_inside(hill_init, h_min, h_max, open_width=1.0, inset=inset),
            min=h_min,
            max=h_max,
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
        t_min = config.top_constraint_min if config.top_constraint_min is not None else -np.inf
        t_max = config.top_constraint_max if config.top_constraint_max is not None else np.inf
        params["top"].set(
            value=_start_inside(
                top_init, t_min, t_max, open_width=_response_span(responses), inset=inset
            ),
            min=t_min,
            max=t_max,
        )

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
        params["bottom"].set(
            value=_start_inside(
                bottom_init, b_min, b_max, open_width=_response_span(responses), inset=inset
            ),
            min=b_min,
            max=b_max,
        )

    return params, log_ec50_min, log_ec50_max


def _start_inside(
    value: float, lo: float, hi: float, *, open_width: float, inset: float = 0.01
) -> float:
    """A start for a parameter bounded by ``[lo, hi]`` (either may be ±inf): ``value`` kept
    ``inset`` (1 %) of the range's width off each bound, or of ``open_width`` when the range is
    half-open; ``inset=0`` clamps it into the range.

    lmfit maps a bounded parameter through a transform whose slope is zero at the bound, so
    from a start exactly on one leastsq sees no gradient and stops where it began.
    """
    margin = inset * (hi - lo if np.isfinite(hi - lo) else open_width)
    return min(max(value, lo + margin), hi - margin)


def _response_span(responses: np.ndarray) -> float:
    return float(np.ptp(responses)) or 1.0


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
    primary: ValueQualifier | None,
    config: DoseResponseConfig,
) -> CurveClass:
    """Classify a fitted curve using thresholds from ``config``.

    Defaults are calibrated for normalized (%) Y axes. Raw-signal protocols
    must override ``inactive_threshold``/``full_top_min``/``full_bottom_max``
    on the protocol's ``DoseResponseConfig`` to classify correctly.

    A curve past its primary intercept's level at the lowest dose (``primary`` "<") is
    active at all doses, whatever its R².
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

    if primary == ValueQualifier.LT:
        return CurveClass.ACTIVE_ALL_DOSES

    if (
        r_squared >= config.full_r2_min
        and fitted_top >= config.full_top_min
        and fitted_bottom <= config.full_bottom_max
    ):
        return CurveClass.FULL

    if r_squared >= config.partial_r2_min:
        return CurveClass.PARTIAL

    return CurveClass.INACTIVE
