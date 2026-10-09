"""Workspace settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, model_validator

from cellar.application.workspace_config.get_workspace_settings import (
    GetWorkspaceSettingsQuery,
)
from cellar.application.workspace_config.set_home_organism import SetHomeOrganismCommand
from cellar.application.workspace_config.update_workspace_settings import (
    UpdateWorkspaceSettingsCommand,
)
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings
from cellar.interface.dependencies import (
    AuthDep,
    GetWorkspaceSettingsDep,
    SetHomeOrganismDep,
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
    protocol_naming: dict = {}
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
            protocol_naming=s.protocol_naming,
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
    protocol_naming: dict | None = None

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
                "protocol_naming",
            )
            if key in provided
        },
    )
    settings = result_to_response(await use_case(command, auth=auth))
    return WorkspaceSettingsResponse.from_domain(settings)


class HomeOrganismTerm(BaseModel):
    term_id: str
    label: str
    ontology_source: str = "NCBITAXON"


class SetHomeOrganismRequest(BaseModel):
    """``terms``: the home organisms (empty clears them). ``term`` is the older single shape
    (null clears); external callers may still send it."""

    terms: list[HomeOrganismTerm] | None = None
    term: HomeOrganismTerm | None = None
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _one_shape(self) -> SetHomeOrganismRequest:
        sent = self.model_fields_set & {"terms", "term"}
        if len(sent) != 1 or (self.terms is None and "terms" in sent):
            raise ValueError("Send either terms (a list) or term")
        return self

    def as_list(self) -> list[dict]:
        if self.terms is not None:
            return [t.model_dump() for t in self.terms]
        return [self.term.model_dump()] if self.term else []


@router.put("/home-organism", response_model=WorkspaceSettingsResponse)
async def set_home_organism(
    body: SetHomeOrganismRequest, auth: AuthDep, use_case: SetHomeOrganismDep
) -> WorkspaceSettingsResponse:
    """Targets from these organisms are named without them; relabels protocols."""
    cmd = SetHomeOrganismCommand(workspace_id=auth.workspace_id, terms=body.as_list())
    settings = result_to_response(await use_case(cmd, auth=auth))
    return WorkspaceSettingsResponse.from_domain(settings)
