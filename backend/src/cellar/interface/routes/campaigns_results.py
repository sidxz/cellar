"""Campaign result-row + decision endpoints.

Covers per-row CRUD (add / remove), per-row decision changes, bulk-decision
updates, and per-cell manual overrides.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from cellar.application.research_organization.add_result_row import (
    AddResultRowCommand,
)
from cellar.application.research_organization.bulk_set_result_decisions import (
    BulkSetResultDecisionsCommand,
)
from cellar.application.research_organization.override_result_cell import (
    OverrideResultCellCommand,
)
from cellar.application.research_organization.remove_result_row import (
    RemoveResultRowCommand,
)
from cellar.application.research_organization.set_result_decision import (
    SetResultDecisionCommand,
)
from cellar.domain.research_organization.enums import (
    CampaignDecision,
    HitCall,
    ValueQualifier,
)
from cellar.interface.dependencies import (
    AddResultRowDep,
    AuthDep,
    BulkSetResultDecisionsDep,
    OverrideResultCellDep,
    RemoveResultRowDep,
    SetResultDecisionDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.routes._campaign_dtos import (
    AddResultRowRequest,
    BulkSetResultDecisionsRequest,
    BulkSetResultDecisionsResponse,
    CampaignResponse,
    OverrideCellRequest,
    SetResultDecisionRequest,
)

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])


# NOTE: route order matters. FastAPI matches in registration order, so the
# literal `/bulk-decision` MUST be registered before `/{result_id}` —
# otherwise the path-parameter route swallows "bulk-decision" as a
# ``result_id`` value and fails UUID validation with a 422.
@router.patch(
    "/{campaign_id}/results/bulk-decision",
    response_model=BulkSetResultDecisionsResponse,
)
async def bulk_set_result_decisions(
    campaign_id: uuid.UUID,
    body: BulkSetResultDecisionsRequest,
    auth: AuthDep,
    uc: BulkSetResultDecisionsDep,
) -> BulkSetResultDecisionsResponse:
    """Bulk-set decision for many CampaignResult rows in one transaction.

    The frontend posts the currently-filtered ``result_ids`` so chemists can
    "Mark all visible as Selected/Deferred/Rejected" without hitting the
    per-row endpoint 100+ times.
    """
    cmd = BulkSetResultDecisionsCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        result_ids=body.result_ids,
        decision=CampaignDecision(body.decision),
        reason=body.reason,
    )
    outcome = result_to_response(await uc(cmd, auth=auth))
    return BulkSetResultDecisionsResponse(
        campaign=CampaignResponse.from_domain(outcome.campaign),
        updated_count=outcome.updated_count,
        missing_ids=outcome.missing_ids,
    )


@router.patch("/{campaign_id}/results/{result_id}", response_model=CampaignResponse)
async def set_result_decision(
    campaign_id: uuid.UUID,
    result_id: uuid.UUID,
    body: SetResultDecisionRequest,
    auth: AuthDep,
    uc: SetResultDecisionDep,
) -> CampaignResponse:
    """Set a screener's per-compound decision (SELECTED / DEFERRED / REJECTED)."""
    cmd_kwargs: dict = {
        "workspace_id": auth.workspace_id,
        "campaign_id": campaign_id,
        "result_id": result_id,
        "decision": CampaignDecision(body.decision),
        "reason": body.reason,
    }
    if "notes" in body.model_fields_set:
        cmd_kwargs["notes"] = body.notes
    cmd = SetResultDecisionCommand(**cmd_kwargs)
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
        hit_call=HitCall(body.hit_call) if body.hit_call is not None else None,
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
        result_id=result_id,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)
