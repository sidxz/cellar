"""User preferences endpoints — thin route resolving use cases from DI."""

from __future__ import annotations

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


class UpdatePreferencesBody(BaseModel):
    theme: str | None = None
    sidebar_collapsed: bool | None = None


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(auth: AuthDep, use_case: GetPreferencesDep) -> PreferencesResponse:
    query = GetPreferencesQuery(workspace_id=auth.workspace_id, user_id=auth.user_id)
    result = await use_case(query)
    prefs = result_to_response(result)
    return PreferencesResponse(theme=prefs.theme, sidebar_collapsed=prefs.sidebar_collapsed)


@router.patch("/preferences", response_model=PreferencesResponse)
async def update_preferences(
    body: UpdatePreferencesBody,
    auth: AuthDep,
    use_case: UpdatePreferencesDep,
) -> PreferencesResponse:
    command = UpdatePreferencesCommand(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        theme=body.theme,
        sidebar_collapsed=body.sidebar_collapsed,
    )
    result = await use_case(command)
    prefs = result_to_response(result)
    return PreferencesResponse(theme=prefs.theme, sidebar_collapsed=prefs.sidebar_collapsed)
