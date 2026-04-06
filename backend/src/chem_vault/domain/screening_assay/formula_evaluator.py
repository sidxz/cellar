"""FormulaEvaluator protocol — domain-layer abstraction over formula computation.

The protocol lives in the domain so application-layer services can depend on it.
The concrete implementation (AstevalFormulaEvaluator) lives in infrastructure.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from returns.result import Result

from chem_vault.domain.shared.errors import DomainError, ValidationError


class FormulaValidationError(ValidationError):
    """Raised when a formula is syntactically invalid or references undefined variables."""

    def __init__(
        self,
        formula: str,
        error_detail: str,
        *,
        undefined_variables: list[str] | None = None,
    ) -> None:
        self.formula = formula
        self.error_detail = error_detail
        self.undefined_variables: list[str] = undefined_variables or []
        detail_parts = [error_detail]
        if self.undefined_variables:
            detail_parts.append(f"Undefined variables: {', '.join(self.undefined_variables)}")
        super().__init__(
            f"Invalid formula: {formula!r}",
            detail="; ".join(detail_parts),
        )


@dataclass(frozen=True)
class CalculatedReadoutResult:
    """The outcome of evaluating a calculated readout formula for a single well/row."""

    readout_definition_id: uuid.UUID
    value: float
    source_formula: str
    is_cross_protocol: bool = False


@runtime_checkable
class FormulaEvaluator(Protocol):
    """Evaluate and validate arithmetic formulas against named variable bindings.

    Implementations must be stateless — each call is independent.
    """

    def run(
        self,
        formula: str,
        bindings: dict[str, float],
    ) -> Result[float, DomainError]:
        """Evaluate *formula* with the given variable *bindings*.

        Returns:
            Success(float) — the numeric result.
            Failure(FormulaValidationError) — syntax error, undefined variable,
                division by zero, or non-numeric result.
        """
        ...

    def validate(
        self,
        formula: str,
        available_variables: list[str],
    ) -> Result[None, DomainError]:
        """Validate *formula* against the declared *available_variables*.

        Does not need real data — uses dummy values (1.0) for each variable.

        Returns:
            Success(None) — formula is valid.
            Failure(FormulaValidationError) — syntax error or undefined variable
                (check ``err.undefined_variables`` for the offending names).
        """
        ...
