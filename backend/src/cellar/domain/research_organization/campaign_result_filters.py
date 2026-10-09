"""Review filters narrow a result list; they never change stage evaluation."""

from __future__ import annotations

import uuid
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.shared.aggregation_types import ValueQualifier
from cellar.domain.shared.units import canonical_unit


class MeasurementFilter(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    channel_id: uuid.UUID
    minimum: float | None = None
    maximum: float | None = None
    # Bounds use the stored unit up to spelling (uM = µM; closed snapshots keep their old
    # spelling); empty means dimensionless. No silent conversion between different units.
    unit: str = Field(default="", max_length=40)
    qc: Literal["any", "passed", "failed", "unknown"] = "any"

    @model_validator(mode="after")
    def valid_bounds(self) -> Self:
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum must not exceed maximum")
        if self.minimum is None and self.maximum is None and self.qc == "any":
            raise ValueError("a measurement filter needs a bound or QC condition")
        return self

    def matches(self, row: CampaignResult) -> bool:
        cell = next((m for m in row.measurements if m.channel_id == self.channel_id), None)
        if cell is None:
            return False
        if (
            self.qc != "any"
            and cell.qc_pass is not {"passed": True, "failed": False, "unknown": None}[self.qc]
        ):
            return False
        if self.minimum is not None or self.maximum is not None:
            # Censored values (< or >), ND and excluded cells are not exact numeric evidence.
            if (
                cell.value_qualifier != ValueQualifier.EQ
                or cell.value is None
                or canonical_unit(cell.unit) != canonical_unit(self.unit)
            ):
                return False
            if self.minimum is not None and cell.value < self.minimum:
                return False
            if self.maximum is not None and cell.value > self.maximum:
                return False
        return True


class CampaignResultFilters(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    search: str = Field(default="", max_length=200)
    overridden: bool | None = None
    measurements: tuple[MeasurementFilter, ...] = Field(default=(), max_length=8)
