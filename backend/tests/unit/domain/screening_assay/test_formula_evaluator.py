"""Tests for FormulaEvaluator protocol + AstevalFormulaEvaluator implementation."""

from __future__ import annotations

import math

import pytest
from returns.pipeline import is_successful
from returns.result import Failure

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
        result = self.ev.run("a + b", {"a": 3.0, "b": 4.0})
        assert is_successful(result)
        assert result.unwrap() == pytest.approx(7.0)

    def test_simple_multiplication(self):
        result = self.ev.run("a * b", {"a": 6.0, "b": 7.0})
        assert is_successful(result)
        assert result.unwrap() == pytest.approx(42.0)

    def test_float_division(self):
        result = self.ev.run("x / y", {"x": 10.0, "y": 4.0})
        assert is_successful(result)
        assert result.unwrap() == pytest.approx(2.5)

    def test_literal_expression(self):
        result = self.ev.run("42.0", {})
        assert is_successful(result)
        assert result.unwrap() == pytest.approx(42.0)

    # --- domain-relevant formulas ---

    def test_percent_inhibition_formula(self):
        """(pos_control - signal) / (pos_control - neg_control) * 100"""
        result = self.ev.run(
            "(pos_control - signal) / (pos_control - neg_control) * 100",
            {"pos_control": 100.0, "signal": 50.0, "neg_control": 0.0},
        )
        assert is_successful(result)
        assert result.unwrap() == pytest.approx(50.0)

    def test_z_score_formula(self):
        result = self.ev.run(
            "(value - mean) / std_dev",
            {"value": 10.0, "mean": 5.0, "std_dev": 2.5},
        )
        assert is_successful(result)
        assert result.unwrap() == pytest.approx(2.0)

    # --- math functions ---

    def test_log10(self):
        result = self.ev.run("log10(x)", {"x": 100.0})
        assert is_successful(result)
        assert result.unwrap() == pytest.approx(2.0)

    def test_log_natural(self):
        result = self.ev.run("log(x)", {"x": math.e})
        assert is_successful(result)
        assert result.unwrap() == pytest.approx(1.0)

    def test_log2(self):
        result = self.ev.run("log2(x)", {"x": 8.0})
        assert is_successful(result)
        assert result.unwrap() == pytest.approx(3.0)

    def test_sqrt(self):
        result = self.ev.run("sqrt(x)", {"x": 9.0})
        assert is_successful(result)
        assert result.unwrap() == pytest.approx(3.0)

    def test_abs(self):
        result = self.ev.run("abs(x)", {"x": -5.0})
        assert is_successful(result)
        assert result.unwrap() == pytest.approx(5.0)

    def test_min_max(self):
        result_min = self.ev.run("min(a, b)", {"a": 3.0, "b": 7.0})
        result_max = self.ev.run("max(a, b)", {"a": 3.0, "b": 7.0})
        assert result_min.unwrap() == pytest.approx(3.0)
        assert result_max.unwrap() == pytest.approx(7.0)

    def test_exp(self):
        result = self.ev.run("exp(x)", {"x": 0.0})
        assert is_successful(result)
        assert result.unwrap() == pytest.approx(1.0)

    def test_pi_constant(self):
        result = self.ev.run("pi * r * r", {"r": 1.0})
        assert is_successful(result)
        assert result.unwrap() == pytest.approx(math.pi)

    def test_e_constant(self):
        result = self.ev.run("e", {})
        assert is_successful(result)
        assert result.unwrap() == pytest.approx(math.e)

    # --- complex / nested expressions ---

    def test_complex_expression(self):
        """Nested arithmetic similar to an IC50 normalisation."""
        result = self.ev.run(
            "100 * (1 - (signal - low) / (high - low))",
            {"signal": 60.0, "low": 10.0, "high": 110.0},
        )
        assert is_successful(result)
        assert result.unwrap() == pytest.approx(50.0)

    def test_nested_math_functions(self):
        result = self.ev.run("log10(sqrt(x))", {"x": 100.0})
        assert is_successful(result)
        assert result.unwrap() == pytest.approx(1.0)

    # --- error cases ---

    def test_division_by_zero_returns_failure(self):
        result = self.ev.run("1 / 0", {})
        assert not is_successful(result)
        assert isinstance(result.failure(), FormulaValidationError)

    def test_undefined_variable_returns_failure(self):
        result = self.ev.run("x + y", {"x": 1.0})
        assert not is_successful(result)
        err = result.failure()
        assert isinstance(err, FormulaValidationError)
        assert "y" in err.undefined_variables

    def test_syntax_error_returns_failure(self):
        result = self.ev.run("((x + 1", {"x": 1.0})
        assert not is_successful(result)
        err = result.failure()
        assert isinstance(err, FormulaValidationError)

    def test_empty_formula_returns_failure(self):
        result = self.ev.run("", {})
        assert not is_successful(result)
        assert isinstance(result.failure(), FormulaValidationError)

    def test_whitespace_only_formula_returns_failure(self):
        result = self.ev.run("   ", {})
        assert not is_successful(result)
        assert isinstance(result.failure(), FormulaValidationError)

    def test_variable_division_by_zero_returns_failure(self):
        """Division by a zero-valued variable should also fail."""
        result = self.ev.run("a / b", {"a": 5.0, "b": 0.0})
        assert not is_successful(result)
        assert isinstance(result.failure(), FormulaValidationError)


# ---------------------------------------------------------------------------
# TestFormulaValidation
# ---------------------------------------------------------------------------


class TestFormulaValidation:
    """Tests for AstevalFormulaEvaluator.validate()."""

    def setup_method(self):
        self.ev = AstevalFormulaEvaluator()

    def test_valid_formula_returns_success(self):
        result = self.ev.validate(
            "signal / control * 100",
            ["signal", "control"],
        )
        assert is_successful(result)
        assert result.unwrap() is None

    def test_undefined_variable_in_validate(self):
        result = self.ev.validate(
            "signal / mystery * 100",
            ["signal", "control"],
        )
        assert not is_successful(result)
        err = result.failure()
        assert isinstance(err, FormulaValidationError)
        assert "mystery" in err.undefined_variables

    def test_syntax_error_in_validate(self):
        result = self.ev.validate("x * * y", ["x", "y"])
        assert not is_successful(result)
        assert isinstance(result.failure(), FormulaValidationError)

    def test_math_functions_allowed_in_validate(self):
        result = self.ev.validate(
            "log10(signal) - log10(background)",
            ["signal", "background"],
        )
        assert is_successful(result)

    def test_empty_formula_in_validate(self):
        result = self.ev.validate("", ["x"])
        assert not is_successful(result)
        assert isinstance(result.failure(), FormulaValidationError)

    def test_no_variables_formula(self):
        """A formula using only constants and math symbols should validate fine."""
        result = self.ev.validate("pi * 2", [])
        assert is_successful(result)

    def test_multiple_undefined_variables_captured(self):
        result = self.ev.validate("a + b + c", ["a"])
        assert not is_successful(result)
        err = result.failure()
        assert isinstance(err, FormulaValidationError)
        # At least one of the undefined vars is detected
        # (asteval stops at the first NameError, so we may see b or c)
        assert len(err.undefined_variables) >= 1
        assert err.undefined_variables[0] in ("b", "c")
