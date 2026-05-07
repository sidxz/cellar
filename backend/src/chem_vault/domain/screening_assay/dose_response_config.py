"""DoseResponseConfig value object — protocol-level curve fitting configuration."""

from __future__ import annotations

from dataclasses import dataclass

from chem_vault.domain.screening_assay.enums import (
    CurveType,
    HillSlopeConstraint,
    InterceptBasis,
    InterceptKind,
    NormalizationScope,
    ReadoutNormalization,
)
from chem_vault.domain.shared.errors import ValidationError


@dataclass(frozen=True)
class InterceptSpec:
    """One intercept derived from a fitted dose-response curve.

    ``level`` semantics depend on ``basis``:

    * ``RELATIVE_PERCENT``: percent (0, 100) between bottom (0%) and top
      (100%). IC50 = 50, IC90 = 90, EC50 = 50, EC90 = 90.
    * ``ABSOLUTE``: an absolute Y value the curve must cross (rare).

    ``kind`` (IC vs EC) flips the direction of the response threshold:
    for IC, ``response_target = top - level/100 * (top - bottom)``; for EC,
    ``response_target = bottom + level/100 * (top - bottom)``.
    """

    kind: InterceptKind
    level: float
    basis: InterceptBasis = InterceptBasis.RELATIVE_PERCENT
    label: str | None = None

    def __post_init__(self) -> None:
        if (
            self.basis == InterceptBasis.RELATIVE_PERCENT
            and not (0 < self.level < 100)
        ):
            raise ValidationError(
                f"InterceptSpec relative percent must be in (0, 100), got {self.level}"
            )

    @property
    def display_label(self) -> str:
        if self.label:
            return self.label
        if self.basis == InterceptBasis.RELATIVE_PERCENT:
            return f"{self.kind.value.upper()}{self.level:g}"
        return f"{self.kind.value.upper()}@{self.level:g}"


# Single source of truth for the auto-outlier-removal default sigma threshold.
# CDD/Prism convention is 3.0 (Grubbs-like leave-one-out).
DEFAULT_OUTLIER_SIGMA: float = 3.0

# Curve classification defaults — calibrated for normalized (% inhibition / %
# activation / % control) readouts. Raw-signal protocols should override these
# on the config so they don't all collapse to PARTIAL/INACTIVE by mismatch.
DEFAULT_INACTIVE_THRESHOLD: float = 30.0
DEFAULT_FULL_R2_MIN: float = 0.8
DEFAULT_FULL_TOP_MIN: float = 80.0
DEFAULT_FULL_BOTTOM_MAX: float = 20.0
DEFAULT_PARTIAL_R2_MIN: float = 0.6


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
        - classification thresholds: r2 fields in (0, 1]; inactive/top/bottom
          plain floats; full_top_min > full_bottom_max
    """

    curve_type: CurveType
    y_readout_name: str
    x_readout_name: str | None = None
    # When the Y readout def emits multiple normalized columns (e.g. raw +
    # %inh + z-score), this picks which one feeds the fit. ``None`` selects
    # the raw layer (rows where ``is_computed=False``). The protocol
    # aggregate is responsible for cross-validating that the chosen formula
    # is in the Y readout def's ``normalizations`` set.
    y_normalization: ReadoutNormalization | None = None
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
    outlier_sigma: float | None = DEFAULT_OUTLIER_SIGMA
    # Curve classification thresholds. Defaults assume a normalized (%) Y axis;
    # raw-signal protocols (fluorescence, luminescence) should override.
    inactive_threshold: float = DEFAULT_INACTIVE_THRESHOLD
    full_r2_min: float = DEFAULT_FULL_R2_MIN
    full_top_min: float = DEFAULT_FULL_TOP_MIN
    full_bottom_max: float = DEFAULT_FULL_BOTTOM_MAX
    partial_r2_min: float = DEFAULT_PARTIAL_R2_MIN
    # Intercepts to compute from the same Hill fit. Empty defaults to a single
    # 50% intercept derived from ``curve_type`` (IC50 -> IC50, EC50 -> EC50,
    # etc.) so back-compat with existing single-intercept protocols is
    # automatic. Multi-intercept protocols set this to (IC50, IC90) etc.
    intercepts: tuple[InterceptSpec, ...] = ()

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

        if not (0 < self.full_r2_min <= 1):
            raise ValidationError(
                "DoseResponseConfig full_r2_min must be in (0, 1]"
            )
        if not (0 < self.partial_r2_min <= 1):
            raise ValidationError(
                "DoseResponseConfig partial_r2_min must be in (0, 1]"
            )
        if self.full_top_min <= self.full_bottom_max:
            raise ValidationError(
                "DoseResponseConfig full_top_min must be greater than full_bottom_max"
            )

        # Default intercept set from curve_type when none provided.
        if not self.intercepts:
            default_kind = (
                InterceptKind.IC
                if self.curve_type == CurveType.IC50
                else InterceptKind.EC
            )
            object.__setattr__(
                self,
                "intercepts",
                (
                    InterceptSpec(
                        kind=default_kind,
                        level=50.0,
                        basis=InterceptBasis.RELATIVE_PERCENT,
                    ),
                ),
            )

        # Reject exact duplicates on (kind, level, basis).
        seen: set[tuple[InterceptKind, float, InterceptBasis]] = set()
        for spec in self.intercepts:
            key = (spec.kind, spec.level, spec.basis)
            if key in seen:
                raise ValidationError(
                    f"DoseResponseConfig has duplicate intercept spec {key}"
                )
            seen.add(key)
