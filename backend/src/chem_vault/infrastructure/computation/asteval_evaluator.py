"""Asteval-backed formula evaluator.

Uses ``asteval.Interpreter(minimal=True)`` so that only an explicit whitelist of
math symbols is available — no builtins, no ``import``, no ``exec``.
"""

from __future__ import annotations

import math
import re
from typing import Any

import asteval

from chem_vault.domain.screening_assay.formula_evaluator import FormulaValidationError

# ---------------------------------------------------------------------------
# Whitelisted math symbols injected into every interpreter instance
# ---------------------------------------------------------------------------

_MATH_SYMBOLS: dict[str, Any] = {
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "sqrt": math.sqrt,
    "abs": abs,
    "pow": pow,
    "min": min,
    "max": max,
    "round": round,
    "exp": math.exp,
    "pi": math.pi,
    "e": math.e,
}

# Regex to extract variable names from asteval NameError messages such as
# "name 'foo' is not defined"
_UNDEFINED_VAR_RE = re.compile(r"name '(\w+)' is not defined")


def _make_interpreter() -> asteval.Interpreter:
    """Create a fresh minimal interpreter pre-loaded with whitelisted symbols."""
    interp = asteval.Interpreter(minimal=True)
    interp.symtable.update(_MATH_SYMBOLS)
    return interp


def _extract_undefined_variables(errors: list[Any]) -> list[str]:
    """Pull undefined variable names out of a list of ExceptionHolder objects."""
    undefined: list[str] = []
    for holder in errors:
        if holder.exc is NameError:
            match = _UNDEFINED_VAR_RE.search(holder.msg)
            if match:
                name = match.group(1)
                # Skip whitelisted symbols reported as undefined (shouldn't happen,
                # but guard against it)
                if name not in _MATH_SYMBOLS:
                    undefined.append(name)
    return undefined


class AstevalFormulaEvaluator:
    """Stateless formula evaluator backed by asteval.

    Implements the ``FormulaEvaluator`` protocol from the domain layer.
    """

    def run(
        self,
        formula: str,
        bindings: dict[str, float],
    ) -> float:
        """Evaluate *formula* with the provided variable *bindings*.

        Raises FormulaValidationError on:
        - Empty formula
        - Syntax errors
        - Undefined variables
        - Division by zero
        - Non-numeric result (None or non-float)
        """
        stripped = formula.strip()
        if not stripped:
            raise FormulaValidationError(formula, "Formula must not be empty")

        interp = _make_interpreter()
        interp.symtable.update(bindings)

        result = interp(stripped)

        if interp.error:
            # Classify the first error
            first = interp.error[0]
            exc_type = first.exc

            if exc_type is ZeroDivisionError:
                raise FormulaValidationError(formula, "Division by zero")

            undefined = _extract_undefined_variables(interp.error)
            if undefined:
                raise FormulaValidationError(
                    formula,
                    f"Undefined variable(s): {', '.join(undefined)}",
                    undefined_variables=undefined,
                )

            raise FormulaValidationError(formula, first.msg)

        if result is None:
            raise FormulaValidationError(formula, "Formula produced no result")

        if not isinstance(result, (int, float)):
            raise FormulaValidationError(
                formula,
                f"Formula must return a numeric value, got {type(result).__name__}",
            )

        float_result = float(result)
        if math.isnan(float_result) or math.isinf(float_result):
            raise FormulaValidationError(
                formula,
                f"Formula produced a non-finite value: {float_result}",
            )

        return float_result

    def validate(
        self,
        formula: str,
        available_variables: list[str],
    ) -> None:
        """Validate *formula* without real data by substituting 1.0 for each variable.

        Raises:
            FormulaValidationError with ``undefined_variables`` populated
                if any variable referenced in the formula is not in *available_variables*.
        """
        stripped = formula.strip()
        if not stripped:
            raise FormulaValidationError(formula, "Formula must not be empty")

        dummy_bindings = {var: 1.0 for var in available_variables}
        interp = _make_interpreter()
        interp.symtable.update(dummy_bindings)

        result = interp(stripped)

        if interp.error:
            first = interp.error[0]

            undefined = _extract_undefined_variables(interp.error)
            if undefined:
                raise FormulaValidationError(
                    formula,
                    f"Undefined variable(s): {', '.join(undefined)}",
                    undefined_variables=undefined,
                )

            raise FormulaValidationError(formula, first.msg)

        # A None result here could mean division by zero with all-1.0 inputs
        # (e.g. `x - x`). That's still a syntactically valid formula, so we
        # only reject None when it accompanies errors (already handled above).
        _ = result  # noqa: F841
