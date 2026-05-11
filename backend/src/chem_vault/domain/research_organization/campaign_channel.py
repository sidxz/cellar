"""CampaignChannel — owned entity defining one column in a campaign snapshot.

A Channel binds a protocol's readout to a selection rule (which run/value to
pick), an optional QC filter, optional qualifier handling, and an optional
hit-threshold (typically carried forward from the protocol's HitCriterion).
At close, the channel produces one CampaignMeasurement per CampaignResult.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from chem_vault.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from chem_vault.domain.screening_assay.hit_criterion import HitCriterion
from chem_vault.domain.shared.errors import ValidationError


@dataclass
class CampaignChannel:
    campaign_id: uuid.UUID
    label: str
    protocol_id: uuid.UUID
    readout_definition_id: uuid.UUID
    source_kind: ChannelSourceKind
    selection_rule: SelectionRule
    qualifier_handling: QualifierHandling
    display_order: int
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    qc_filter: dict[str, Any] | None = None
    hit_threshold: HitCriterion | None = None

    def __post_init__(self) -> None:
        if not self.label or not self.label.strip():
            raise ValidationError("CampaignChannel.label must not be empty")
        self.label = self.label.strip()
        if self.display_order < 0:
            raise ValidationError("CampaignChannel.display_order must be ≥ 0")
