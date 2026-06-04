"""Campaign lifecycle endpoints — create, list, get, update, add-results, refresh, close, supersede.

Channel, result-row, and publishing endpoints are split into sibling modules
(``campaigns_channels.py``, ``campaigns_results.py``, ``campaigns_publishing.py``).
All shared Pydantic DTOs live in ``_campaign_dtos.py``.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Query

from cellar.application.research_organization.add_results_from_campaign import (
    AddResultsFromCampaignCommand,
)
from cellar.application.research_organization.add_results_from_collection import (
    AddResultsFromCollectionCommand,
)
from cellar.application.research_organization.add_results_from_runs import (
    AddResultsFromRunsCommand,
)
from cellar.application.research_organization.close_campaign import (
    CloseCampaignCommand,
)
from cellar.application.research_organization.create_campaign import (
    CreateCampaignCommand,
)
from cellar.application.research_organization.get_campaign import (
    GetCampaignQuery,
)
from cellar.application.research_organization.list_campaigns import (
    ListCampaignsQuery,
)
from cellar.application.research_organization.preview_run_import import (
    PreviewRunImportQuery,
)
from cellar.application.research_organization.refresh_campaign_from_sources import (
    RefreshFromSourcesCommand,
)
from cellar.application.research_organization.supersede_campaign import (
    SupersedeCampaignCommand,
)
from cellar.application.research_organization.update_campaign_metadata import (
    UpdateCampaignMetadataCommand,
)
from cellar.domain.research_organization.enums import CampaignDecision
from cellar.interface.dependencies import (
    AddResultsFromCampaignDep,
    AddResultsFromCollectionDep,
    AddResultsFromRunsDep,
    AuthDep,
    CloseCampaignDep,
    CreateCampaignDep,
    GetCampaignDep,
    ListCampaignsDep,
    PreviewRunImportDep,
    RefreshFromSourcesDep,
    SupersedeCampaignDep,
    UpdateCampaignMetadataDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.pagination import PaginatedResponse, clamp_limit, parse_cursor
from cellar.interface.routes._campaign_dtos import (
    AddFromCampaignRequest,
    AddFromCollectionRequest,
    AddFromRunsRequest,
    AddResultsOutcomeResponse,
    CampaignResponse,
    CloseCampaignRequest,
    CreateCampaignRequest,
    PreviewRunImportRequest,
    SupersedeRequest,
    UpdateCampaignRequest,
)

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])


@router.post("", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    body: CreateCampaignRequest,
    auth: AuthDep,
    uc: CreateCampaignDep,
) -> CampaignResponse:
    """Create an empty draft Campaign. Compounds are added via add-from-* endpoints."""
    cmd = CreateCampaignCommand(
        workspace_id=auth.workspace_id,
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        publishes_collection=body.publishes_collection,
        created_by=auth.user_id,
        supersedes_campaign_id=body.supersedes_campaign_id,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.get("", response_model=PaginatedResponse[CampaignResponse])
async def list_campaigns(
    auth: AuthDep,
    uc: ListCampaignsDep,
    project_id: uuid.UUID | None = Query(default=None),
    cursor: str | None = None,
    limit: int | None = None,
    tags: list[uuid.UUID] | None = Query(default=None),
    tag_logic: Literal["any", "all"] = Query(default="any"),
) -> PaginatedResponse[CampaignResponse]:
    """List campaigns in the workspace, optionally filtered by project."""
    query = ListCampaignsQuery(
        workspace_id=auth.workspace_id,
        project_id=project_id,
        cursor_id=parse_cursor(cursor),
        limit=clamp_limit(limit),
        tags=tags,
        tag_logic=tag_logic,
    )
    page = result_to_response(await uc(query, auth=auth))
    return PaginatedResponse(
        items=[CampaignResponse.from_domain(c) for c in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: uuid.UUID,
    auth: AuthDep,
    uc: GetCampaignDep,
) -> CampaignResponse:
    """Get a campaign by id (full draft view including channels + results)."""
    query = GetCampaignQuery(workspace_id=auth.workspace_id, campaign_id=campaign_id)
    out = result_to_response(await uc(query, auth=auth))
    return CampaignResponse.from_domain(out.campaign, out.scientist_by_run_id)


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: uuid.UUID,
    body: UpdateCampaignRequest,
    auth: AuthDep,
    uc: UpdateCampaignMetadataDep,
) -> CampaignResponse:
    """Update campaign name/description."""
    provided = body.model_fields_set
    cmd_kwargs: dict = {
        "workspace_id": auth.workspace_id,
        "campaign_id": campaign_id,
    }
    if "name" in provided:
        cmd_kwargs["name"] = body.name
    if "description" in provided:
        cmd_kwargs["description"] = body.description
    cmd = UpdateCampaignMetadataCommand(**cmd_kwargs)
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.post("/{campaign_id}/add-from-collection", response_model=AddResultsOutcomeResponse)
async def add_results_from_collection(
    campaign_id: uuid.UUID,
    body: AddFromCollectionRequest,
    auth: AuthDep,
    uc: AddResultsFromCollectionDep,
) -> AddResultsOutcomeResponse:
    """Add compound results from a Collection to a DRAFT campaign (idempotent)."""
    cmd = AddResultsFromCollectionCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        collection_id=body.collection_id,
        description=body.description,
    )
    outcome = result_to_response(await uc(cmd, auth=auth))
    return AddResultsOutcomeResponse.from_outcome(outcome)


@router.post("/{campaign_id}/add-from-campaign", response_model=AddResultsOutcomeResponse)
async def add_results_from_campaign(
    campaign_id: uuid.UUID,
    body: AddFromCampaignRequest,
    auth: AuthDep,
    uc: AddResultsFromCampaignDep,
) -> AddResultsOutcomeResponse:
    """Add compound results from another Campaign's filtered result set (idempotent)."""
    cmd = AddResultsFromCampaignCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        source_campaign_id=body.source_campaign_id,
        decision_filter=[CampaignDecision(d) for d in body.decision_filter],
        description=body.description,
    )
    outcome = result_to_response(await uc(cmd, auth=auth))
    return AddResultsOutcomeResponse.from_outcome(outcome)


@router.post("/{campaign_id}/preview-run-import")
async def preview_run_import(
    campaign_id: uuid.UUID,
    body: PreviewRunImportRequest,
    auth: AuthDep,
    uc: PreviewRunImportDep,
) -> dict[str, Any]:
    """Compute the would-be-added cells for the multi-run import dialog (B6).

    Read-only. Returns ``{summary, channels, rows}`` — see spec §3.2.
    """
    q = PreviewRunImportQuery(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        run_ids=body.run_ids,
        channel_configs=[c.to_domain() for c in body.channel_configs],
        filter_mode=body.filter_mode,
    )
    return result_to_response(await uc(q, auth=auth))


@router.post("/{campaign_id}/add-from-runs", response_model=AddResultsOutcomeResponse)
async def add_results_from_runs(
    campaign_id: uuid.UUID,
    body: AddFromRunsRequest,
    auth: AuthDep,
    uc: AddResultsFromRunsDep,
) -> AddResultsOutcomeResponse:
    """Add compound results from one or more protocol Runs (B6).

    Creates campaign channels for each unique (protocol_id, readout_definition_id),
    reusing existing ones. Filters molecules by hit-criteria when scope=hits_only.
    Snapshots concentration/replicate/QC per cell.
    """
    cmd = AddResultsFromRunsCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        run_ids=body.run_ids,
        channel_configs=[c.to_domain() for c in body.channel_configs],
        filter_mode=body.filter_mode,
        scope=body.scope,
        default_decision=CampaignDecision(body.default_decision),
        description=body.description,
        refresh_existing_cells=body.refresh_existing_cells,
    )
    outcome = result_to_response(await uc(cmd, auth=auth))
    return AddResultsOutcomeResponse.from_outcome(outcome)


@router.post("/{campaign_id}/refresh", response_model=CampaignResponse)
async def refresh_campaign(
    campaign_id: uuid.UUID,
    auth: AuthDep,
    uc: RefreshFromSourcesDep,
) -> CampaignResponse:
    """Re-resolve all non-override measurements in a DRAFT campaign."""
    cmd = RefreshFromSourcesCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.post("/{campaign_id}/close", response_model=CampaignResponse)
async def close_campaign(
    campaign_id: uuid.UUID,
    body: CloseCampaignRequest,
    auth: AuthDep,
    uc: CloseCampaignDep,
) -> CampaignResponse:
    """Lock a DRAFT campaign and optionally publish a frozen Collection."""
    cmd = CloseCampaignCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        user_id=auth.user_id,
        signature_id=body.signature_id,
        signature_meaning=body.signature_meaning,
        publishes_collection=body.publishes_collection,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.post("/{campaign_id}/supersede", response_model=CampaignResponse)
async def supersede_campaign(
    campaign_id: uuid.UUID,
    body: SupersedeRequest,
    auth: AuthDep,
    uc: SupersedeCampaignDep,
) -> CampaignResponse:
    """Mark a closed campaign as superseded by a newer one.

    ``campaign_id`` is the OLD (closed) campaign to supersede.
    ``body.new_campaign_id`` is the NEW campaign that replaces it.
    Returns the old campaign (now SUPERSEDED).
    """
    cmd = SupersedeCampaignCommand(
        workspace_id=auth.workspace_id,
        old_campaign_id=campaign_id,
        new_campaign_id=body.new_campaign_id,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)
