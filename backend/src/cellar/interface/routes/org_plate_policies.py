"""Org plate policy endpoints — per-org plate loan config."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.inventory.org_plate_policy import (
    GetOrgPlatePolicyQuery,
    SetOrgPlatePolicyCommand,
)
from cellar.domain.inventory.enums import LoanConfirmationMode
from cellar.domain.inventory.org_plate_policy import OrgPlatePolicy
from cellar.interface.dependencies import AuthDep, GetOrgPlatePolicyDep, SetOrgPlatePolicyDep
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/org-plate-policies", tags=["org-plate-policies"])


class OrgPlatePolicyResponse(BaseModel):
    org_id: uuid.UUID
    require_approval: bool
    confirmation: LoanConfirmationMode
    default_due_days: int | None = None
    version: int

    @classmethod
    def from_domain(cls, p: OrgPlatePolicy) -> OrgPlatePolicyResponse:
        return cls(
            org_id=p.org_id,
            require_approval=p.require_approval,
            confirmation=p.confirmation,
            default_due_days=p.default_due_days,
            version=p.version,
        )


class SetOrgPlatePolicyBody(BaseModel):
    require_approval: bool
    confirmation: LoanConfirmationMode
    default_due_days: int | None

    model_config = {"extra": "forbid"}


@router.get("/{org_id}", response_model=OrgPlatePolicyResponse)
async def get_org_plate_policy(
    org_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetOrgPlatePolicyDep,
) -> OrgPlatePolicyResponse:
    query = GetOrgPlatePolicyQuery(workspace_id=auth.workspace_id, org_id=org_id)
    policy = result_to_response(await use_case(query, auth=auth))
    return OrgPlatePolicyResponse.from_domain(policy)


@router.put("/{org_id}", response_model=OrgPlatePolicyResponse)
async def set_org_plate_policy(
    org_id: uuid.UUID,
    body: SetOrgPlatePolicyBody,
    auth: AuthDep,
    use_case: SetOrgPlatePolicyDep,
) -> OrgPlatePolicyResponse:
    command = SetOrgPlatePolicyCommand(
        workspace_id=auth.workspace_id,
        org_id=org_id,
        require_approval=body.require_approval,
        confirmation=body.confirmation.value,
        default_due_days=body.default_due_days,
    )
    policy = result_to_response(await use_case(command, auth=auth))
    return OrgPlatePolicyResponse.from_domain(policy)
