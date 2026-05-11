"""CampaignResult — one snapshot row per compound within a campaign.

Owns N CampaignMeasurements (one per channel). Carries the screener's
per-compound decision (selected / deferred / rejected). At close, the
collection of CampaignResults with decision=SELECTED feeds the emitted
frozen output Collection.

``added_from`` records how the compound entered the campaign. It is
``None`` for results added manually via ``AddResultRow`` without explicit
attribution (treated as ManualRef in the published view). Immutable after
first write — only set at add time, never updated by reconciliation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from chem_vault.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from chem_vault.domain.research_organization.enums import CampaignDecision
from chem_vault.domain.shared.errors import ValidationError

if TYPE_CHECKING:
    from chem_vault.domain.research_organization.source_ref import SourceRef


@dataclass
class CampaignResult:
    campaign_id: uuid.UUID
    molecule_id: uuid.UUID
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    representative_batch_id: uuid.UUID | None = None
    decision: CampaignDecision = CampaignDecision.DEFERRED
    decision_reason: str | None = None
    notes: str | None = None
    added_from: SourceRef | None = None
    measurements: list[CampaignMeasurement] = field(default_factory=list)

    def add_measurement(self, m: CampaignMeasurement) -> None:
        if m.result_id != self.id:
            raise ValidationError(
                f"CampaignMeasurement.result_id ({m.result_id}) does not match "
                f"CampaignResult.id ({self.id})"
            )
        self.measurements.append(m)

    def remove_measurement_for_channel(self, channel_id: uuid.UUID) -> None:
        self.measurements = [
            m for m in self.measurements if m.channel_id != channel_id
        ]

    def set_decision(
        self, decision: CampaignDecision, *, reason: str | None = None
    ) -> None:
        self.decision = decision
        self.decision_reason = reason

    def find_measurement(self, channel_id: uuid.UUID) -> CampaignMeasurement | None:
        for m in self.measurements:
            if m.channel_id == channel_id:
                return m
        return None
