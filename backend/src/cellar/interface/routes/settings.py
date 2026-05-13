"""Workspace settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.shared.sentinel import UNSET
from cellar.application.workspace_config.get_workspace_settings import (
    GetWorkspaceSettingsQuery,
)
from cellar.application.workspace_config.update_workspace_settings import (
    UpdateWorkspaceSettingsCommand,
)
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings
from cellar.interface.dependencies import (
    AuthDep,
    GetWorkspaceSettingsDep,
    UpdateWorkspaceSettingsDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class WorkspaceSettingsResponse(BaseModel):
    registration_rules: dict
    custom_field_definitions: list
    default_molecule_type: str | None = None
    audit_reason_policy: str | None = None
    signature_required_for: list[str]
    audit_retention_days: int | None = None
    formulation_number_scheme: str | None = None
    version: int

    @classmethod
    def from_domain(cls, s: WorkspaceSettings) -> WorkspaceSettingsResponse:
        return cls(
            registration_rules=s.registration_rules,
            custom_field_definitions=s.custom_field_definitions,
            default_molecule_type=s.default_molecule_type,
            audit_reason_policy=s.audit_reason_policy,
            signature_required_for=s.signature_required_for,
            audit_retention_days=s.audit_retention_days,
            formulation_number_scheme=s.formulation_number_scheme,
            version=s.version,
        )


class UpdateWorkspaceSettingsBody(BaseModel):
    registration_rules: dict | None = None
    custom_field_definitions: list | None = None
    default_molecule_type: str | None = None
    audit_reason_policy: str | None = None
    signature_required_for: list[str] | None = None
    audit_retention_days: int | None = None
    formulation_number_scheme: str | None = None

    model_config = {"extra": "forbid"}


@router.get("", response_model=WorkspaceSettingsResponse)
async def get_settings(
    auth: AuthDep,
    use_case: GetWorkspaceSettingsDep,
) -> WorkspaceSettingsResponse:
    query = GetWorkspaceSettingsQuery(workspace_id=auth.workspace_id)
    settings = result_to_response(await use_case(query, auth=auth))
    return WorkspaceSettingsResponse.from_domain(settings)


@router.patch("", response_model=WorkspaceSettingsResponse)
async def update_settings(
    body: UpdateWorkspaceSettingsBody,
    auth: AuthDep,
    use_case: UpdateWorkspaceSettingsDep,
) -> WorkspaceSettingsResponse:
    provided = body.model_fields_set
    command = UpdateWorkspaceSettingsCommand(
        workspace_id=auth.workspace_id,
        **{
            key: getattr(body, key)
            for key in (
                "registration_rules",
                "custom_field_definitions",
                "default_molecule_type",
                "audit_reason_policy",
                "signature_required_for",
                "audit_retention_days",
                "formulation_number_scheme",
            )
            if key in provided
        },
    )
    settings = result_to_response(await use_case(command, auth=auth))
    return WorkspaceSettingsResponse.from_domain(settings)
