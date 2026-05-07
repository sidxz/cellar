"""Tests for LmfitCurveFitter — 4PL Hill equation fitting."""

from __future__ import annotations

import random

import pytest
from returns.result import Failure, Success

from chem_vault.domain.screening_assay.curve_fitting import ConcentrationResponsePoint
from chem_vault.domain.screening_assay.dose_response_config import DoseResponseConfig
from chem_vault.domain.screening_assay.enums import (
    CurveClass,
    CurveType,
    HillSlopeConstraint,
)
from chem_vault.infrastructure.lmfit.curve_fitter import LmfitCurveFitter


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
        """
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
        )
        fitted = self.fitter.fit(points, cfg).unwrap()
        assert 55.0 <= fitted.fitted_value <= 90.0, (
            f"IC50 {fitted.fitted_value} outside acceptance band [55, 90] µM"
        )
        assert fitted.r_squared > 0.95
        assert 0.9 <= fitted.hill_slope <= 1.1

    def test_lock_and_range_mutually_exclusive_at_construction(self):
        """Domain-layer ValidationError, not a runtime fitter error."""
        from chem_vault.domain.shared.errors import ValidationError as VE

        with pytest.raises(VE, match="top_constraint"):
            _config_with_ranges(top_constraint=100.0, top_constraint_min=85.0)

    def test_range_min_greater_than_max_rejected_at_construction(self):
        from chem_vault.domain.shared.errors import ValidationError as VE

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
        from chem_vault.domain.shared.errors import ValidationError as VE

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

    def test_default_3sigma_removes_clear_outlier(self):
        points = self._points_with_one_clear_outlier()
        cfg = _config_with_ranges()
        fitted = self.fitter.fit(points, cfg).unwrap()
        auto_excluded = [
            p for p in fitted.excluded_points if p.get("reason") == "auto_3sigma"
        ]
        assert len(auto_excluded) == 1, (
            f"expected 1 auto-excluded outlier, got {len(auto_excluded)}"
        )

    def test_outlier_sigma_none_disables_removal(self):
        points = self._points_with_one_clear_outlier()
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="Concentration",
            y_readout_name="% Inhibition",
            outlier_sigma=None,
        )
        fitted = self.fitter.fit(points, cfg).unwrap()
        auto_excluded = [
            p for p in fitted.excluded_points if p.get("reason") == "auto_3sigma"
        ]
        assert auto_excluded == [], (
            "outlier_sigma=None must disable auto-removal entirely"
        )

    def test_outlier_sigma_must_be_positive(self):
        from chem_vault.domain.shared.errors import ValidationError as VE

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
