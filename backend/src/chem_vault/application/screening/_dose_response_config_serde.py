"""DoseResponseConfig dict <-> VO serialization.

Single source of truth for translating protocol JSONB / API request dicts
into the domain VO. New optional fields added to ``DoseResponseConfig`` flow
through here automatically — call sites do not need updating.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from chem_vault.domain.screening_assay.dose_response_config import (
    DEFAULT_FULL_BOTTOM_MAX,
    DEFAULT_FULL_R2_MIN,
    DEFAULT_FULL_TOP_MIN,
    DEFAULT_INACTIVE_THRESHOLD,
    DEFAULT_OUTLIER_SIGMA,
    DEFAULT_PARTIAL_R2_MIN,
    DoseResponseConfig,
)
from chem_vault.domain.screening_assay.enums import (
    CurveType,
    HillSlopeConstraint,
    NormalizationScope,
)


def deserialize_dose_response_config(data: dict[str, Any]) -> DoseResponseConfig:
    """Build a ``DoseResponseConfig`` VO from a dict.

    Raises ``ValidationError`` (via the VO's ``__post_init__``) when invariants
    are violated. Missing classification thresholds fall back to module-level
    defaults so old JSONB rows deserialize cleanly.
    """
    return DoseResponseConfig(
        curve_type=CurveType(data["curve_type"]),
        x_readout_name=data.get("x_readout_name"),
        y_readout_name=data["y_readout_name"],
        hill_slope_constraint=HillSlopeConstraint(
            data.get("hill_slope_constraint", "unconstrained")
        ),
        activity_threshold=data.get("activity_threshold"),
        normalization_scope=NormalizationScope(
            data.get("normalization_scope", "per_plate")
        ),
        top_constraint=data.get("top_constraint"),
        bottom_constraint=data.get("bottom_constraint"),
        top_constraint_min=data.get("top_constraint_min"),
        top_constraint_max=data.get("top_constraint_max"),
        bottom_constraint_min=data.get("bottom_constraint_min"),
        bottom_constraint_max=data.get("bottom_constraint_max"),
        hill_slope_min=data.get("hill_slope_min"),
        hill_slope_max=data.get("hill_slope_max"),
        outlier_sigma=data.get("outlier_sigma", DEFAULT_OUTLIER_SIGMA),
        inactive_threshold=data.get("inactive_threshold", DEFAULT_INACTIVE_THRESHOLD),
        full_r2_min=data.get("full_r2_min", DEFAULT_FULL_R2_MIN),
        full_top_min=data.get("full_top_min", DEFAULT_FULL_TOP_MIN),
        full_bottom_max=data.get("full_bottom_max", DEFAULT_FULL_BOTTOM_MAX),
        partial_r2_min=data.get("partial_r2_min", DEFAULT_PARTIAL_R2_MIN),
    )


def serialize_dose_response_config(config: DoseResponseConfig) -> dict[str, Any]:
    """Serialize a ``DoseResponseConfig`` VO to a JSON-friendly dict.

    Enum values are flattened to their ``.value`` strings so the output is
    directly JSONB-compatible.
    """
    raw = asdict(config)
    raw["curve_type"] = config.curve_type.value
    raw["hill_slope_constraint"] = config.hill_slope_constraint.value
    raw["normalization_scope"] = config.normalization_scope.value
    return raw
