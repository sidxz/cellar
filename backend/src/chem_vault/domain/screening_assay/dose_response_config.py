"""DoseResponseConfig value object — protocol-level curve fitting configuration."""

from __future__ import annotations

from dataclasses import dataclass

from chem_vault.domain.screening_assay.enums import (
    CurveType,
    HillSlopeConstraint,
    NormalizationScope,
)
from chem_vault.domain.shared.errors import ValidationError


@dataclass(frozen=True)
class DoseResponseConfig:
    """Protocol-level configuration for dose-response curve fitting.

    Value Object — immutable, equality by value.
    Defines how a dose-response readout references its X/Y axes
    and how the Hill equation fitting should be constrained.

    ``x_readout_name`` is optional. ``None`` means "use the well's
    concentration as the X-axis" — the default and most common case.
    Setting ``x_readout_name`` only matters when X should be sourced
    from a derived/transformed readout (rare).

    Invariants:
        - y_readout_name must be non-empty
        - if x_readout_name is set, it must differ from y_readout_name
        - activity_threshold in [0, 100] if set
        - top_constraint > bottom_constraint if both set
    """

    curve_type: CurveType
    y_readout_name: str
    x_readout_name: str | None = None
    hill_slope_constraint: HillSlopeConstraint = HillSlopeConstraint.UNCONSTRAINED
    activity_threshold: float | None = None
    normalization_scope: NormalizationScope = NormalizationScope.PER_PLATE
    top_constraint: float | None = None
    bottom_constraint: float | None = None

    def __post_init__(self) -> None:
        if not self.y_readout_name or not self.y_readout_name.strip():
            raise ValidationError("DoseResponseConfig y_readout_name must not be empty")
        if self.x_readout_name is not None:
            if not self.x_readout_name.strip():
                raise ValidationError(
                    "DoseResponseConfig x_readout_name must not be empty when set"
                )
            if self.x_readout_name.strip() == self.y_readout_name.strip():
                raise ValidationError(
                    "DoseResponseConfig x_readout_name and y_readout_name must be different"
                )
        if self.activity_threshold is not None and not (0 <= self.activity_threshold <= 100):
            raise ValidationError(
                "DoseResponseConfig activity_threshold must be in [0, 100]"
            )
        if (
            self.top_constraint is not None
            and self.bottom_constraint is not None
            and self.top_constraint <= self.bottom_constraint
        ):
            raise ValidationError(
                "DoseResponseConfig top_constraint must be greater than bottom_constraint"
            )
