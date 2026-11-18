"""Column descriptions (spec §6.6), computed on read from the loaded aggregate.

Never persisted: every read that shows columns already holds their measurements, so
one pass over them is the whole cost and nothing can go stale.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping

from cellar.application.visualization.dataset import LAYER_LABELS
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import CampaignMeasurement
from cellar.domain.research_organization.enums import ChannelSourceKind
from cellar.domain.research_organization.measurement_facts import (
    ColumnDescription,
    build_column_profile,
    describe_column,
)
from cellar.domain.screening_assay.repository import ProtocolRepository


def readout_label(channel: CampaignChannel, readout_name: str | None) -> str:
    """The readout's name plus its normalization layer, as the grid heads it:
    "Signal (% Inhibition)". A dose-response column has no layer of its own."""
    name = readout_name or channel.label  # the readout definition is gone
    norm = channel.normalization_applied
    if norm and channel.source_kind == ChannelSourceKind.READOUT_DATA:
        return f"{name} ({LAYER_LABELS.get(norm, norm)})"
    return name


def describe_channels(
    campaign: Campaign, readout_names: Mapping[uuid.UUID, str]
) -> dict[uuid.UUID, ColumnDescription]:
    """Every column's description, by channel id; ``readout_names`` by readout definition."""
    by_channel: dict[uuid.UUID, list[CampaignMeasurement]] = {}
    for r in campaign.results:
        for m in r.measurements:
            by_channel.setdefault(m.channel_id, []).append(m)
    stage_names = {s.id: s.name for s in campaign.stages}
    return {
        ch.id: describe_column(
            channel=ch,
            stage_name=stage_names.get(ch.stage_id) if ch.stage_id else None,
            readout_label=readout_label(ch, readout_names.get(ch.readout_definition_id)),
            profile=build_column_profile(ch, by_channel.get(ch.id, [])),
        )
        for ch in campaign.channels
    }


async def load_readout_names(
    protocol_repo: ProtocolRepository, workspace_id: uuid.UUID, campaigns: Iterable[Campaign]
) -> dict[uuid.UUID, str]:
    """Readout definition names for every column of ``campaigns``, in one load."""
    protocol_ids = list({ch.protocol_id for c in campaigns for ch in c.channels})
    if not protocol_ids:
        return {}
    protocols = await protocol_repo.find_by_ids(workspace_id, protocol_ids)
    return {rd.id: rd.name for p in protocols for rd in p.readout_definitions}
