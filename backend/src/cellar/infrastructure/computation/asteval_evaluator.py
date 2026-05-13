"""Asteval-backed formula evaluator.

Uses ``asteval.Interpreter(minimal=True)`` so that only an explicit whitelist of
math symbols is available — no builtins, no ``import``, no ``exec``.

Bracket syntax: cellar readout names can contain spaces (e.g. "Raw AU"),
which aren't valid Python identifiers. Formulas reference space-containing
readouts via ``[Name With Spaces]``. A preprocess pass before evaluation
swaps each ``[X]`` for a sanitized alias and re-keys the bindings dict so
asteval sees only standard identifiers.
"""

from __future__ import annotations

import math
import re
from typing import Any

import asteval

from cellar.domain.screening_assay.formula_evaluator import FormulaValidationError

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

# Bracket-wrapped reference: `[Name With Spaces]`. Empty content (`[]`) is
# disallowed at preprocess time. The regex deliberately doesn't try to be
# clever about nesting — readout names don't contain `[` or `]`, so a
# greedy non-`]` match is safe.
_BRACKET_REF_RE = re.compile(r"\[([^\[\]]+?)\]")


def _expand_brackets(
    formula: str,
    bindings: dict[str, float],
) -> tuple[str, dict[str, float]]:
    """Replace ``[Name With Spaces]`` references with sanitized aliases.

    Returns a ``(rewritten_formula, expanded_bindings)`` pair. The expanded
    bindings include the original entries unchanged plus an alias entry
    for each bracketed name that exists in the input bindings. Bracketed
    names that aren't in bindings get an alias entry too — pointing to a
    sentinel that asteval will see as undefined, producing the standard
    "Undefined variable" error path with the alias swapped back to the
    original bracketed name in the message.

    Unbalanced brackets (a `[` without a matching `]`) are left in place
    and asteval will surface a syntax error on them.
    """
    if "[" not in formula:
        return formula, bindings

    aliases: dict[str, str] = {}  # original name -> alias
    expanded: dict[str, float] = dict(bindings)

    def _replace(m: "re.Match[str]") -> str:
        name = m.group(1).strip()
        if not name:
            # Empty `[]` is invalid — leave the original text so asteval
            # raises a syntax error.
            return m.group(0)
        if name in aliases:
            return aliases[name]
        alias = f"_v{len(aliases)}"
        aliases[name] = alias
        if name in bindings:
            expanded[alias] = bindings[name]
        # If the name isn't in bindings, the alias stays unbound and
        # asteval will report it as undefined — caught downstream and
        # surfaced through `_extract_undefined_variables` (which we
        # post-process to swap aliases back to bracketed names so the
        # error message reads naturally).
        return alias

    rewritten = _BRACKET_REF_RE.sub(_replace, formula)
    # Stash the alias->name reverse map on the function via a tuple so
    # callers can map errors back to the user-facing names. We return it
    # as a third element only when we actually rewrote something —
    # callers branch on whether rewriting happened anyway.
    expanded["__cellar_alias_map__"] = aliases  # type: ignore[assignment]
    return rewritten, expanded


def _unswap_alias_in_message(message: str, aliases: dict[str, str]) -> str:
    """If `message` mentions any of our alias identifiers, swap them back
    to the original bracketed name for a chemist-friendly error."""
    if not aliases:
        return message
    for original_name, alias in aliases.items():
        if alias in message:
            message = message.replace(alias, f"[{original_name}]")
    return message


def _swap_aliases_in_undefined(undefined: list[str], aliases: dict[str, str]) -> list[str]:
    """Swap aliases back to user-facing bracketed names in the undefined
    variable list."""
    if not aliases:
        return undefined
    reverse: dict[str, str] = {alias: name for name, alias in aliases.items()}
    return [f"[{reverse[v]}]" if v in reverse else v for v in undefined]


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

        rewritten, expanded = _expand_brackets(stripped, bindings)
        # Pop the alias map off so we don't leak it into asteval's symtable.
        aliases: dict[str, str] = expanded.pop(
            "__cellar_alias_map__",
            {},  # type: ignore[arg-type]
        )

        interp = _make_interpreter()
        interp.symtable.update(expanded)

        result = interp(rewritten)

        if interp.error:
            # Classify the first error
            first = interp.error[0]
            exc_type = first.exc

            if exc_type is ZeroDivisionError:
                raise FormulaValidationError(formula, "Division by zero")

            undefined = _extract_undefined_variables(interp.error)
            if undefined:
                user_facing = _swap_aliases_in_undefined(undefined, aliases)
                raise FormulaValidationError(
                    formula,
                    f"Undefined variable(s): {', '.join(user_facing)}",
                    undefined_variables=user_facing,
                )

            raise FormulaValidationError(formula, _unswap_alias_in_message(first.msg, aliases))

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

        dummy_bindings: dict[str, float] = {var: 1.0 for var in available_variables}
        rewritten, expanded = _expand_brackets(stripped, dummy_bindings)
        aliases: dict[str, str] = expanded.pop(
            "__cellar_alias_map__",
            {},  # type: ignore[arg-type]
        )

        interp = _make_interpreter()
        interp.symtable.update(expanded)

        result = interp(rewritten)

        if interp.error:
            first = interp.error[0]

            undefined = _extract_undefined_variables(interp.error)
            if undefined:
                undefined = _swap_aliases_in_undefined(undefined, aliases)
                raise FormulaValidationError(
                    formula,
                    f"Undefined variable(s): {', '.join(undefined)}",
                    undefined_variables=undefined,
                )

            raise FormulaValidationError(formula, _unswap_alias_in_message(first.msg, aliases))

        # A None result here could mean division by zero with all-1.0 inputs
        # (e.g. `x - x`). That's still a syntactically valid formula, so we
        # only reject None when it accompanies errors (already handled above).
        _ = result  # noqa: F841
