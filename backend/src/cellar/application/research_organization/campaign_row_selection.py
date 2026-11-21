"""The rows a campaign's results search returns for a stage, outcome and review filters.

Shared by the paged search (``ListCampaignResults``) and the bulk QC write
(``SetCellQcVerdicts``), so "the rows I am looking at" and "the rows I just marked" are
always the same code.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from cellar.application.research_organization.campaign_identity_reader import (
    CampaignIdentityReader,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_result_filters import CampaignResultFilters
from cellar.domain.research_organization.enums import StageOutcome
from cellar.domain.research_organization.stage_evaluation import StageOutcomes
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class RowSelection:
    #: Which stage's verdict to filter on. Required when ``outcome`` or
    #: ``filters.overridden`` is set.
    stage_id: uuid.UUID | None = None
    #: Verdicts at ``stage_id`` **after** any manual override. A row is kept when its
    #: verdict is any of these; empty means no outcome filter.
    outcome: tuple[StageOutcome, ...] = ()
    filters: CampaignResultFilters = field(default_factory=CampaignResultFilters)


async def select_campaign_rows(
    campaign: Campaign,
    selection: RowSelection,
    *,
    outcomes: StageOutcomes,
    identity_reader: CampaignIdentityReader,
) -> Result[list[CampaignResult], DomainError]:
    """The selected rows in campaign order; no ordering or paging.

    422 for ``outcome`` or ``filters.overridden`` without ``stage_id``; 404 for an
    unknown stage or filter channel.
    """
    if selection.outcome and selection.stage_id is None:
        return Failure(ValidationError("outcome requires stage_id"))
    if selection.filters.overridden is not None and selection.stage_id is None:
        return Failure(ValidationError("overridden requires stage_id"))
    if selection.stage_id is not None and campaign.find_stage(selection.stage_id) is None:
        return Failure(NotFoundError("CampaignStage", str(selection.stage_id)))
    known_channels = {ch.id for ch in campaign.channels}
    for condition in selection.filters.measurements:
        if condition.channel_id not in known_channels:
            return Failure(NotFoundError("CampaignChannel", str(condition.channel_id)))

    rows = list(campaign.results)
    if selection.stage_id is not None and selection.outcome:
        stage_id = selection.stage_id
        wanted = set(selection.outcome)
        rows = [
            r
            for r in rows
            if (o := outcomes.get(r.id, {}).get(stage_id)) is not None and o.outcome in wanted
        ]
    if selection.filters.overridden is not None:
        assert selection.stage_id is not None
        rows = [
            r
            for r in rows
            if (o := outcomes.get(r.id, {}).get(selection.stage_id)) is not None
            and o.overridden == selection.filters.overridden
        ]
    for condition in selection.filters.measurements:
        rows = [r for r in rows if condition.matches(r)]
    if selection.filters.search and rows:
        matches = await identity_reader.matching_ids(
            campaign.workspace_id, list({r.molecule_id for r in rows}), selection.filters.search
        )
        rows = [r for r in rows if r.molecule_id in matches]
    return Success(rows)
