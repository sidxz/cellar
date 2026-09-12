"""Campaign stage-management endpoints (add / update / remove / override)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from cellar.application.research_organization.add_campaign_stage import (
    AddCampaignStageCommand,
)
from cellar.application.research_organization.remove_campaign_stage import (
    RemoveCampaignStageCommand,
)
from cellar.application.research_organization.set_stage_override import (
    SetStageOverrideCommand,
)
from cellar.application.research_organization.update_campaign_stage import (
    UpdateCampaignStageCommand,
)
from cellar.domain.research_organization.campaign_stage import UNSET, StageCriterion
from cellar.domain.research_organization.enums import StageKind, StageOutcome
from cellar.interface.dependencies import (
    AddCampaignStageDep,
    AuthDep,
    RemoveCampaignStageDep,
    SetStageOverrideDep,
    UpdateCampaignStageDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.routes._campaign_dtos import (
    AddStageRequest,
    CampaignResponse,
    SetStageOverrideRequest,
    UpdateStageRequest,
)

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])


@router.post("/{campaign_id}/stages", response_model=CampaignResponse, status_code=200)
async def add_campaign_stage(
    campaign_id: uuid.UUID,
    body: AddStageRequest,
    auth: AuthDep,
    uc: AddCampaignStageDep,
) -> CampaignResponse:
    """Add a hit-triage stage to a draft Campaign."""
    cmd = AddCampaignStageCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        name=body.name,
        parent_stage_id=body.parent_stage_id,
        kind=StageKind(body.kind),
        criteria=[c.to_domain() for c in body.criteria],
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.patch("/{campaign_id}/stages/{stage_id}", response_model=CampaignResponse)
async def update_campaign_stage(
    campaign_id: uuid.UUID,
    stage_id: uuid.UUID,
    body: UpdateStageRequest,
    auth: AuthDep,
    uc: UpdateCampaignStageDep,
) -> CampaignResponse:
    """Update a campaign stage.

    Semantics: omitted fields are left unchanged (UNSET); a null
    ``parent_stage_id`` clears it. ``name``/``criteria``/``display_order``/
    ``kind`` have no "clear" meaning on the aggregate, so an explicit null for
    those is treated the same as omitted. Switching to ``kind: "manual"``
    requires sending ``criteria: []`` in the same PATCH (422 otherwise).
    """
    provided = body.model_fields_set

    name: str | object = body.name if "name" in provided else UNSET
    parent_stage_id: uuid.UUID | object | None = (
        body.parent_stage_id if "parent_stage_id" in provided else UNSET
    )
    criteria: list[StageCriterion] | object = (
        [c.to_domain() for c in body.criteria]
        if "criteria" in provided and body.criteria is not None
        else UNSET
    )
    display_order: int | object = (
        body.display_order
        if "display_order" in provided and body.display_order is not None
        else UNSET
    )
    kind: StageKind | object = (
        StageKind(body.kind) if "kind" in provided and body.kind is not None else UNSET
    )

    cmd = UpdateCampaignStageCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        stage_id=stage_id,
        name=name,
        parent_stage_id=parent_stage_id,
        criteria=criteria,
        display_order=display_order,
        kind=kind,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.delete("/{campaign_id}/stages/{stage_id}", response_model=CampaignResponse)
async def remove_campaign_stage(
    campaign_id: uuid.UUID,
    stage_id: uuid.UUID,
    auth: AuthDep,
    uc: RemoveCampaignStageDep,
) -> CampaignResponse:
    """Remove a stage from a draft Campaign. 409 when child stages exist."""
    cmd = RemoveCampaignStageCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        stage_id=stage_id,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.put(
    "/{campaign_id}/results/{result_id}/stages/{stage_id}/override",
    response_model=CampaignResponse,
)
async def set_stage_override(
    campaign_id: uuid.UUID,
    result_id: uuid.UUID,
    stage_id: uuid.UUID,
    body: SetStageOverrideRequest,
    auth: AuthDep,
    uc: SetStageOverrideDep,
) -> CampaignResponse:
    """Manually force a stage's hit/miss outcome for one CampaignResult."""
    cmd = SetStageOverrideCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        result_id=result_id,
        stage_id=stage_id,
        user_id=auth.user_id,
        forced_outcome=StageOutcome(body.outcome),
        reason=body.reason,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.delete(
    "/{campaign_id}/results/{result_id}/stages/{stage_id}/override",
    response_model=CampaignResponse,
)
async def clear_stage_override(
    campaign_id: uuid.UUID,
    result_id: uuid.UUID,
    stage_id: uuid.UUID,
    auth: AuthDep,
    uc: SetStageOverrideDep,
) -> CampaignResponse:
    """Clear a manual (result, stage) override, if any (no-op when none exists)."""
    cmd = SetStageOverrideCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        result_id=result_id,
        stage_id=stage_id,
        user_id=auth.user_id,
        forced_outcome=None,
        reason=None,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)
