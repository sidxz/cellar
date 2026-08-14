"""User preferences + workspace member endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.shared.sentinel import UNSET
from cellar.application.user.get_preferences import GetPreferencesQuery
from cellar.application.user.update_preferences import UpdatePreferencesCommand
from cellar.interface.dependencies import (
    AuthDep,
    GetPreferencesDep,
    UpdatePreferencesDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/user", tags=["user"])


class MeResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    name: str
    org_id: uuid.UUID | None = None
    org_slug: str | None = None
    workspace_role: str
    is_admin: bool


@router.get("/me", response_model=MeResponse)
async def me(auth: AuthDep) -> MeResponse:
    return MeResponse(
        user_id=auth.user_id,
        email=getattr(auth, "email", ""),
        name=getattr(auth, "name", ""),
        org_id=auth.org_id,
        org_slug=auth.org_slug,
        workspace_role=auth.workspace_role,
        is_admin=auth.is_admin,
    )


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
    prefs = result_to_response(await use_case(query, auth=auth))
    return PreferencesResponse.from_domain(prefs)


@router.patch("/preferences", response_model=PreferencesResponse)
async def update_preferences(
    body: UpdatePreferencesBody,
    auth: AuthDep,
    use_case: UpdatePreferencesDep,
) -> PreferencesResponse:

    # Distinguish "field omitted" from "field explicitly set to null"
    dsc = (
        body.default_search_columns if "default_search_columns" in body.model_fields_set else UNSET
    )

    command = UpdatePreferencesCommand(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        theme=body.theme,
        sidebar_collapsed=body.sidebar_collapsed,
        default_search_columns=dsc,
    )
    prefs = result_to_response(await use_case(command, auth=auth))
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
    return [
        WorkspaceMemberResponse(
            user_id=m["user_id"],
            email=m["email"],
            name=m["name"],
            avatar_url=m.get("avatar_url"),
            role=m["role"],
        )
        for m in members
    ]
