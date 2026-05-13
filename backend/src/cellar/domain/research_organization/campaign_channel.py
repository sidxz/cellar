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

from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from cellar.domain.shared.hit_criterion import HitCriterion
from cellar.domain.shared.errors import ValidationError


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
    #: Which normalization layer of the readout this channel reads. None for
    #: the raw layer (``normalization_applied IS NULL``); set to a formula
    #: name (e.g. ``"percent_inhibition"``) to pick the computed layer.
    #: Only meaningful when ``source_kind == READOUT_DATA``; ignored for
    #: dose-response curve channels (the curve's normalization is locked in
    #: by the protocol's ``dose_response_config.y_normalization``).
    normalization_applied: str | None = None

    def __post_init__(self) -> None:
        if not self.label or not self.label.strip():
            raise ValidationError("CampaignChannel.label must not be empty")
        self.label = self.label.strip()
        if self.display_order < 0:
            raise ValidationError("CampaignChannel.display_order must be ≥ 0")
