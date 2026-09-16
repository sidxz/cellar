"""Campaign-library endpoints: link / unlink, coverage, and the gap list.

The campaign twin of the run-collection routes in ``runs.py`` — same 204
idempotent link pair, the same ``CollectionCoverageResponse`` shape, the same
paged gap. Coverage is deliberately its own read: neither the campaign list
nor ``GET /campaigns/{id}/summary`` pays for it.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Query, Response

from cellar.application.research_organization.campaign_collection_coverage import (
    GetCampaignCollectionCoverageQuery,
    GetCampaignCollectionGapQuery,
)
from cellar.application.research_organization.manage_campaign_collections import (
    AddCampaignCollectionCommand,
    RemoveCampaignCollectionCommand,
)
from cellar.interface.dependencies import (
    AddCampaignCollectionDep,
    AuthDep,
    GetCampaignCollectionCoverageDep,
    GetCampaignCollectionGapDep,
    RemoveCampaignCollectionDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.routes._campaign_dtos import CampaignCollectionCoverageResponse

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])


@router.post("/{campaign_id}/collections/{collection_id}", status_code=204)
async def add_campaign_collection(
    campaign_id: uuid.UUID,
    collection_id: uuid.UUID,
    auth: AuthDep,
    uc: AddCampaignCollectionDep,
) -> Response:
    """Name a library this campaign screened (idempotent)."""
    result = await uc(
        AddCampaignCollectionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign_id,
            collection_id=collection_id,
        ),
        auth=auth,
    )
    result_to_response(result)
    return Response(status_code=204)


@router.delete("/{campaign_id}/collections/{collection_id}", status_code=204)
async def remove_campaign_collection(
    campaign_id: uuid.UUID,
    collection_id: uuid.UUID,
    auth: AuthDep,
    uc: RemoveCampaignCollectionDep,
) -> Response:
    """Unlink a library from this campaign."""
    result = await uc(
        RemoveCampaignCollectionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign_id,
            collection_id=collection_id,
        ),
        auth=auth,
    )
    result_to_response(result)
    return Response(status_code=204)


@router.get(
    "/{campaign_id}/collection-coverage",
    response_model=list[CampaignCollectionCoverageResponse],
)
async def campaign_collection_coverage(
    campaign_id: uuid.UUID,
    auth: AuthDep,
    uc: GetCampaignCollectionCoverageDep,
    include: Literal["stages"] | None = Query(
        None,
        description=(
            "Pass 'stages' to also tally each library's rows through the "
            "campaign's stages. Costs a full campaign load; omit it for "
            "coverage alone."
        ),
    ),
) -> list[CampaignCollectionCoverageResponse]:
    """Per linked library: members read in any of this campaign's seed runs.

    With ``include=stages`` each entry also carries the campaign's funnel
    counted over that library's rows — which library the hits came from.
    """
    libraries = result_to_response(
        await uc(
            GetCampaignCollectionCoverageQuery(
                workspace_id=auth.workspace_id,
                campaign_id=campaign_id,
                include_stages=include == "stages",
            ),
            auth=auth,
        )
    )
    return [CampaignCollectionCoverageResponse.from_library(lib) for lib in libraries]


@router.get(
    "/{campaign_id}/collections/{collection_id}/gap",
    response_model=list[uuid.UUID],
)
async def campaign_collection_gap(
    campaign_id: uuid.UUID,
    collection_id: uuid.UUID,
    auth: AuthDep,
    uc: GetCampaignCollectionGapDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[uuid.UUID]:
    """Library members no seed run of this campaign read (paginated)."""
    result = await uc(
        GetCampaignCollectionGapQuery(
            workspace_id=auth.workspace_id,
            campaign_id=campaign_id,
            collection_id=collection_id,
            offset=offset,
            limit=limit,
        ),
        auth=auth,
    )
    return result_to_response(result)
