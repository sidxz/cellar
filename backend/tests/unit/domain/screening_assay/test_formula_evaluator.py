"""Tests for FormulaEvaluator protocol + AstevalFormulaEvaluator implementation."""

from __future__ import annotations

import math

import pytest

from chem_vault.domain.screening_assay.formula_evaluator import (
    FormulaEvaluator,
    FormulaValidationError,
)
from chem_vault.infrastructure.computation.asteval_evaluator import AstevalFormulaEvaluator


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_asteval_evaluator_satisfies_protocol():
    """AstevalFormulaEvaluator must satisfy the FormulaEvaluator Protocol at runtime."""
    evaluator = AstevalFormulaEvaluator()
    assert isinstance(evaluator, FormulaEvaluator)


# ---------------------------------------------------------------------------
# TestFormulaExecution
# ---------------------------------------------------------------------------


class TestFormulaExecution:
    """Tests for AstevalFormulaEvaluator.run()."""

    def setup_method(self):
        self.ev = AstevalFormulaEvaluator()

    # --- happy-path arithmetic ---

    def test_simple_addition(self):
        assert self.ev.run("a + b", {"a": 3.0, "b": 4.0}) == pytest.approx(7.0)

    def test_simple_multiplication(self):
        assert self.ev.run("a * b", {"a": 6.0, "b": 7.0}) == pytest.approx(42.0)

    def test_float_division(self):
        assert self.ev.run("x / y", {"x": 10.0, "y": 4.0}) == pytest.approx(2.5)

    def test_literal_expression(self):
        assert self.ev.run("42.0", {}) == pytest.approx(42.0)

    # --- domain-relevant formulas ---

    def test_percent_inhibition_formula(self):
        """(pos_control - signal) / (pos_control - neg_control) * 100"""
        result = self.ev.run(
            "(pos_control - signal) / (pos_control - neg_control) * 100",
            {"pos_control": 100.0, "signal": 50.0, "neg_control": 0.0},
        )
        assert result == pytest.approx(50.0)

    def test_z_score_formula(self):
        result = self.ev.run(
            "(value - mean) / std_dev",
            {"value": 10.0, "mean": 5.0, "std_dev": 2.5},
        )
        assert result == pytest.approx(2.0)

    # --- math functions ---

    def test_log10(self):
        assert self.ev.run("log10(x)", {"x": 100.0}) == pytest.approx(2.0)

    def test_log_natural(self):
        assert self.ev.run("log(x)", {"x": math.e}) == pytest.approx(1.0)

    def test_log2(self):
        assert self.ev.run("log2(x)", {"x": 8.0}) == pytest.approx(3.0)

    def test_sqrt(self):
        assert self.ev.run("sqrt(x)", {"x": 9.0}) == pytest.approx(3.0)

    def test_abs(self):
        assert self.ev.run("abs(x)", {"x": -5.0}) == pytest.approx(5.0)

    def test_min_max(self):
        assert self.ev.run("min(a, b)", {"a": 3.0, "b": 7.0}) == pytest.approx(3.0)
        assert self.ev.run("max(a, b)", {"a": 3.0, "b": 7.0}) == pytest.approx(7.0)

    def test_exp(self):
        assert self.ev.run("exp(x)", {"x": 0.0}) == pytest.approx(1.0)

    def test_pi_constant(self):
        assert self.ev.run("pi * r * r", {"r": 1.0}) == pytest.approx(math.pi)

    def test_e_constant(self):
        assert self.ev.run("e", {}) == pytest.approx(math.e)

    # --- complex / nested expressions ---

    def test_complex_expression(self):
        """Nested arithmetic similar to an IC50 normalisation."""
        result = self.ev.run(
            "100 * (1 - (signal - low) / (high - low))",
            {"signal": 60.0, "low": 10.0, "high": 110.0},
        )
        assert result == pytest.approx(50.0)

    def test_nested_math_functions(self):
        assert self.ev.run("log10(sqrt(x))", {"x": 100.0}) == pytest.approx(1.0)

    # --- error cases ---

    def test_division_by_zero_raises(self):
        with pytest.raises(FormulaValidationError):
            self.ev.run("1 / 0", {})

    def test_undefined_variable_raises(self):
        with pytest.raises(FormulaValidationError) as exc_info:
            self.ev.run("x + y", {"x": 1.0})
        assert "y" in exc_info.value.undefined_variables

    def test_syntax_error_raises(self):
        with pytest.raises(FormulaValidationError):
            self.ev.run("((x + 1", {"x": 1.0})

    def test_empty_formula_raises(self):
        with pytest.raises(FormulaValidationError):
            self.ev.run("", {})

    def test_whitespace_only_formula_raises(self):
        with pytest.raises(FormulaValidationError):
            self.ev.run("   ", {})

    def test_variable_division_by_zero_raises(self):
        """Division by a zero-valued variable should also raise."""
        with pytest.raises(FormulaValidationError):
            self.ev.run("a / b", {"a": 5.0, "b": 0.0})


# ---------------------------------------------------------------------------
# TestFormulaValidation
# ---------------------------------------------------------------------------


class TestFormulaValidation:
    """Tests for AstevalFormulaEvaluator.validate()."""

    def setup_method(self):
        self.ev = AstevalFormulaEvaluator()

    def test_valid_formula_returns_none(self):
        result = self.ev.validate(
            "signal / control * 100",
            ["signal", "control"],
        )
        assert result is None

    def test_undefined_variable_in_validate(self):
        with pytest.raises(FormulaValidationError) as exc_info:
            self.ev.validate(
                "signal / mystery * 100",
                ["signal", "control"],
            )
        assert "mystery" in exc_info.value.undefined_variables

    def test_syntax_error_in_validate(self):
        with pytest.raises(FormulaValidationError):
            self.ev.validate("x * * y", ["x", "y"])

    def test_math_functions_allowed_in_validate(self):
        # Should not raise
        self.ev.validate(
            "log10(signal) - log10(background)",
            ["signal", "background"],
        )

    def test_empty_formula_in_validate(self):
        with pytest.raises(FormulaValidationError):
            self.ev.validate("", ["x"])

    def test_no_variables_formula(self):
        """A formula using only constants and math symbols should validate fine."""
        # Should not raise
        self.ev.validate("pi * 2", [])

    def test_multiple_undefined_variables_captured(self):
        with pytest.raises(FormulaValidationError) as exc_info:
            self.ev.validate("a + b + c", ["a"])
        err = exc_info.value
        # At least one of the undefined vars is detected
        # (asteval stops at the first NameError, so we may see b or c)
        assert len(err.undefined_variables) >= 1
        assert err.undefined_variables[0] in ("b", "c")
