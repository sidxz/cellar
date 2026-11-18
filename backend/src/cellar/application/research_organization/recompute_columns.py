"""recompute_columns — the one writer of auto-resolved campaign cells.

Every campaign value is written here (spec §6.3 "One resolver"): per column, the
scope comes from ``resolution_run_ids``, the candidates from one
``ColumnCandidateQuery.fetch`` for every target row at once (never one query per
cell), and the cells from ``ColumnResolver``. Manual overrides are never rewritten;
a replaced cell keeps its measurement id, so the row is UPDATEd rather than DELETEd
and re-INSERTed against the unique (result_id, channel_id).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from cellar.application.research_organization.column_resolution import (
    Candidate,
    ColumnCandidateQuery,
    ColumnResolver,
    resolution_run_ids,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.enums import UnresolvedReason


async def recompute_columns(
    *,
    query: ColumnCandidateQuery,
    campaign: Campaign,
    channels: Iterable[CampaignChannel],
    molecule_ids: list[uuid.UUID] | None = None,
    extra_rows: Sequence[CampaignResult] = (),
) -> int:
    """Re-resolve ``channels`` for the campaign's rows (all, or those of
    ``molecule_ids``), skipping manual overrides. Returns the cells written.

    ``extra_rows`` are rows not yet on the campaign that resolve with it in the same
    fetch (add-from-runs judges new compounds on their values before adding them)."""
    wanted = None if molecule_ids is None else set(molecule_ids)
    rows = [
        r for r in [*campaign.results, *extra_rows] if wanted is None or r.molecule_id in wanted
    ]
    resolver = ColumnResolver()
    written = 0
    for channel in channels:
        targets = [
            r for r in rows if not ((m := r.find_measurement(channel.id)) and m.is_manual_override)
        ]
        if not targets:
            continue
        mids = [r.molecule_id for r in targets]
        run_ids = resolution_run_ids(campaign, channel)
        # A stage with no runs leaves its column untested; it never reads protocol-wide.
        candidates: dict[uuid.UUID, list[Candidate]] = (
            {}
            if run_ids == "none"
            else await query.fetch(
                workspace_id=campaign.workspace_id,
                channel=channel,
                run_ids=run_ids,
                molecule_ids=mids,
            )
        )
        cells = resolver.resolve_column(
            channel=channel,
            molecule_ids=mids,
            candidates=candidates,
            result_id_by_molecule={r.molecule_id: r.id for r in targets},
        )
        for row in targets:
            cell = cells[row.molecule_id]
            if run_ids == "none":
                cell.unresolved_reason = UnresolvedReason.NO_RUNS_AT_STAGE
            old = row.find_measurement(channel.id)
            if old is not None:
                cell.id = old.id
                row.remove_measurement_for_channel(channel.id)
            row.add_measurement(cell)
        written += len(targets)
    return written
