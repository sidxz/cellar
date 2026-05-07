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
        - lock and range are mutually exclusive (per parameter): cannot set
          ``top_constraint`` together with ``top_constraint_min`` or
          ``top_constraint_max``; same for bottom and hill
        - if both ``*_min`` and ``*_max`` are set, ``min < max``
        - hill range must not contradict ``hill_slope_constraint`` (e.g.,
          POSITIVE_ONLY + range straddling 0 is rejected)
    """

    curve_type: CurveType
    y_readout_name: str
    x_readout_name: str | None = None
    hill_slope_constraint: HillSlopeConstraint = HillSlopeConstraint.UNCONSTRAINED
    activity_threshold: float | None = None
    normalization_scope: NormalizationScope = NormalizationScope.PER_PLATE
    top_constraint: float | None = None
    bottom_constraint: float | None = None
    top_constraint_min: float | None = None
    top_constraint_max: float | None = None
    bottom_constraint_min: float | None = None
    bottom_constraint_max: float | None = None
    hill_slope_min: float | None = None
    hill_slope_max: float | None = None
    # Auto-outlier removal: during the second-pass refit, points with
    # residual > ``outlier_sigma`` × SD of the other residuals are excluded.
    # ``None`` disables outlier removal entirely; a positive float sets the
    # threshold (CDD-equivalent default is 3.0). Below the minimum-points
    # floor (~6 points) the fitter doesn't have enough degrees of freedom
    # to estimate residual SD, so detection is skipped regardless.
    outlier_sigma: float | None = 3.0

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

        if self.top_constraint is not None and (
            self.top_constraint_min is not None or self.top_constraint_max is not None
        ):
            raise ValidationError(
                "DoseResponseConfig top_constraint cannot be combined with "
                "top_constraint_min/top_constraint_max — choose lock or range"
            )
        if self.bottom_constraint is not None and (
            self.bottom_constraint_min is not None
            or self.bottom_constraint_max is not None
        ):
            raise ValidationError(
                "DoseResponseConfig bottom_constraint cannot be combined with "
                "bottom_constraint_min/bottom_constraint_max — choose lock or range"
            )

        if (
            self.top_constraint_min is not None
            and self.top_constraint_max is not None
            and self.top_constraint_min >= self.top_constraint_max
        ):
            raise ValidationError(
                "DoseResponseConfig top_constraint_min must be less than top_constraint_max"
            )
        if (
            self.bottom_constraint_min is not None
            and self.bottom_constraint_max is not None
            and self.bottom_constraint_min >= self.bottom_constraint_max
        ):
            raise ValidationError(
                "DoseResponseConfig bottom_constraint_min must be less than "
                "bottom_constraint_max"
            )
        if (
            self.hill_slope_min is not None
            and self.hill_slope_max is not None
            and self.hill_slope_min >= self.hill_slope_max
        ):
            raise ValidationError(
                "DoseResponseConfig hill_slope_min must be less than hill_slope_max"
            )

        if self.hill_slope_constraint == HillSlopeConstraint.POSITIVE_ONLY:
            if self.hill_slope_min is not None and self.hill_slope_min <= 0:
                raise ValidationError(
                    "DoseResponseConfig hill_slope_min contradicts "
                    "hill_slope_constraint=POSITIVE_ONLY (must be > 0)"
                )
            if self.hill_slope_max is not None and self.hill_slope_max <= 0:
                raise ValidationError(
                    "DoseResponseConfig hill_slope_max contradicts "
                    "hill_slope_constraint=POSITIVE_ONLY (must be > 0)"
                )
        elif self.hill_slope_constraint == HillSlopeConstraint.NEGATIVE_ONLY:
            if self.hill_slope_min is not None and self.hill_slope_min >= 0:
                raise ValidationError(
                    "DoseResponseConfig hill_slope_min contradicts "
                    "hill_slope_constraint=NEGATIVE_ONLY (must be < 0)"
                )
            if self.hill_slope_max is not None and self.hill_slope_max >= 0:
                raise ValidationError(
                    "DoseResponseConfig hill_slope_max contradicts "
                    "hill_slope_constraint=NEGATIVE_ONLY (must be < 0)"
                )

        if self.outlier_sigma is not None and self.outlier_sigma <= 0:
            raise ValidationError(
                "DoseResponseConfig outlier_sigma must be positive (or None to disable)"
            )
