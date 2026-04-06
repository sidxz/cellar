"""User preferences + workspace member endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.user.get_preferences import GetPreferencesQuery
from chem_vault.application.user.update_preferences import UpdatePreferencesCommand
from chem_vault.interface.dependencies import (
    AuthDep,
    GetPreferencesDep,
    UpdatePreferencesDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/user", tags=["user"])


class PreferencesResponse(BaseModel):
    theme: str = "dark"
    sidebar_collapsed: bool = False
    default_search_columns: list[str] | None = None


class UpdatePreferencesBody(BaseModel):
    theme: str | None = None
    sidebar_collapsed: bool | None = None
    default_search_columns: list[str] | None = None


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(auth: AuthDep, use_case: GetPreferencesDep) -> PreferencesResponse:
    query = GetPreferencesQuery(workspace_id=auth.workspace_id, user_id=auth.user_id)
    result = await use_case(query)
    prefs = result_to_response(result)
    return PreferencesResponse(
        theme=prefs.theme,
        sidebar_collapsed=prefs.sidebar_collapsed,
        default_search_columns=prefs.default_search_columns,
    )


@router.patch("/preferences", response_model=PreferencesResponse)
async def update_preferences(
    body: UpdatePreferencesBody,
    auth: AuthDep,
    use_case: UpdatePreferencesDep,
) -> PreferencesResponse:
    from chem_vault.application.user.update_preferences import _UNSET

    # Distinguish "field omitted" from "field explicitly set to null"
    dsc = body.default_search_columns if "default_search_columns" in body.model_fields_set else _UNSET

    command = UpdatePreferencesCommand(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        theme=body.theme,
        sidebar_collapsed=body.sidebar_collapsed,
        default_search_columns=dsc,
    )
    result = await use_case(command)
    prefs = result_to_response(result)
    return PreferencesResponse(
        theme=prefs.theme,
        sidebar_collapsed=prefs.sidebar_collapsed,
        default_search_columns=prefs.default_search_columns,
    )


# ---------------------------------------------------------------------------
# Workspace members (proxy to Sentinel)
# ---------------------------------------------------------------------------


class WorkspaceMemberResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    name: str
    avatar_url: str | None = None
    role: str


@router.get("/workspace-members", response_model=list[WorkspaceMemberResponse])
async def list_workspace_members(
    auth: AuthDep, q: str | None = None
) -> list[WorkspaceMemberResponse]:
    """List members of the current workspace. Proxies to Sentinel."""
    if q:
        members = await auth.search_workspace_members(q, limit=20)
    else:
        members = await auth.list_members(limit=50)
    return [WorkspaceMemberResponse(**m) for m in members]
