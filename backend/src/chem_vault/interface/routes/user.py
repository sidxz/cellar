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

    @classmethod
    def from_domain(cls, prefs: object) -> PreferencesResponse:
        return cls(
            theme=getattr(prefs, "theme", "dark"),
            sidebar_collapsed=getattr(prefs, "sidebar_collapsed", False),
            default_search_columns=getattr(prefs, "default_search_columns", None),
        )


class UpdatePreferencesBody(BaseModel):
    theme: str | None = None
    sidebar_collapsed: bool | None = None
    default_search_columns: list[str] | None = None


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(auth: AuthDep, use_case: GetPreferencesDep) -> PreferencesResponse:
    query = GetPreferencesQuery(workspace_id=auth.workspace_id, user_id=auth.user_id)
    prefs = result_to_response(await use_case(query))
    return PreferencesResponse.from_domain(prefs)


@router.patch("/preferences", response_model=PreferencesResponse)
async def update_preferences(
    body: UpdatePreferencesBody,
    auth: AuthDep,
    use_case: UpdatePreferencesDep,
) -> PreferencesResponse:
    from chem_vault.application.shared.sentinel import UNSET

    # Distinguish "field omitted" from "field explicitly set to null"
    dsc = body.default_search_columns if "default_search_columns" in body.model_fields_set else UNSET

    command = UpdatePreferencesCommand(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        theme=body.theme,
        sidebar_collapsed=body.sidebar_collapsed,
        default_search_columns=dsc,
    )
    prefs = result_to_response(await use_case(command))
    return PreferencesResponse.from_domain(prefs)


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
