"""Workspace settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.workspace_config.get_workspace_settings import (
    GetWorkspaceSettingsQuery,
)
from chem_vault.application.workspace_config.update_workspace_settings import (
    UpdateWorkspaceSettingsCommand,
)
from chem_vault.domain.workspace_config.workspace_settings import WorkspaceSettings, _SENTINEL
from chem_vault.interface.dependencies import (
    AuthDep,
    GetWorkspaceSettingsDep,
    UpdateWorkspaceSettingsDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class WorkspaceSettingsResponse(BaseModel):
    registration_rules: dict
    custom_field_definitions: dict
    default_molecule_type: str | None = None
    audit_reason_policy: dict
    signature_required_for: list[str]
    audit_retention_days: int | None = None
    formulation_number_scheme: dict
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
    custom_field_definitions: dict | None = None
    default_molecule_type: str | None | object = _SENTINEL
    audit_reason_policy: dict | None = None
    signature_required_for: list[str] | None = None
    audit_retention_days: int | None | object = _SENTINEL
    formulation_number_scheme: dict | None = None

    model_config = {"arbitrary_types_allowed": True}


@router.get("", response_model=WorkspaceSettingsResponse)
async def get_settings(
    auth: AuthDep,
    use_case: GetWorkspaceSettingsDep,
) -> WorkspaceSettingsResponse:
    query = GetWorkspaceSettingsQuery(workspace_id=auth.workspace_id)
    settings = result_to_response(await use_case(query))
    return WorkspaceSettingsResponse.from_domain(settings)


@router.patch("", response_model=WorkspaceSettingsResponse)
async def update_settings(
    body: UpdateWorkspaceSettingsBody,
    auth: AuthDep,
    use_case: UpdateWorkspaceSettingsDep,
) -> WorkspaceSettingsResponse:
    command = UpdateWorkspaceSettingsCommand(
        workspace_id=auth.workspace_id,
        registration_rules=body.registration_rules if body.registration_rules is not None else _SENTINEL,
        custom_field_definitions=body.custom_field_definitions if body.custom_field_definitions is not None else _SENTINEL,
        default_molecule_type=body.default_molecule_type,
        audit_reason_policy=body.audit_reason_policy if body.audit_reason_policy is not None else _SENTINEL,
        signature_required_for=body.signature_required_for if body.signature_required_for is not None else _SENTINEL,
        audit_retention_days=body.audit_retention_days,
        formulation_number_scheme=body.formulation_number_scheme if body.formulation_number_scheme is not None else _SENTINEL,
    )
    settings = result_to_response(await use_case(command))
    return WorkspaceSettingsResponse.from_domain(settings)
