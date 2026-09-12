"""Campaign result-row endpoints.

Covers per-row CRUD (add / remove), bulk row removal, per-row notes edits,
and per-cell manual overrides.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from cellar.application.research_organization.add_result_row import (
    AddResultRowCommand,
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
from cellar.domain.research_organization.enums import ValueQualifier
from cellar.interface.dependencies import (
    AddResultRowDep,
    AuthDep,
    OverrideResultCellDep,
    RemoveResultRowDep,
    SetResultNotesDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.routes._campaign_dtos import (
    AddResultRowRequest,
    BulkRemoveResultsRequest,
    CampaignResponse,
    OverrideCellRequest,
    SetResultNotesRequest,
)

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])


@router.patch("/{campaign_id}/results/{result_id}", response_model=CampaignResponse)
async def set_result_notes(
    campaign_id: uuid.UUID,
    result_id: uuid.UUID,
    body: SetResultNotesRequest,
    auth: AuthDep,
    uc: SetResultNotesDep,
) -> CampaignResponse:
    """Set (or, with ``null``, clear) the free-text notes on one result row."""
    cmd = SetResultNotesCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        result_id=result_id,
        notes=body.notes,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


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
