"""DoseResponseCurve entity — fitted pharmacological curve from run data."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from chem_vault.domain.screening_assay.curve_fitting import InterceptValue
from chem_vault.domain.screening_assay.enums import CurveClass, CurveType
from chem_vault.domain.shared.entity import Entity
from chem_vault.domain.shared.errors import ValidationError


class DoseResponseCurve(Entity):
    """A fitted dose-response curve derived from screening run data.

    NOT an AggregateRoot — lives outside the Run aggregate boundary.
    Represents curve-fitting results (IC50, EC50, etc.) for a
    molecule/batch/protocol/run combination.

    Invariants:
        - num_points >= 1
        - r_squared in [0, 1]
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        molecule_id: uuid.UUID,
        batch_id: uuid.UUID,
        protocol_id: uuid.UUID,
        run_id: uuid.UUID,
        curve_type: CurveType,
        fitted_value: float,
        hill_slope: float,
        top: float,
        bottom: float,
        r_squared: float,
        confidence_interval_low: float | None = None,
        confidence_interval_high: float | None = None,
        num_points: int,
        curve_class: CurveClass | None = None,
        raw_data: list[dict[str, Any]] | None = None,
        excluded_points: list[dict[str, Any]] | None = None,
        fit_quality_warnings: list[str] | None = None,
        intercept_values: list[InterceptValue] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)

        if num_points < 1:
            raise ValidationError("num_points must be >= 1")
        if not (0 <= r_squared <= 1):
            raise ValidationError("r_squared must be in [0, 1]")

        self.workspace_id = workspace_id
        self.molecule_id = molecule_id
        self.batch_id = batch_id
        self.protocol_id = protocol_id
        self.run_id = run_id
        self.curve_type = curve_type
        # Fitted IC50/EC50/etc value. Unit is the owning protocol's dose_unit;
        # callers look it up at display time. Not denormalized here.
        self.fitted_value = fitted_value
        self.hill_slope = hill_slope
        self.top = top
        self.bottom = bottom
        self.r_squared = r_squared
        self.confidence_interval_low = confidence_interval_low
        self.confidence_interval_high = confidence_interval_high
        self.num_points = num_points
        self.curve_class = curve_class
        self.raw_data = raw_data or []
        self.excluded_points = excluded_points
        self.fit_quality_warnings = list(fit_quality_warnings or [])
        # Per-spec intercepts derived from the same Hill fit (e.g. IC50, IC90).
        # Empty list = legacy single-intercept curve; readers fall back to
        # ``fitted_value`` for the headline.
        self.intercept_values = list(intercept_values or [])
