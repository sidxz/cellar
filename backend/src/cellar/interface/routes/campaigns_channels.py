"""Campaign channel-management endpoints (add / update / remove)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from cellar.application.research_organization.add_campaign_channel import (
    AddCampaignChannelCommand,
)
from cellar.application.research_organization.remove_campaign_channel import (
    RemoveCampaignChannelCommand,
)
from cellar.application.research_organization.update_campaign_channel import (
    UNSET,
    UpdateCampaignChannelCommand,
)
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from cellar.domain.shared.hit_criterion import HitCriterion
from cellar.interface.dependencies import (
    AddCampaignChannelDep,
    AuthDep,
    RemoveCampaignChannelDep,
    UpdateCampaignChannelDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.routes._campaign_dtos import (
    AddChannelRequest,
    CampaignResponse,
    UpdateChannelRequest,
)

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])


@router.post("/{campaign_id}/channels", response_model=CampaignResponse, status_code=200)
async def add_campaign_channel(
    campaign_id: uuid.UUID,
    body: AddChannelRequest,
    auth: AuthDep,
    uc: AddCampaignChannelDep,
) -> CampaignResponse:
    """Add a channel to a draft Campaign."""
    cmd = AddCampaignChannelCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        label=body.label,
        protocol_id=body.protocol_id,
        readout_definition_id=body.readout_definition_id,
        source_kind=ChannelSourceKind(body.source_kind),
        selection_rule=SelectionRule(body.selection_rule),
        qualifier_handling=QualifierHandling(body.qualifier_handling),
        qc_filter=body.qc_filter,
        hit_threshold=body.hit_threshold.to_domain() if body.hit_threshold is not None else None,
        display_order=body.display_order,
        normalization_applied=body.normalization_applied,
        intercept_key=body.intercept_key.to_domain() if body.intercept_key is not None else None,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.patch("/{campaign_id}/channels/{channel_id}", response_model=CampaignResponse)
async def update_campaign_channel(
    campaign_id: uuid.UUID,
    channel_id: uuid.UUID,
    body: UpdateChannelRequest,
    auth: AuthDep,
    uc: UpdateCampaignChannelDep,
) -> CampaignResponse:
    """Update a campaign channel.

    Semantics: omitted fields are left unchanged (UNSET); null-valued fields
    are cleared where applicable (qc_filter, hit_threshold).
    """
    provided = body.model_fields_set

    # Map omit → UNSET, present → actual value (including None)
    label: str | object = body.label if "label" in provided else UNSET
    selection_rule: SelectionRule | object = (
        SelectionRule(body.selection_rule)
        if "selection_rule" in provided and body.selection_rule is not None
        else UNSET
    )
    qc_filter: dict | None | object = body.qc_filter if "qc_filter" in provided else UNSET
    hit_threshold: HitCriterion | None | object = (
        (body.hit_threshold.to_domain() if (body.hit_threshold is not None) else None)
        if "hit_threshold" in provided
        else UNSET
    )

    cmd = UpdateCampaignChannelCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        channel_id=channel_id,
        label=label,
        selection_rule=selection_rule,
        qc_filter=qc_filter,
        hit_threshold=hit_threshold,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.delete("/{campaign_id}/channels/{channel_id}", response_model=CampaignResponse)
async def remove_campaign_channel(
    campaign_id: uuid.UUID,
    channel_id: uuid.UUID,
    auth: AuthDep,
    uc: RemoveCampaignChannelDep,
) -> CampaignResponse:
    """Remove a channel and its measurements from a draft Campaign."""
    cmd = RemoveCampaignChannelCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        channel_id=channel_id,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)
