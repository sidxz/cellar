"""Campaign result-row endpoints.

Covers the paged row read, per-row CRUD (add / remove), bulk row removal,
per-row notes edits, and per-cell manual overrides.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from cellar.application.research_organization.add_result_row import (
    AddResultRowCommand,
)
from cellar.application.research_organization.list_campaign_results import (
    ListCampaignResultsQuery,
)
from cellar.application.research_organization.override_result_cell import (
    OverrideResultCellCommand,
)
from cellar.application.research_organization.remove_result_row import (
    RemoveResultRowCommand,
)
from cellar.application.research_organization.set_result_notes import (
    SetResultNotesCommand,
)
from cellar.domain.research_organization.enums import StageOutcome, ValueQualifier
from cellar.interface.dependencies import (
    AddResultRowDep,
    AuthDep,
    ListCampaignResultsDep,
    OverrideResultCellDep,
    RemoveResultRowDep,
    SetResultNotesDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PaginatedResponse,
    clamp_limit,
    parse_cursor,
)
from cellar.interface.routes._campaign_dtos import (
    AddResultRowRequest,
    BulkRemoveResultsRequest,
    CampaignResponse,
    CampaignResultResponse,
    OverrideCellRequest,
    SetResultNotesRequest,
)

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])


@router.get("/{campaign_id}/results", response_model=PaginatedResponse[CampaignResultResponse])
async def list_campaign_results(
    campaign_id: uuid.UUID,
    auth: AuthDep,
    uc: ListCampaignResultsDep,
    stage_id: uuid.UUID | None = None,
    outcome: StageOutcome | None = None,
    order_by: Annotated[
        uuid.UUID | None, Query(description="Channel id to sort by; omit for row order")
    ] = None,
    direction: Literal["asc", "desc"] = "asc",
    cursor: str | None = None,
    limit: Annotated[int, Query(le=MAX_PAGE_SIZE, ge=1)] = DEFAULT_PAGE_SIZE,
) -> PaginatedResponse[CampaignResultResponse]:
    """One page of a campaign's result rows, filtered and ordered server-side.

    ``outcome`` filters on the verdict at ``stage_id`` **after** overrides —
    the same value the row's ``stage_outcomes`` reports — and needs
    ``stage_id``. ``order_by`` names a channel: plain values sort first,
    then censored ones, with ND and excluded cells last in either direction.
    ``total_count`` is the filtered count, so a page can say "50 of 214".

    The full ``GET /campaigns/{id}`` read is unchanged; use this when you want
    a page rather than the matrix.
    """
    query = ListCampaignResultsQuery(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        stage_id=stage_id,
        outcome=outcome,
        order_by_channel_id=order_by,
        descending=direction == "desc",
        cursor_id=parse_cursor(cursor),
        limit=clamp_limit(limit),
    )
    out = result_to_response(await uc(query, auth=auth))
    return PaginatedResponse(
        items=[
            CampaignResultResponse.from_domain(r, out.outcomes.get(r.id)) for r in out.page.items
        ],
        next_cursor=out.page.next_cursor,
        total_count=out.page.total_count,
    )


@router.patch("/{campaign_id}/results/{result_id}", status_code=204)
async def set_result_notes(
    campaign_id: uuid.UUID,
    result_id: uuid.UUID,
    body: SetResultNotesRequest,
    auth: AuthDep,
    uc: SetResultNotesDep,
) -> Response:
    """Set (or, with ``null``, clear) the free-text notes on one result row.

    204: returning the campaign would serialise the whole result matrix back
    for a one-field edit, and every caller refetches anyway.
    """
    cmd = SetResultNotesCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        result_id=result_id,
        notes=body.notes,
    )
    result_to_response(await uc(cmd, auth=auth))
    return Response(status_code=204)


@router.patch(
    "/{campaign_id}/results/{result_id}/cells/{channel_id}",
    response_model=CampaignResponse,
)
async def override_result_cell(
    campaign_id: uuid.UUID,
    result_id: uuid.UUID,
    channel_id: uuid.UUID,
    body: OverrideCellRequest,
    auth: AuthDep,
    uc: OverrideResultCellDep,
) -> CampaignResponse:
    """Manually override a single (result, channel) measurement cell."""
    cmd = OverrideResultCellCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        result_id=result_id,
        channel_id=channel_id,
        value=body.value,
        value_qualifier=ValueQualifier(body.value_qualifier),
        unit=body.unit,
        reason=body.reason,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.post("/{campaign_id}/results", response_model=CampaignResponse)
async def add_result_row(
    campaign_id: uuid.UUID,
    body: AddResultRowRequest,
    auth: AuthDep,
    uc: AddResultRowDep,
) -> CampaignResponse:
    """Add a new compound result row (manual attribution) to a DRAFT campaign."""
    cmd = AddResultRowCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        molecule_id=body.molecule_id,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.delete("/{campaign_id}/results/{result_id}", response_model=CampaignResponse)
async def remove_result_row(
    campaign_id: uuid.UUID,
    result_id: uuid.UUID,
    auth: AuthDep,
    uc: RemoveResultRowDep,
) -> CampaignResponse:
    """Remove a compound result row and its measurements from a DRAFT campaign."""
    cmd = RemoveResultRowCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        result_ids=[result_id],
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.post("/{campaign_id}/results/bulk-remove", response_model=CampaignResponse)
async def bulk_remove_result_rows(
    campaign_id: uuid.UUID,
    body: BulkRemoveResultsRequest,
    auth: AuthDep,
    uc: RemoveResultRowDep,
) -> CampaignResponse:
    """Remove N compound result rows from a DRAFT campaign in one save.

    POST rather than DELETE because some proxies drop DELETE bodies. 404 on
    the first unknown result id, with nothing removed.
    """
    cmd = RemoveResultRowCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        result_ids=body.result_ids,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)
