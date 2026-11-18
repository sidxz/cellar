"""Column descriptions (spec §6.6), computed on read from the loaded aggregate.

Never persisted: every read that shows columns already holds their measurements, so
one pass over them is the whole cost and nothing can go stale.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping

from cellar.application.screening.run_aggregation import effective_rule
from cellar.application.visualization.dataset import LAYER_LABELS
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import CampaignMeasurement
from cellar.domain.research_organization.enums import ChannelSourceKind, SelectionRule
from cellar.domain.research_organization.measurement_facts import (
    ColumnDescription,
    build_column_profile,
    describe_column,
)
from cellar.domain.screening_assay.enums import unit_for_normalization
from cellar.domain.screening_assay.protocol import ReadoutDefinition
from cellar.domain.screening_assay.repository import ProtocolRepository


def readout_label(channel: CampaignChannel, readout_name: str | None) -> str:
    """The readout's name plus its normalization layer, as the grid heads it:
    "Signal (% Inhibition)". A dose-response column has no layer of its own; one that
    surfaces a secondary intercept is named for it ("EC90"), so two intercept columns
    of one readout never share a label."""
    if channel.intercept_key is not None:
        ik = channel.intercept_key
        return f"{ik.kind.upper()}{ik.level:g}"
    name = readout_name or channel.label  # the readout definition is gone
    norm = channel.normalization_applied
    if norm and channel.source_kind == ChannelSourceKind.READOUT_DATA:
        return f"{name} ({LAYER_LABELS.get(norm, norm)})"
    return name


def _computed_rule(channel: CampaignChannel, readout: ReadoutDefinition | None) -> SelectionRule:
    """The rule the resolver applies: a readout column's values are single-point,
    in the unit of the readout's layer (as ``ColumnCandidateQuery`` reads them)."""
    if channel.source_kind != ChannelSourceKind.READOUT_DATA:
        return channel.selection_rule
    unit = unit_for_normalization(channel.normalization_applied, readout.unit if readout else None)
    return effective_rule(channel.selection_rule, unit=unit, single_point=True)


def _scope_run_count(campaign: Campaign, ch: CampaignChannel) -> int | None:
    """Runs the column may draw from: its stage's, or the campaign's for a campaign
    column; None for a column that reads every run of the protocol."""
    if ch.resolve_from_all_runs:
        return None
    if ch.stage_id is not None:
        return len(campaign.stage_run_ids(ch.stage_id, ch.protocol_id))
    return len(campaign.campaign_run_ids(ch.protocol_id))


def describe_channels(
    campaign: Campaign, readouts: Mapping[uuid.UUID, ReadoutDefinition]
) -> dict[uuid.UUID, ColumnDescription]:
    """Every column's description, by channel id; ``readouts`` by readout definition id."""
    by_channel: dict[uuid.UUID, list[CampaignMeasurement]] = {}
    for r in campaign.results:
        for m in r.measurements:
            by_channel.setdefault(m.channel_id, []).append(m)
    stage_names = {s.id: s.name for s in campaign.stages}
    out = {}
    for ch in campaign.channels:
        readout = readouts.get(ch.readout_definition_id)
        out[ch.id] = describe_column(
            channel=ch,
            stage_name=stage_names.get(ch.stage_id) if ch.stage_id else None,
            readout_label=readout_label(ch, readout.name if readout else None),
            profile=build_column_profile(ch, by_channel.get(ch.id, [])),
            rule=_computed_rule(ch, readout),
            scope_run_count=_scope_run_count(campaign, ch),
        )
    return out


async def load_readouts(
    protocol_repo: ProtocolRepository, workspace_id: uuid.UUID, campaigns: Iterable[Campaign]
) -> dict[uuid.UUID, ReadoutDefinition]:
    """Readout definitions of every column of ``campaigns``, by id, in one load."""
    protocol_ids = list({ch.protocol_id for c in campaigns for ch in c.channels})
    if not protocol_ids:
        return {}
    protocols = await protocol_repo.find_by_ids(workspace_id, protocol_ids)
    return {rd.id: rd for p in protocols for rd in p.readout_definitions}
