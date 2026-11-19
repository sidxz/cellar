"""Tests for LmfitCurveFitter — 4PL Hill equation fitting."""

from __future__ import annotations

import math
import random

import numpy as np
import pytest
from returns.result import Failure, Success

from cellar.domain.screening_assay.curve_fitting import (
    DOSE_ZERO_LEFT_OUT,
    ConcentrationResponsePoint,
    ResponseScale,
)
from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig, InterceptSpec
from cellar.domain.screening_assay.enums import (
    CurveClass,
    CurveType,
    HillSlopeConstraint,
    InterceptKind,
)
from cellar.domain.shared.aggregation_types import ValueQualifier
from cellar.infrastructure.lmfit.curve_fitter import (
    LmfitCurveFitter,
    _fit_multi_start,
    _fit_single_start,
)
from tests.unit.screening.dr_synthetic import GRID, Case


def _generate_hill_data(
    ic50: float = 100.0,
    hill_slope: float = -1.0,
    top: float = 100.0,
    bottom: float = 0.0,
    n_points: int = 10,
    noise_pct: float = 0.02,
    seed: int = 42,
) -> list[ConcentrationResponsePoint]:
    """Synthetic FALLING dose-response data (top at low conc, bottom at high conc).

    Uses the legacy form ``y = bottom + (top-bottom) / (1 + (c/ic50)**|h|)`` —
    monotonically decreasing in c. ``hill_slope`` parameter is unused (kept for
    API back-compat with existing tests); curve direction is always falling.
    """
    rng = random.Random(seed)
    concs = [10000.0 / (3**i) for i in range(n_points)]
    points = []
    for c in concs:
        response = bottom + (top - bottom) / (1 + (c / ic50) ** abs(hill_slope))
        noise = rng.gauss(0, (top - bottom) * noise_pct)
        points.append(ConcentrationResponsePoint(concentration=c, response=response + noise))
    return points


def _generate_inhibition_data(
    ic50: float = 80.0,
    hill: float = 1.0,
    top: float = 100.0,
    bottom: float = 0.0,
    n_points: int = 11,
    noise_pct: float = 0.02,
    seed: int = 42,
    conc_min: float = 0.1,
    conc_max: float = 100.0,
) -> list[ConcentrationResponsePoint]:
    """Synthetic RISING % inhibition data (Prism form, signed Hill).

    ``y = bottom + (top-bottom) / (1 + 10^((logIC50 - logc) * hill))``
    With hill > 0, the curve rises with concentration — the typical
    % inhibition vs [inhibitor] shape.
    """
    import math as _m

    rng = random.Random(seed)
    log_min = _m.log10(conc_min)
    log_max = _m.log10(conc_max)
    log_ic50 = _m.log10(ic50)
    points = []
    for i in range(n_points):
        log_c = log_min + (log_max - log_min) * i / (n_points - 1)
        c = 10**log_c
        response = bottom + (top - bottom) / (1 + 10 ** ((log_ic50 - log_c) * hill))
        noise = rng.gauss(0, max(abs(top - bottom), 1.0) * noise_pct)
        points.append(ConcentrationResponsePoint(concentration=c, response=response + noise))
    return points


def _make_config(
    curve_type: CurveType = CurveType.IC50,
    hill_constraint: HillSlopeConstraint = HillSlopeConstraint.UNCONSTRAINED,
    top_constraint: float | None = None,
    bottom_constraint: float | None = None,
) -> DoseResponseConfig:
    return DoseResponseConfig(
        curve_type=curve_type,
        x_readout_name="Concentration",
        y_readout_name="% Inhibition",
        hill_slope_constraint=hill_constraint,
        top_constraint=top_constraint,
        bottom_constraint=bottom_constraint,
    )


class TestLmfitCurveFitter:
    def setup_method(self):
        self.fitter = LmfitCurveFitter()

    def test_fit_full_curve(self):
        points = _generate_hill_data(ic50=100.0, hill_slope=-1.0, top=100.0, bottom=0.0)
        config = _make_config()
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        fitted = result.unwrap()
        assert abs(fitted.fitted_value - 100.0) < 20.0
        assert fitted.r_squared > 0.95
        assert fitted.curve_class == CurveClass.FULL
        assert fitted.num_points == 10
        assert len(fitted.raw_data) == 10
        assert len(fitted.excluded_points) == 0

    def test_fit_partial_curve(self):
        points = _generate_hill_data(ic50=100.0, top=60.0, bottom=5.0)
        config = _make_config()
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        fitted = result.unwrap()
        assert fitted.curve_class == CurveClass.PARTIAL

    def test_fit_inactive(self):
        points = [
            ConcentrationResponsePoint(concentration=10000.0 / (3**i), response=5.0 + random.Random(i).gauss(0, 2))
            for i in range(10)
        ]
        config = _make_config()
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        fitted = result.unwrap()
        assert fitted.curve_class == CurveClass.INACTIVE

    def test_fit_with_excluded_points(self):
        points = _generate_hill_data(ic50=100.0)
        points[0] = ConcentrationResponsePoint(
            concentration=points[0].concentration, response=points[0].response, is_excluded=True,
        )
        points[1] = ConcentrationResponsePoint(
            concentration=points[1].concentration, response=points[1].response, is_excluded=True,
        )
        config = _make_config()
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        fitted = result.unwrap()
        assert fitted.num_points == 8
        assert len(fitted.excluded_points) == 2

    def test_fit_too_few_points(self):
        points = _generate_hill_data(n_points=3)
        config = _make_config()
        result = self.fitter.fit(points, config)
        assert isinstance(result, Failure)
        assert "at least 4" in str(result.failure()).lower()

    @pytest.mark.parametrize("doses", [[2.0], [0.1, 1.0, 10.0]])
    def test_fewer_than_four_distinct_doses_is_no_curve(self, doses):
        """Eight wells at one dose (a control stack) or replicates at three doses are
        never a curve, however many points they hold."""
        points = [
            ConcentrationResponsePoint(concentration=doses[i % len(doses)], response=95.0 + i)
            for i in range(8)
        ]
        result = self.fitter.fit(points, _make_config())
        assert isinstance(result, Failure)
        assert f"at least 4 distinct doses; got {len(doses)}" in str(result.failure())

    def test_a_point_at_dose_zero_is_left_out_of_the_fit(self):
        """Rifampicin's Resazurin titration: a vehicle well at dose 0 in an otherwise valid
        series. Zero has no place on a log-dose axis, so the point sits out of the fit and
        the curve records it, instead of the whole series being refused."""
        series = [
            (0.0, -3.89), (0.0006, 38.37), (0.0013, 54.94), (0.0025, 74.19), (0.005, 91.78),
            (0.01, 93.40), (0.02, 97.92), (0.03, 99.16), (0.06, 97.75), (0.13, 99.82),
            (0.25, 98.07), (0.5, 100.93), (1.0, 101.12), (2.0, 101.58), (2.0, 100.26),
        ]  # fmt: skip
        points = [ConcentrationResponsePoint(concentration=c, response=r) for c, r in series]
        result = self.fitter.fit(points, _make_config())
        assert isinstance(result, Success)
        fitted = result.unwrap()
        assert fitted.num_points == 14
        assert 0.0 not in [p["concentration"] for p in fitted.raw_data]
        assert f"{DOSE_ZERO_LEFT_OUT}:1" in fitted.fit_quality_warnings
        assert 0.0005 < fitted.fitted_value < 0.003

    @pytest.mark.parametrize("seed", [0, 1, 2, 3])
    def test_the_curve_class_does_not_depend_on_the_order_of_the_points(self, seed):
        """Rifampicin's Resazurin series arrives in well order (a 2 µM well first), not dose
        order; a 4PL is monotonic in dose, so the order must not make it bell-shaped."""
        series = [
            (2.0, 100.26), (0.0006, 38.37), (0.0013, 54.94), (0.0025, 74.19), (0.005, 91.78),
            (0.01, 93.40), (0.02, 97.92), (0.03, 99.16), (0.06, 97.75), (0.13, 99.82),
            (0.25, 98.07), (0.5, 100.93), (1.0, 101.12), (2.0, 101.58),
        ]  # fmt: skip
        points = [ConcentrationResponsePoint(concentration=c, response=r) for c, r in series]
        in_dose_order = self.fitter.fit(
            sorted(points, key=lambda p: p.concentration), _make_config()
        ).unwrap()
        random.Random(seed).shuffle(points)
        shuffled = self.fitter.fit(points, _make_config()).unwrap()
        assert in_dose_order.curve_class != CurveClass.BELL_SHAPED
        assert shuffled.curve_class == in_dose_order.curve_class

    def test_an_inactive_series_still_records_its_dose_zero_points(self):
        points = [ConcentrationResponsePoint(concentration=0.0, response=1.0)] * 2 + [
            ConcentrationResponsePoint(concentration=10.0**-i, response=2.0) for i in range(5)
        ]
        fitted = self.fitter.fit(points, _make_config()).unwrap()
        assert fitted.curve_class == CurveClass.INACTIVE
        assert fitted.fit_quality_warnings == [f"{DOSE_ZERO_LEFT_OUT}:2"]

    def test_points_at_dose_zero_do_not_count_toward_four_doses(self):
        points = [ConcentrationResponsePoint(concentration=0.0, response=0.0)] + [
            ConcentrationResponsePoint(concentration=c, response=r)
            for c, r in [(0.1, 10.0), (1.0, 50.0), (10.0, 90.0), (10.0, 92.0)]
        ]
        result = self.fitter.fit(points, _make_config())
        assert isinstance(result, Failure)
        assert "at least 4 distinct doses; got 3" in str(result.failure())

    def test_fit_with_hill_slope_constraint_negative(self):
        points = _generate_hill_data(ic50=100.0, hill_slope=-1.0)
        config = _make_config(hill_constraint=HillSlopeConstraint.NEGATIVE_ONLY)
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        assert result.unwrap().hill_slope < 0

    def test_fit_with_fixed_top(self):
        points = _generate_hill_data(ic50=100.0, top=100.0)
        config = _make_config(top_constraint=100.0)
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        assert abs(result.unwrap().top - 100.0) < 1.0

    def test_confidence_intervals(self):
        points = _generate_hill_data(ic50=100.0)
        config = _make_config()
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        fitted = result.unwrap()
        assert fitted.confidence_interval_low < fitted.fitted_value
        assert fitted.confidence_interval_high > fitted.fitted_value

    def test_raw_data_format(self):
        points = _generate_hill_data(ic50=100.0, n_points=8)
        config = _make_config()
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        fitted = result.unwrap()
        for pt in fitted.raw_data:
            assert "concentration" in pt
            assert "response" in pt


# ──────────────────────────────────────────────────────────────────────────
# Phase A direction-aware fitting tests (Prism parametrization)
# ──────────────────────────────────────────────────────────────────────────


class TestDirectionAwareFitting:
    """Covers the regression that motivated the rewrite: rising % inhibition
    curves with hard ``top_constraint=100, bottom_constraint=0`` were
    collapsing to IC50 ≈ 1e-12 because the legacy parametrization treated
    ``top`` as the low-concentration plateau.
    """

    def setup_method(self):
        self.fitter = LmfitCurveFitter()

    def test_rising_inhibition_with_hard_top_lock_fits_correctly(self):
        """The canonical NadD-like case. Rising % inhibition, IC50 = 80 µM,
        hard locks at top=100 / bottom=0 — should fit close to truth."""
        points = _generate_inhibition_data(ic50=80.0, hill=1.0, top=100.0, bottom=0.0)
        config = _make_config(top_constraint=100.0, bottom_constraint=0.0)

        result = self.fitter.fit(points, config)
        assert isinstance(result, Success), result.failure() if isinstance(result, Failure) else None
        fitted = result.unwrap()

        assert 50.0 < fitted.fitted_value < 150.0, (
            f"Expected IC50 around 80, got {fitted.fitted_value}"
        )
        assert fitted.hill_slope > 0, (
            f"Rising curve must have positive Hill, got {fitted.hill_slope}"
        )
        assert fitted.r_squared > 0.95
        assert fitted.top == pytest.approx(100.0, abs=0.001)
        assert fitted.bottom == pytest.approx(0.0, abs=0.001)
        assert "ec50_at_bound" not in fitted.fit_quality_warnings

    def test_falling_curve_unconstrained_keeps_negative_hill(self):
        """Legacy falling-data path still works under the new parametrization.
        Direction inference picks hill < 0; post-fit value is negative."""
        points = _generate_hill_data(ic50=100.0)
        result = self.fitter.fit(points, _make_config())
        assert isinstance(result, Success)
        fitted = result.unwrap()
        assert fitted.hill_slope < 0
        assert 50.0 < fitted.fitted_value < 200.0
        assert fitted.r_squared > 0.9

    def test_top_bottom_hard_locks_are_honored(self):
        """`vary=False` on top/bottom — fitted values must equal the constraint
        values to numerical precision (no inversion regression)."""
        points = _generate_inhibition_data(ic50=80.0)
        config = _make_config(top_constraint=100.0, bottom_constraint=0.0)
        fitted = self.fitter.fit(points, config).unwrap()
        assert fitted.top == pytest.approx(100.0, abs=1e-6)
        assert fitted.bottom == pytest.approx(0.0, abs=1e-6)

    def test_log_space_ci_is_asymmetric(self):
        """Symmetric stderr in log space → asymmetric CI in linear space.
        For nontrivial CIs, (ci_high - fitted) > (fitted - ci_low)."""
        points = _generate_inhibition_data(ic50=80.0, noise_pct=0.05)
        fitted = self.fitter.fit(points, _make_config()).unwrap()

        upper_half = fitted.confidence_interval_high - fitted.fitted_value
        lower_half = fitted.fitted_value - fitted.confidence_interval_low
        # Log-space CI is asymmetric in linear space whenever stderr > 0.
        assert upper_half > lower_half, (
            f"Expected log-asymmetric CI; got [{fitted.confidence_interval_low}, "
            f"{fitted.confidence_interval_high}] around {fitted.fitted_value}"
        )

    def test_ec50_at_bound_warning_for_no_signal_data(self):
        """Truly flat data with hard constraints can't yield a real IC50.
        Fitter pushes log_ec50 to a bound; warning is emitted; curve still
        renders (Success, not Failure)."""
        points = [
            ConcentrationResponsePoint(concentration=10**i, response=0.0)
            for i in range(-3, 8)  # 11 points spanning 10 decades
        ]
        config = _make_config(top_constraint=100.0, bottom_constraint=0.0)
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        fitted = result.unwrap()
        assert "ec50_at_bound" in fitted.fit_quality_warnings

    def test_inactive_fast_path_skipped_when_constraints_set(self):
        """Max < 30% would normally short-circuit to INACTIVE without
        running the optimizer. With a hard constraint, the user has asked
        for a constrained fit; the fast-path must be bypassed."""
        # Build flat low-response data: max ~ 5%, well under the 30% cutoff.
        rng = random.Random(0)
        points = [
            ConcentrationResponsePoint(
                concentration=10000.0 / (3**i),
                response=2.0 + rng.gauss(0, 1.0),
            )
            for i in range(10)
        ]
        # Without constraint → fast-path returns the inactive sentinel
        # (fitted_value == 0.0 from the short-circuit branch).
        unconstrained = self.fitter.fit(points, _make_config()).unwrap()
        assert unconstrained.fitted_value == 0.0
        assert unconstrained.curve_class == CurveClass.INACTIVE

        # With constraint → fast-path bypassed; fit runs. fitted_value
        # may still be nonsense and downstream classification can still
        # mark it INACTIVE, but the optimizer was given a chance.
        constrained = self.fitter.fit(
            points, _make_config(top_constraint=100.0, bottom_constraint=0.0)
        ).unwrap()
        # The flat data + hard top/bottom locks pushes log_ec50 to a bound;
        # the fitter reports that, not the inactive-zero sentinel.
        assert constrained.fit_quality_warnings, (
            "Expected at least one fit_quality_warning when constraints are "
            "applied to inactive data"
        )

    def test_fixed_at_one_for_rising_inhibition(self):
        """`HillSlopeConstraint.FIXED_AT_ONE` now means |hill| = 1 with the
        sign chosen by data direction. Rising % inhibition → hill = +1."""
        points = _generate_inhibition_data(ic50=50.0, hill=1.0)
        config = _make_config(hill_constraint=HillSlopeConstraint.FIXED_AT_ONE)
        fitted = self.fitter.fit(points, config).unwrap()
        assert fitted.hill_slope == pytest.approx(1.0, abs=0.01), (
            f"Expected hill = +1 for rising data with FIXED_AT_ONE, "
            f"got {fitted.hill_slope}"
        )

    def test_no_warnings_on_clean_fit(self):
        """A clean rising curve with strong signal should produce zero
        fit_quality_warnings (positive control for the warning logic)."""
        points = _generate_inhibition_data(
            ic50=10.0, hill=1.0, top=100.0, bottom=0.0, noise_pct=0.01,
            conc_min=0.01, conc_max=1000.0,
        )
        fitted = self.fitter.fit(points, _make_config()).unwrap()
        assert fitted.fit_quality_warnings == [], (
            f"Expected no warnings, got {fitted.fit_quality_warnings}"
        )


# ──────────────────────────────────────────────────────────────────────────
# Phase B — bounded-range constraints (CDD-style)
# ──────────────────────────────────────────────────────────────────────────


def _config_with_ranges(**overrides) -> DoseResponseConfig:
    base = dict(
        curve_type=CurveType.IC50,
        x_readout_name="Concentration",
        y_readout_name="% Inhibition",
    )
    base.update(overrides)
    return DoseResponseConfig(**base)


class TestRangeConstraints:
    """Phase B — Top/Bottom/Hill bounded ranges (CDD's IC50calc default)."""

    def setup_method(self):
        self.fitter = LmfitCurveFitter()

    def test_top_range_keeps_fitted_top_inside_bounds(self):
        """Plain rising curve, Top range [85, 110] — fitted Top must land in range."""
        points = _generate_inhibition_data(ic50=80.0, hill=1.0, top=100.0, bottom=0.0)
        cfg = _config_with_ranges(top_constraint_min=85.0, top_constraint_max=110.0)
        fitted = self.fitter.fit(points, cfg).unwrap()
        assert 85.0 <= fitted.top <= 110.0, (
            f"Top {fitted.top} outside [85, 110]"
        )

    def test_top_range_hits_upper_bound_on_overshoot(self):
        """Synthetic data plateauing well above the range (true top=130, observed
        plateau ≈ 130 over a wide dose range) — fit pegged at upper bound 110."""
        points = _generate_inhibition_data(
            ic50=10.0,
            hill=1.0,
            top=130.0,
            bottom=0.0,
            noise_pct=0.01,
            conc_min=0.01,
            conc_max=1000.0,
        )
        cfg = _config_with_ranges(top_constraint_min=85.0, top_constraint_max=110.0)
        fitted = self.fitter.fit(points, cfg).unwrap()
        assert fitted.top == pytest.approx(110.0, abs=0.5)

    def test_nadd_partial_curve_with_cdd_default_ranges(self):
        """Canonical Phase B acceptance: an NadD-shaped partial curve
        (capping ~62 % at 100 µM) with CDD-default ranges
        Top ∈ [85, 110], Bottom ∈ [-10, 10], Hill ∈ [0.9, 1.1] should produce
        an IC50 in the [55, 90] µM band where CDD's optimizer lands.

        Generated from the Prism 4PL with true Top=110, Bottom=0, Hill=1,
        IC50=70 µM, sampled across the same dose range as the NadD plate
        (0.001 to 100 µM, 11 points). The optimizer cannot observe the
        upper plateau, so without ranges the fit is wildly under-determined;
        with CDD's ranges it converges near IC50 = 70.

        Also asserts the multi-intercept feature (Phase I): with
        intercepts=(IC50, IC90), the fitter emits both values from the same
        Hill fit. IC90 lies past the tested dose range (the curve plateaus
        around IC50): the fitted curve has not reached its 90% level (=99)
        at 100 µM, so it reads "> 100 µM" rather than an extrapolated value.
        """
        from cellar.domain.screening_assay.dose_response_config import (
            InterceptSpec,
        )
        from cellar.domain.screening_assay.enums import InterceptKind

        points = _generate_inhibition_data(
            ic50=70.0,
            hill=1.0,
            top=110.0,
            bottom=0.0,
            n_points=11,
            noise_pct=0.03,
            conc_min=0.001,
            conc_max=100.0,
            seed=11,
        )
        cfg = _config_with_ranges(
            top_constraint_min=85.0,
            top_constraint_max=110.0,
            bottom_constraint_min=-10.0,
            bottom_constraint_max=10.0,
            hill_slope_min=0.9,
            hill_slope_max=1.1,
            intercepts=(
                InterceptSpec(InterceptKind.IC, 50),
                InterceptSpec(InterceptKind.IC, 90),
            ),
        )
        fitted = self.fitter.fit(points, cfg).unwrap()
        assert 55.0 <= fitted.fitted_value <= 90.0, (
            f"IC50 {fitted.fitted_value} outside acceptance band [55, 90] µM"
        )
        assert fitted.r_squared > 0.95
        assert 0.9 <= fitted.hill_slope <= 1.1

        # Both intercepts present and ordered by spec.
        assert len(fitted.intercept_values) == 2
        ic50 = fitted.intercept_values[0]
        ic90 = fitted.intercept_values[1]
        assert ic50.spec.level == 50
        assert ic90.spec.level == 90
        # IC90 needs more drug than IC50 for a rising inhibition curve: here more
        # than the highest tested dose.
        assert ic90.value > ic50.value
        assert ic50.qualifier == ValueQualifier.EQ
        assert (ic90.qualifier, ic90.value, ic90.at_bound) == (ValueQualifier.GT, 100.0, True)

    def test_lock_and_range_mutually_exclusive_at_construction(self):
        """Domain-layer ValidationError, not a runtime fitter error."""
        from cellar.domain.shared.errors import ValidationError as VE

        with pytest.raises(VE, match="top_constraint"):
            _config_with_ranges(top_constraint=100.0, top_constraint_min=85.0)

    def test_range_min_greater_than_max_rejected_at_construction(self):
        from cellar.domain.shared.errors import ValidationError as VE

        with pytest.raises(VE, match="top_constraint_min"):
            _config_with_ranges(top_constraint_min=110.0, top_constraint_max=85.0)

    def test_init_value_clamped_into_range(self):
        """Strongly rising data → top_init ≈ 130 from data inference; with
        Top range [50, 100] the fitter must clamp the start point inside
        [50, 100] (lmfit rejects out-of-bounds starts with a SystemExit)."""
        points = _generate_inhibition_data(
            ic50=80.0, hill=1.0, top=130.0, bottom=0.0, noise_pct=0.01,
        )
        cfg = _config_with_ranges(top_constraint_min=50.0, top_constraint_max=100.0)
        result = self.fitter.fit(points, cfg)
        assert isinstance(result, Success), (
            f"Fit must succeed despite top_init outside range: "
            f"{result.failure() if isinstance(result, Failure) else None}"
        )
        fitted = result.unwrap()
        assert 50.0 <= fitted.top <= 100.0

    def test_hill_range_consistent_with_positive_only_enum(self):
        """POSITIVE_ONLY enum + Hill range [0.5, 2.0] both constrain hill > 0;
        the explicit range overrides the enum's [0.01, 20] bounds — fit lands
        inside [0.5, 2.0]."""
        points = _generate_inhibition_data(ic50=80.0, hill=1.5)
        cfg = _config_with_ranges(
            hill_constraint=HillSlopeConstraint.POSITIVE_ONLY,
            hill_slope_min=0.5,
            hill_slope_max=2.0,
        ) if False else DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="Concentration",
            y_readout_name="% Inhibition",
            hill_slope_constraint=HillSlopeConstraint.POSITIVE_ONLY,
            hill_slope_min=0.5,
            hill_slope_max=2.0,
        )
        fitted = self.fitter.fit(points, cfg).unwrap()
        assert 0.5 <= fitted.hill_slope <= 2.0

    def test_hill_range_contradicting_enum_rejected_at_construction(self):
        """POSITIVE_ONLY + Hill range straddling 0 → ValidationError."""
        from cellar.domain.shared.errors import ValidationError as VE

        with pytest.raises(VE, match="hill_slope"):
            DoseResponseConfig(
                curve_type=CurveType.IC50,
                x_readout_name="Concentration",
                y_readout_name="% Inhibition",
                hill_slope_constraint=HillSlopeConstraint.POSITIVE_ONLY,
                hill_slope_min=-2.0,
                hill_slope_max=2.0,
            )

    def test_open_top_range_only_max_set(self):
        """Top range with only max set → upper bound only, no lower bound."""
        points = _generate_inhibition_data(ic50=80.0, hill=1.0, top=100.0, bottom=0.0)
        cfg = _config_with_ranges(top_constraint_max=110.0)
        fitted = self.fitter.fit(points, cfg).unwrap()
        assert fitted.top <= 110.0

    def test_bottom_range_keeps_fitted_bottom_inside_bounds(self):
        points = _generate_inhibition_data(
            ic50=80.0, hill=1.0, top=100.0, bottom=5.0
        )
        cfg = _config_with_ranges(
            bottom_constraint_min=-10.0, bottom_constraint_max=10.0
        )
        fitted = self.fitter.fit(points, cfg).unwrap()
        assert -10.0 <= fitted.bottom <= 10.0


class TestOutlierSigmaConfig:
    """Phase B follow-on — outlier removal threshold is protocol-configurable."""

    def setup_method(self):
        self.fitter = LmfitCurveFitter()

    def _points_with_one_clear_outlier(self):
        """Inhibition curve where the 4th point is wildly off."""
        points = _generate_inhibition_data(
            ic50=10.0, hill=1.0, top=100.0, bottom=0.0,
            n_points=11, noise_pct=0.01, conc_min=0.01, conc_max=1000.0,
            seed=7,
        )
        outlier = points[3]
        points[3] = ConcentrationResponsePoint(
            concentration=outlier.concentration,
            response=outlier.response + 60.0,  # huge residual
        )
        return points

    def test_default_3sigma_surfaces_clear_outlier_as_suggestion(self):
        """With the redesigned fitter, auto-3σ is a SUGGESTION, not a silent
        removal. The candidate appears on ``outlier_suggestions`` and is NOT
        in ``excluded_points``; the point still contributes to the fit."""
        points = self._points_with_one_clear_outlier()
        cfg = _config_with_ranges()
        fitted = self.fitter.fit(points, cfg).unwrap()
        # Suggestion present
        assert len(fitted.outlier_suggestions) == 1, (
            f"expected 1 outlier suggestion, got {len(fitted.outlier_suggestions)}"
        )
        assert fitted.outlier_suggestions[0].idx == 3
        # No silent exclusion
        auto_excluded = [
            p for p in fitted.excluded_points if p.get("reason") == "auto_3sigma"
        ]
        assert auto_excluded == [], (
            "auto-3σ must not silently remove points anymore"
        )
        # Point was used in the fit (num_points unchanged from input)
        assert fitted.num_points == len(points)

    def test_outlier_sigma_none_disables_detection(self):
        """``outlier_sigma=None`` skips suggestion detection entirely — used
        by preview / Sprint-2 commit paths where the chemist owns selection."""
        points = self._points_with_one_clear_outlier()
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="Concentration",
            y_readout_name="% Inhibition",
            outlier_sigma=None,
        )
        fitted = self.fitter.fit(points, cfg).unwrap()
        assert fitted.outlier_suggestions == (), (
            "outlier_sigma=None must skip suggestion detection entirely"
        )
        # And of course no silent exclusion either.
        auto_excluded = [
            p for p in fitted.excluded_points if p.get("reason") == "auto_3sigma"
        ]
        assert auto_excluded == []

    def test_outlier_sigma_must_be_positive(self):
        from cellar.domain.shared.errors import ValidationError as VE

        with pytest.raises(VE, match="outlier_sigma"):
            DoseResponseConfig(
                curve_type=CurveType.IC50,
                y_readout_name="response",
                outlier_sigma=0.0,
            )
        with pytest.raises(VE, match="outlier_sigma"):
            DoseResponseConfig(
                curve_type=CurveType.IC50,
                y_readout_name="response",
                outlier_sigma=-1.0,
            )


class TestOutlierSuggestionAlignment:
    """F2 (post-redesign) — outlier suggestions must carry the ORIGINAL index +
    concentration of the offending point. Bug guard: when a specific point at
    position 3 is blatantly off, the SUGGESTION must name idx=3 and the
    original concentration; ``raw_data`` is unchanged (no silent removal)."""

    def setup_method(self):
        self.fitter = LmfitCurveFitter()

    def test_single_clear_outlier_at_position_three_surfaces_as_suggestion(self):
        # 11 points in a clean rising curve; replace point at index 3 with
        # something massively wrong (residual ~ 60).
        clean = _generate_inhibition_data(
            ic50=10.0, hill=1.0, top=100.0, bottom=0.0,
            n_points=11, noise_pct=0.005, conc_min=0.01, conc_max=1000.0,
            seed=21,
        )
        bad_idx = 3
        original_bad_conc = clean[bad_idx].concentration
        clean[bad_idx] = ConcentrationResponsePoint(
            concentration=original_bad_conc,
            response=clean[bad_idx].response + 60.0,
        )
        cfg = _config_with_ranges()
        fitted = self.fitter.fit(clean, cfg).unwrap()

        assert len(fitted.outlier_suggestions) == 1, (
            f"expected exactly 1 outlier suggestion, got "
            f"{len(fitted.outlier_suggestions)}"
        )
        suggestion = fitted.outlier_suggestions[0]
        # idx must point at the original-input position; concentration must
        # match the original offending point.
        assert suggestion.idx == bad_idx
        assert suggestion.concentration == pytest.approx(original_bad_conc, rel=1e-9)
        assert suggestion.residual_z_full_sd > 0
        # Nothing silently moved to excluded_data.
        auto_excluded = [
            p for p in fitted.excluded_points if p.get("reason") == "auto_3sigma"
        ]
        assert auto_excluded == []
        # raw_data still has all the points (including the bad one) — no
        # silent surgery on the active-points list.
        assert len(fitted.raw_data) == len(clean)


class TestOutlierSuggestionContract:
    """Sprint-2 redesign: the fitter emits SUGGESTIONS, never silent removals.

    Single source of truth for the new contract — every other test in this
    module assumes this behavior."""

    def setup_method(self):
        self.fitter = LmfitCurveFitter()

    def _points_with_clear_outlier_at(self, idx: int):
        points = _generate_inhibition_data(
            ic50=10.0, hill=1.0, top=100.0, bottom=0.0,
            n_points=11, noise_pct=0.005, conc_min=0.01, conc_max=1000.0,
            seed=21,
        )
        bad = points[idx]
        points[idx] = ConcentrationResponsePoint(
            concentration=bad.concentration,
            response=bad.response + 60.0,
        )
        return points

    def test_fit_returns_outlier_suggestion_separately_from_exclusions(self):
        """A clear outlier surfaces as a SUGGESTION (not a silent exclusion)
        and the offending point still contributes to the fit."""
        points = self._points_with_clear_outlier_at(idx=5)
        cfg = _config_with_ranges()
        result = self.fitter.fit(points, cfg)
        assert isinstance(result, Success)
        fitted = result.unwrap()
        # Suggestion is present and points at the offender.
        assert any(s.idx == 5 for s in fitted.outlier_suggestions)
        # The point was NOT silently moved to excluded_points.
        auto_excluded = [
            e for e in fitted.excluded_points if e.get("reason") == "auto_3sigma"
        ]
        assert auto_excluded == []
        # num_points unchanged from input — no surgery.
        assert fitted.num_points == len(points)

    def test_fit_no_suggestions_when_outlier_sigma_is_none(self):
        """outlier_sigma=None disables the suggestion pass entirely — the
        Sprint-2 preview/commit paths rely on this to avoid cascade."""
        points = self._points_with_clear_outlier_at(idx=5)
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="Concentration",
            y_readout_name="% Inhibition",
            outlier_sigma=None,
        )
        fitted = self.fitter.fit(points, cfg).unwrap()
        assert fitted.outlier_suggestions == ()

    def test_suggestion_carries_residual_severity(self):
        points = self._points_with_clear_outlier_at(idx=5)
        cfg = _config_with_ranges()
        fitted = self.fitter.fit(points, cfg).unwrap()
        assert len(fitted.outlier_suggestions) >= 1
        s = fitted.outlier_suggestions[0]
        assert s.residual_z_full_sd > 0

    def test_first_pass_fit_quality_bounded_when_outlier_present(self):
        """A single severe outlier degrades but does not destroy the first-pass fit.

        Guards against a future change where suggestion emission silently
        allows catastrophic fit failure (e.g. R² < 0.7) without the chemist
        noticing on first load. Empirically the fitter produces R² ≈ 0.83
        on an 11-point clean sigmoid with one ~5σ outlier; the floor 0.7
        leaves some headroom but is tight enough to catch a real
        regression in fit robustness."""
        points = self._points_with_clear_outlier_at(idx=3)
        cfg = _config_with_ranges()
        result = self.fitter.fit(points, cfg)
        assert isinstance(result, Success)
        fitted = result.unwrap()
        # The outlier WAS surfaced as a suggestion.
        assert any(s.idx == 3 for s in fitted.outlier_suggestions)
        # The outlier STAYED in the fit (no silent exclusion).
        assert fitted.num_points == len(points)
        # Chemistry-truth: fit quality is degraded but bounded.
        assert fitted.r_squared > 0.7, (
            f"first-pass R²={fitted.r_squared} with a single outlier is "
            "unexpectedly low — check that the fit isn't being destabilized "
            "by outliers in a way users would notice"
        )


class TestProtocolDrivenClassification:
    """F4 — classification thresholds are driven by ``DoseResponseConfig`` so
    raw-signal protocols (fluorescence, luminescence) classify correctly."""

    def setup_method(self):
        self.fitter = LmfitCurveFitter()

    def test_raw_signal_full_curve_with_overridden_thresholds(self):
        # Synthetic fluorescence-style data: top ~ 6000 RFU, bottom ~ 100 RFU.
        # Default classification thresholds (full_top_min=80, full_bottom_max=20)
        # would never fire; protocol overrides them to lab-realistic numbers.
        points = _generate_inhibition_data(
            ic50=10.0, hill=1.0, top=6000.0, bottom=100.0,
            n_points=11, noise_pct=0.01, conc_min=0.01, conc_max=1000.0,
            seed=33,
        )
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="Concentration",
            y_readout_name="Raw RFU",
            inactive_threshold=300.0,
            full_top_min=5000.0,
            full_bottom_max=200.0,
        )
        fitted = self.fitter.fit(points, cfg).unwrap()
        assert fitted.curve_class == CurveClass.FULL, (
            f"raw-signal curve should classify as FULL with overridden "
            f"thresholds; got {fitted.curve_class}"
        )

    def test_inactive_fast_path_uses_config_threshold(self):
        # Max response ~ 200 — below custom threshold 300 → INACTIVE.
        rng = random.Random(2)
        points = [
            ConcentrationResponsePoint(
                concentration=10.0 ** (i - 3),
                response=150.0 + rng.gauss(0, 10),
            )
            for i in range(10)
        ]
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="Concentration",
            y_readout_name="Raw RFU",
            inactive_threshold=300.0,
        )
        fitted = self.fitter.fit(points, cfg).unwrap()
        assert fitted.curve_class == CurveClass.INACTIVE
        # CI is now None (was 0.0 synthetic) for inactive fast-path.
        assert fitted.confidence_interval_low is None
        assert fitted.confidence_interval_high is None


class TestConfidenceIntervalNoneAtBound:
    """F6 — return ``None`` for CI when the fit is unreliable (bound hit, stderr
    unavailable, or stderr would clamp to >= 10 decades)."""

    def setup_method(self):
        self.fitter = LmfitCurveFitter()

    def test_ci_is_none_when_ec50_at_bound(self):
        # Truly flat data with hard locks → log_ec50 hits a bound; CI must be
        # None rather than a synthetic ±10 decades.
        points = [
            ConcentrationResponsePoint(concentration=10**i, response=0.0)
            for i in range(-3, 8)
        ]
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="Concentration",
            y_readout_name="% Inhibition",
            top_constraint=100.0,
            bottom_constraint=0.0,
        )
        fitted = self.fitter.fit(points, cfg).unwrap()
        assert "ec50_at_bound" in fitted.fit_quality_warnings
        assert fitted.confidence_interval_low is None
        assert fitted.confidence_interval_high is None

    def test_ci_present_for_clean_fit(self):
        # Sanity check: a normal fit still returns finite CI bounds.
        points = _generate_inhibition_data(
            ic50=80.0, hill=1.0, top=100.0, bottom=0.0, noise_pct=0.02,
        )
        fitted = self.fitter.fit(points, _config_with_ranges()).unwrap()
        assert fitted.confidence_interval_low is not None
        assert fitted.confidence_interval_high is not None
        assert fitted.confidence_interval_low < fitted.fitted_value < fitted.confidence_interval_high


class TestMultiIntercept:
    """One Hill fit -> N intercepts (IC50, IC90, IC99 etc.) — CDD parity."""

    def setup_method(self):
        self.fitter = LmfitCurveFitter()

    def test_single_default_intercept_matches_fitted_value(self):
        """Default config emits one intercept (IC50@50). Its value must equal fitted_value."""
        points = _generate_inhibition_data(ic50=10.0, hill=1.0, top=100.0, bottom=0.0)
        cfg = _make_config()
        result = self.fitter.fit(points, cfg).unwrap()
        assert len(result.intercept_values) == 1
        assert result.intercept_values[0].value == pytest.approx(result.fitted_value, rel=1e-6)
        assert not result.intercept_values[0].at_bound

    def test_ic50_and_ic90_from_one_fit(self):
        """Hill=1 + perfect 0..100 plateau curve: IC90/IC50 = 9 (analytic)."""
        from cellar.domain.screening_assay.dose_response_config import (
            DoseResponseConfig,
            InterceptSpec,
        )
        from cellar.domain.screening_assay.enums import InterceptKind
        points = _generate_inhibition_data(
            ic50=1.0, hill=1.0, top=100.0, bottom=0.0,
            n_points=15, noise_pct=0.001,
            conc_min=0.001, conc_max=1000.0,
        )
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="Concentration",
            y_readout_name="% Inhibition",
            intercepts=(
                InterceptSpec(InterceptKind.IC, 50),
                InterceptSpec(InterceptKind.IC, 90),
            ),
        )
        result = self.fitter.fit(points, cfg).unwrap()
        assert len(result.intercept_values) == 2
        ic50 = result.intercept_values[0]
        ic90 = result.intercept_values[1]
        # IC90 must be at higher concentration than IC50 for a rising curve
        # (need more drug for stronger inhibition).
        assert ic90.value > ic50.value
        # Hill=1 → IC90 / IC50 = 9 (analytic).
        assert ic90.value / ic50.value == pytest.approx(9.0, rel=0.02)

    def test_intercept_outside_curve_window_returns_at_bound(self):
        """IC90 on a curve that plateaus at 50% inhibition can never reach 90%."""
        from cellar.domain.screening_assay.dose_response_config import (
            DoseResponseConfig,
            InterceptSpec,
        )
        from cellar.domain.screening_assay.enums import InterceptKind
        # Synthetic data hard-capped at 50%: bottom=0, top=50.
        points = _generate_inhibition_data(
            ic50=1.0, hill=1.0, top=50.0, bottom=0.0,
            n_points=11, noise_pct=0.005,
        )
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="Concentration",
            y_readout_name="% Inhibition",
            top_constraint=50.0,
            bottom_constraint=0.0,
            intercepts=(InterceptSpec(InterceptKind.IC, 90),),
        )
        result = self.fitter.fit(points, cfg).unwrap()
        # Target y = 0 + 0.9 * 50 = 45 — within [0, 50], so this should NOT
        # be at_bound. Adjust expectation: IC90 == conc at 90% along the
        # 0..50 window. That's reachable.
        assert not result.intercept_values[0].at_bound
        # Now ask for IC@y=80 absolute → outside the curve: not reached at the highest
        # dose, so "> 100" and at_bound.
        from cellar.domain.screening_assay.enums import InterceptBasis
        cfg2 = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="Concentration",
            y_readout_name="% Inhibition",
            top_constraint=50.0,
            bottom_constraint=0.0,
            intercepts=(InterceptSpec(InterceptKind.IC, 80, basis=InterceptBasis.ABSOLUTE),),
        )
        result2 = self.fitter.fit(points, cfg2).unwrap()
        iv = result2.intercept_values[0]
        assert (iv.qualifier, iv.value, iv.at_bound) == (ValueQualifier.GT, 100.0, True)


# ──────────────────────────────────────────────────────────────────────────
# Multi-start: bounded fits find the best fit, not the one next to the start
# ──────────────────────────────────────────────────────────────────────────


def _bounds_around(case: Case, below: float, above: float) -> DoseResponseConfig:
    """Plateau ranges that contain the generating plateaus, ``below`` under and ``above`` over."""
    return DoseResponseConfig(
        curve_type=CurveType.EC50,
        y_readout_name="% Inhibition",
        top_constraint_min=case.top - below,
        top_constraint_max=case.top + above,
        bottom_constraint_min=case.bottom - below,
        bottom_constraint_max=case.bottom + above,
    )


# Exact data, so the generating parameters are the one perfect fit: missing them is the
# optimizer's fault. (With noise, a shallow curve's Hill is not pinned to 15 % by its points.)
_RECOVERABLE = [c for c in GRID if c.position == "inside" and c.noise_sd == 0]


@pytest.mark.parametrize(
    ("below", "above"), [(10, 10), (20, 5), (5, 20)], ids=["centred", "truth-high", "truth-low"]
)
@pytest.mark.parametrize("case", _RECOVERABLE, ids=lambda c: c.name)
def test_bounded_fit_recovers_generating_params(case, below, above):
    fitted = LmfitCurveFitter().fit(case.points(), _bounds_around(case, below, above)).unwrap()
    assert math.log10(fitted.fitted_value) == pytest.approx(case.log_ec50, abs=0.1)
    assert fitted.hill_slope == pytest.approx(case.hill, rel=0.15)


# The WCA_DHFR plate (Resazurin, % inhibition = 100·(NEG - raw)/(NEG - POS), NEG 16370,
# POS 2472), as (µM, %). Both fit cleanly when free. Under bottom [-10, 10] with some of the
# top / Hill ranges labs pair it with, the single start used to sit still: inactive, or an
# EC50 off the crossing. Batch MSD-549135706-001G001 is SACC-0428727.
_MSD_549135706 = [
    (0.0002, -4.22), (0.0004, 10.6), (0.001, 13.05), (0.0015, 38.7), (0.003, 75.05),
    (0.0065, 84.62), (0.0125, 87.52), (0.025, 89.4), (0.05, 92.19), (0.1, 90.42), (0.2, 84.49),
    (0.4, 89.42), (1.0, 90.32), (1.5, 91.67), (3.0, 91.39), (6.5, 92.18), (12.5, 92.33),
    (25.0, 95.42), (50.0, 93.57), (100.0, 92.23),
]  # fmt: skip
# Rifampicin, wells O18-O20 left out.
_RIFAMPICIN = [
    (0.0006, 1.76), (0.0013, 28.29), (0.0025, 38.19), (0.005, 63.14), (0.01, 74.83),
    (0.02, 93.41), (0.03, 95.33), (0.06, 95.87), (0.13, 94.81), (0.25, 99.49), (0.5, 100.34),
    (1.0, 99.32), (2.0, 99.76), (2.0, 100.73),
]  # fmt: skip


# Bottom [-10, 10] with each top and Hill setting labs use on it in the CDD protocols.
@pytest.mark.parametrize(
    "top", [None, (85.0, 110.0), (90.0, 110.0), (90.0, 100.0), (95.0, 105.0)], ids=str
)
@pytest.mark.parametrize("hill", [None, (0.9, 1.1)], ids=str)
@pytest.mark.parametrize(
    ("series", "crossing"),
    [(_MSD_549135706, (0.0015, 0.003)), (_RIFAMPICIN, (0.0025, 0.005))],
    ids=["MSD-549135706", "rifampicin"],
)
def test_plate_regressions_bounded(series, crossing, top, hill):
    points = [ConcentrationResponsePoint(concentration=c, response=r) for c, r in series]
    fitted = LmfitCurveFitter().fit(points, _plate_config(top, hill)).unwrap()
    assert fitted.curve_class != CurveClass.INACTIVE
    # The EC50 sits between the two doses the responses cross 50 % at.
    assert crossing[0] < fitted.fitted_value < crossing[1]


def _plate_config(top, hill) -> DoseResponseConfig:
    return DoseResponseConfig(
        curve_type=CurveType.EC50,
        y_readout_name="% Inhibition",
        bottom_constraint_min=-10.0,
        bottom_constraint_max=10.0,
        top_constraint_min=top[0] if top else None,
        top_constraint_max=top[1] if top else None,
        hill_slope_min=hill[0] if hill else None,
        hill_slope_max=hill[1] if hill else None,
    )


@pytest.mark.parametrize(
    ("series", "crossing", "top", "hill"),
    [
        (_MSD_549135706, (0.0015, 0.003), (90.0, 100.0), None),
        (_MSD_549135706, (0.0015, 0.003), (90.0, 110.0), (0.9, 1.1)),
        (_RIFAMPICIN, (0.0025, 0.005), (95.0, 105.0), (0.9, 1.1)),
    ],
    ids=["MSD-549135706-top90-100", "MSD-549135706-top90-110-hill", "rifampicin-top95-105-hill"],
)
def test_one_start_moves_off_a_plateau_start_clamped_into_its_range(series, crossing, top, hill):
    """The plate cases whose quarter-mean bottom start (above 10) used to be clamped onto the
    bound itself, where lmfit's bound transform has no slope: the fit sat at its start."""
    log_c = np.log10([c for c, _ in series])
    y = np.array([r for _, r in series])
    fit = _fit_single_start(log_c, y, _plate_config(top, hill)).unwrap()
    assert crossing[0] < 10 ** fit.params["log_ec50"].value < crossing[1]


@pytest.mark.parametrize("bounded", [False, True], ids=["free", "bounds-around-truth"])
def test_multi_start_never_worse_than_single_start_on_grid(bounded):
    """Never worse than the start inside the bounds, nor than the fitter before multi-start
    (plateau starts clamped onto their bounds, ``inset=0``)."""
    worse = []
    for case in GRID:
        cfg = _bounds_around(case, 10, 10) if bounded else _make_config()
        points = case.points()
        log_c = np.log10([p.concentration for p in points])
        y = np.array([p.response for p in points])
        new = _fit_multi_start(log_c, y, cfg)
        for inset in (0.01, 0.0):
            old = _fit_single_start(log_c, y, cfg, inset)
            if isinstance(old, Success) and not (
                isinstance(new, Success) and new.unwrap().chisqr <= old.unwrap().chisqr
            ):
                worse.append((case.name, inset))
    assert worse == []


# Plateau ranges labs set on % layers (CDD 76918's, PRT-00006's).
_BOUNDED_EC50_EC90 = DoseResponseConfig(
    curve_type=CurveType.EC50,
    y_readout_name="% Inhibition",
    intercepts=(InterceptSpec(InterceptKind.EC, 50), InterceptSpec(InterceptKind.EC, 90)),
    bottom_constraint_min=-10.0,
    bottom_constraint_max=10.0,
    top_constraint_min=90.0,
    top_constraint_max=110.0,
)
# CDD 76918 (Mtb WCA Resazurin), row 1153888750: a clean step between 3.125 and 6.25 µM (CDD
# EC50 5.43). The bottom plateau sits below its range, so the fit ends with it on -10.
_CDD_76918_1153888750 = [
    (0.0244140625, -8.72), (0.048828125, -22.05), (0.09765625, -18.79), (0.1953125, -16.63),
    (0.390625, -32.17), (0.78125, -19.75), (1.5625, -15.51), (3.125, -8.1), (6.25, 73.02),
    (12.5, 102.03), (25.0, 102.23), (50.0, 102.29),
]  # fmt: skip
# PRT-00006 CC-000975 and CC-000980: no inhibition at any dose, flat around -10 %.
_CC_000975 = [
    (0.2, 8.89), (0.4, -12.12), (1.0, 0.13), (1.5, -6.66), (3.0, -22.82), (6.0, -13.85),
    (13.0, -19.37), (25.0, -13.95), (50.0, -19.05), (100.0, -11.5),
]  # fmt: skip
_CC_000980 = [
    (0.2, -4.52), (0.4, -10.05), (1.0, -11.71), (1.5, -2.3), (3.0, -21.08), (6.0, -14.03),
    (13.0, -15.85), (25.0, -4.1), (50.0, -10.69), (100.0, -0.86),
]  # fmt: skip


def test_a_bounded_fit_whose_plateau_ends_on_its_bound_is_kept():
    """leastsq stops with the bottom on its bound, unable to refine it further, and so cannot
    estimate error bars. The fit is still the curve's best: it is kept, with no CI."""
    fitted = (
        LmfitCurveFitter()
        .fit(_points(_CDD_76918_1153888750), _BOUNDED_EC50_EC90, ResponseScale())
        .unwrap()
    )
    assert fitted.curve_class == CurveClass.FULL
    ec50 = fitted.intercept_values[0]
    assert ec50.qualifier == ValueQualifier.EQ
    assert 3.125 < ec50.value < 6.25


# PRT-00216 CC-061262: rising 38 -> ~100 % (R² 0.97). Free plateaus: the optimizer may return
# the curve with its plateaus named the other way round (top 15, bottom 99, Hill -1.49).
_CC_061262 = [
    (0.005080526342529086, 38.14), (0.015241579027587259, 71.73), (0.04572473708276177, 87.44),
    (0.13717421124828533, 105.79), (0.411522633744856, 99.59), (1.2345679012345678, 97.65),
    (3.7037037037037037, 100.34), (11.11111111111111, 96.02), (33.333333333333336, 99.97),
    (100.0, 96.24),
]  # fmt: skip
# CDD 26279 (yeast cytotoxicity, % of control), row 157278680: noise around 100 % that the fit
# reads as a slight fall; the optimizer returns it with its plateaus named the other way round.
_CDD_26279_157278680 = [
    (0.012207031, 85.94), (0.024414063, 103.19), (0.048828125, 106.94), (0.09765625, 104.68),
    (0.1953125, 114.28), (0.390625, 113.42), (0.78125, 92.18), (1.5625, 86.56), (3.125, 100.31),
    (6.25, 86.05), (12.5, 107.68), (25.0, 116.33), (50.0, 100.88), (100.0, 85.18),
]  # fmt: skip


def test_a_curve_is_read_with_top_as_its_upper_plateau():
    """(top, bottom, Hill) and (bottom, top, -Hill) are the same 4PL; the fitter returns the
    one whose top is the upper plateau, so the class reads it as such."""
    config = DoseResponseConfig(curve_type=CurveType.IC50, y_readout_name="% Inhibition")
    fitted = LmfitCurveFitter().fit(_points(_CC_061262), config).unwrap()
    assert fitted.top > fitted.bottom
    assert fitted.hill_slope > 0
    assert fitted.curve_class == CurveClass.FULL
    assert 0.005 < fitted.fitted_value < 0.016


def test_a_falling_curve_is_read_with_top_as_its_upper_plateau():
    config = DoseResponseConfig(
        curve_type=CurveType.IC50,
        y_readout_name="% Control",
        intercepts=(InterceptSpec(InterceptKind.IC, 50), InterceptSpec(InterceptKind.IC, 90)),
    )
    fitted = LmfitCurveFitter().fit(_points(_CDD_26279_157278680), config).unwrap()
    assert fitted.top > fitted.bottom
    assert fitted.hill_slope < 0
    # Relative levels are measured from the bottom plateau (today's rule), so on this falling
    # curve IC90 lies at a lower dose than IC50.
    ic50, ic90 = fitted.intercept_values
    assert ic90.value < ic50.value


@pytest.mark.parametrize("series", [_CC_000975, _CC_000980], ids=["CC-000975", "CC-000980"])
def test_a_flat_bounded_curve_whose_plateau_ends_on_its_bound_reads_inactive(series):
    """Inactive reads "> highest dose" whatever its intercepts store (the class wins)."""
    fitted = LmfitCurveFitter().fit(_points(series), _BOUNDED_EC50_EC90, ResponseScale()).unwrap()
    assert fitted.curve_class == CurveClass.INACTIVE


# ──────────────────────────────────────────────────────────────────────────
# Intercepts read against the tested doses; "Active at all doses"
# ──────────────────────────────────────────────────────────────────────────

_EC50_EC90 = DoseResponseConfig(
    curve_type=CurveType.EC50,
    y_readout_name="% Inhibition",
    intercepts=(InterceptSpec(InterceptKind.EC, 50), InterceptSpec(InterceptKind.EC, 90)),
)


# Known misreadings, kept visible: on 6-10 points at noise SD 8 the free fit puts a plateau far
# past the data (bottom -367 from points at 10; plateaus at ±4000; top 197 from points at 109),
# so the 50 % level of that window lies outside every response and reads "< lowest dose",
# active at all doses. Today they show equally wrong exact EC50s far below the doses.
_EXTRAPOLATED_PLATEAUS = {
    "rise-full-inside-h0.5-3dec6-sd8",
    "fall-partial-inside-h1-3dec6-sd8",
    "fall-partial-inside-h0.5-4dec10-sd8",
}


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            c,
            id=c.name,
            marks=pytest.mark.xfail(
                c.name in _EXTRAPOLATED_PLATEAUS,
                reason="relative target on plateaus extrapolated past the data",
                strict=True,
            ),
        )
        for c in GRID
    ],
)
def test_intercepts_and_class_follow_the_generating_curve_on_grid(case):
    scale = ResponseScale(*case.scale) if case.scale else None
    fitted = LmfitCurveFitter().fit(case.points(), _EC50_EC90, scale).unwrap()
    lo, hi = case.doses[0], case.doses[-1]

    assert fitted.top >= fitted.bottom
    assert fitted.curve_class in case.expected_class
    ec50, ec90 = fitted.intercept_values
    for iv, expected, offset in (
        (ec50, case.expected_ec50, 0.0),
        (ec90, case.expected_ec90, math.log10(9.0) / case.hill),
    ):
        assert iv.qualifier in expected
        assert iv.at_bound == (iv.qualifier == ValueQualifier.GT)
        if iv.qualifier == ValueQualifier.LT:
            assert iv.value == lo
        elif iv.qualifier == ValueQualifier.GT:
            assert iv.value == hi
        elif iv.qualifier == ValueQualifier.ND:
            assert math.isnan(iv.value)
        elif scale is not None:
            assert lo <= iv.value <= hi
        if case.noise_sd == 0 and expected == {ValueQualifier.EQ} and case.position == "inside":
            # Exact data: the crossing is the generating curve's own.
            assert math.log10(iv.value) == pytest.approx(case.log_ec50 + offset, abs=0.05)

    # fitted_value keeps its meaning: the primary's value when exact, else the fitted midpoint
    # (0.0 on the inactive fast path); never a bound dose.
    if ec50.qualifier == ValueQualifier.EQ:
        assert fitted.fitted_value == ec50.value
    else:
        assert math.isfinite(fitted.fitted_value)
        assert fitted.fitted_value not in (lo, hi)


# The two compounds of the WCA_DHFR plate that inhibit 85-100 % at every dose (µM, %).
_SACC_0428730 = [
    (0.0002, 85.67), (0.0004, 86.06), (0.001, 85.27), (0.0015, 87.3), (0.003, 91.47),
    (0.0065, 91.5), (0.0125, 92.35), (0.025, 92.39), (0.05, 90.12), (0.1, 91.61), (0.2, 92.57),
    (0.4, 92.47), (1.0, 92.98), (1.5, 90.96), (3.0, 93.66), (6.5, 92.49), (12.5, 93.36),
    (25.0, 91.53), (50.0, 88.4), (100.0, 100.94),
]  # fmt: skip
_SACC_0519396 = [
    (0.0002, 92.35), (0.0004, 91.23), (0.001, 90.72), (0.0015, 91.38), (0.003, 91.62),
    (0.0065, 87.93), (0.0125, 90.12), (0.025, 92.7), (0.05, 95.01), (0.1, 95.01), (0.2, 94.3),
    (0.4, 95.48), (1.0, 91.6), (1.5, 93.02), (3.0, 92.24), (6.5, 97.53), (12.5, 100.05),
    (25.0, 101.73), (50.0, 99.45), (100.0, 98.32),
]  # fmt: skip


def _points(series):
    return [ConcentrationResponsePoint(concentration=c, response=r) for c, r in series]


@pytest.mark.parametrize("series", [_SACC_0428730, _SACC_0519396], ids=["0428730", "0519396"])
def test_wca_flat_compounds_are_active_at_all_doses(series):
    fitted = LmfitCurveFitter().fit(_points(series), _EC50_EC90, ResponseScale()).unwrap()
    assert fitted.curve_class == CurveClass.ACTIVE_ALL_DOSES
    ec50, ec90 = fitted.intercept_values
    assert (ec50.qualifier, ec50.value) == (ValueQualifier.LT, 0.0002)
    assert not ec50.at_bound
    # EC90 (90 % on the scale) is read off the fitted band: below it at the lowest dose
    # ("<"), or inside it ("n.d.").
    band = (min(fitted.top, fitted.bottom), max(fitted.top, fitted.bottom))
    assert ec90.qualifier == (ValueQualifier.LT if band[0] >= 90 else ValueQualifier.ND)


@pytest.mark.parametrize("series", [_SACC_0428730, _SACC_0519396], ids=["0428730", "0519396"])
def test_a_flat_curve_without_a_scale_keeps_todays_intercepts(series):
    """Raw-signal and Z-score layers have no scale to judge a flat line by: its intercepts are
    the fitted curve's own crossings, as before, and it is never "active at all doses"."""
    fitted = LmfitCurveFitter().fit(_points(series), _EC50_EC90).unwrap()
    assert fitted.curve_class in (CurveClass.INACTIVE, CurveClass.PARTIAL)
    assert [iv.qualifier for iv in fitted.intercept_values] == [ValueQualifier.EQ] * 2
    assert fitted.fitted_value == fitted.intercept_values[0].value


@pytest.mark.parametrize("scale", [None, ResponseScale()], ids=["no-scale", "percent"])
def test_the_inactive_fast_path_reads_above_the_highest_dose(scale):
    points = [
        ConcentrationResponsePoint(concentration=10.0**-i, response=5.0 + (i % 3))
        for i in range(8)
    ]
    fitted = LmfitCurveFitter().fit(points, _EC50_EC90, scale).unwrap()
    assert fitted.curve_class == CurveClass.INACTIVE
    assert fitted.fitted_value == 0.0
    assert [
        (iv.qualifier, iv.value, iv.at_bound, iv.confidence_interval_low)
        for iv in fitted.intercept_values
    ] == [(ValueQualifier.GT, 1.0, True, None)] * 2


def test_a_bell_shaped_series_keeps_todays_class_and_reads_its_intercepts_on_the_fit():
    """Rising to ~94 % then falling back to ~27 %: the 4PL fits one direction (it cannot
    turn), so the class comes from today's R² / plateau rules (R² 0.52: inactive), never
    "bell_shaped" from the fit, and its intercepts follow the censoring rules on that fitted
    curve, which crosses both levels inside the doses."""
    log_doses = np.linspace(-3, 2, 11)
    rise = 90.0 / (1.0 + 10.0 ** ((-2.0 - log_doses) * 1.5))
    fall = 70.0 / (1.0 + 10.0 ** ((1.0 - log_doses) * 1.5))
    series = list(zip(10.0**log_doses, rise - fall + 5.0, strict=True))
    fitted = LmfitCurveFitter().fit(_points(series), _EC50_EC90, ResponseScale()).unwrap()
    assert fitted.curve_class == CurveClass.INACTIVE
    assert [iv.qualifier for iv in fitted.intercept_values] == [ValueQualifier.EQ] * 2


def test_a_response_scale_needs_a_direction():
    from cellar.domain.shared.errors import ValidationError as VE

    with pytest.raises(VE, match="full must differ from zero"):
        ResponseScale(zero=50.0, full=50.0)
