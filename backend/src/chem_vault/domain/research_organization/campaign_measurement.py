"""CampaignMeasurement — one frozen cell owned by a CampaignResult.

The atomic unit of the snapshot: (compound, channel) -> (value, qualifier,
unit, hit_call, source FKs, protocol snapshot fields). At close, every
auto-resolved cell is locked in. Manual edits flip is_manual_override so
the cell is preserved through subsequent recomputes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from chem_vault.domain.research_organization.enums import HitCall, ValueQualifier
from chem_vault.domain.shared.errors import ValidationError


@dataclass
class CampaignMeasurement:
    result_id: uuid.UUID
    channel_id: uuid.UUID
    value: float | None
    value_qualifier: ValueQualifier
    unit: str
    protocol_name_snapshot: str
    protocol_version_snapshot: int
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    hit_call: HitCall | None = None
    is_manual_override: bool = False
    source_run_id: uuid.UUID | None = None
    source_curve_id: uuid.UUID | None = None
    source_readout_id: uuid.UUID | None = None
    run_date_snapshot: date | None = None

    def __post_init__(self) -> None:
        numeric_qualifiers = {
            ValueQualifier.EQ,
            ValueQualifier.LT,
            ValueQualifier.GT,
        }
        if self.value_qualifier in numeric_qualifiers and self.value is None:
            raise ValidationError(
                f"qualifier {self.value_qualifier.value!r} requires a numeric value"
            )
        if self.value_qualifier in {ValueQualifier.ND, ValueQualifier.EXCLUDED}:
            self.value = None
        if not self.unit or not self.unit.strip():
            raise ValidationError("CampaignMeasurement.unit must not be empty")
        self.unit = self.unit.strip()

    def mark_manual_override(self) -> None:
        self.is_manual_override = True
