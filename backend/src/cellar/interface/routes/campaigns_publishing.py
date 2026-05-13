"""Campaign publishing endpoints — DAIKON contract document + preview."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Query

from cellar.application.research_organization.get_published_campaign import (
    GetPublishedCampaignQuery,
)
from cellar.interface.dependencies import (
    AuthDep,
    GetPublishedCampaignDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])


@router.get("/{campaign_id}/published")
async def get_published_campaign(
    campaign_id: uuid.UUID,
    auth: AuthDep,
    uc: GetPublishedCampaignDep,
    cursor: str | None = Query(default=None),
    page_size: int | None = Query(default=None),
) -> dict[str, Any]:
    """Return the DAIKON contract document for a closed/superseded campaign."""
    query = GetPublishedCampaignQuery(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        cursor=cursor,
        page_size=page_size,
    )
    return result_to_response(await uc(query, auth=auth))


@router.get("/{campaign_id}/preview-published")
async def preview_published_campaign(
    campaign_id: uuid.UUID,
    auth: AuthDep,
    uc: GetPublishedCampaignDep,
    cursor: str | None = Query(default=None),
    page_size: int | None = Query(default=None),
) -> dict[str, Any]:
    """Render any campaign (incl. DRAFT) through the DAIKON serializer.

    Lifts the closed/superseded status guard so the screener can preview
    what the published artifact will look like before closing.
    """
    query = GetPublishedCampaignQuery(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        cursor=cursor,
        page_size=page_size,
        bypass_status_check=True,
    )
    return result_to_response(await uc(query, auth=auth))
