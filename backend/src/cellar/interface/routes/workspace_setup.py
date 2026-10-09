"""Setup checklist for admins: which prerequisites of protocol work are still missing."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.workspace_config.workspace_setup import GetWorkspaceSetupQuery
from cellar.interface.dependencies import AuthDep, GetWorkspaceSetupDep
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/workspace-setup", tags=["workspace-setup"])


class WorkspaceSetupResponse(BaseModel):
    missing_default_categories: list[str]
    missing_default_forms: int
    bioportal_key: bool
    home_organisms: int
    targets: int


@router.get("", response_model=WorkspaceSetupResponse)
async def get_workspace_setup(
    auth: AuthDep, use_case: GetWorkspaceSetupDep
) -> WorkspaceSetupResponse:
    setup = result_to_response(
        await use_case(GetWorkspaceSetupQuery(workspace_id=auth.workspace_id), auth=auth)
    )
    return WorkspaceSetupResponse(**vars(setup))
