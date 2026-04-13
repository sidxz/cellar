"""Protocol form CRUD endpoints."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.workspace_config.create_protocol_form import (
    CreateProtocolForm,
    CreateProtocolFormCommand,
)
from chem_vault.application.workspace_config.delete_protocol_form import (
    DeleteProtocolForm,
    DeleteProtocolFormCommand,
)
from chem_vault.application.workspace_config.list_protocol_forms import (
    ListProtocolForms,
    ListProtocolFormsQuery,
)
from chem_vault.application.workspace_config.update_protocol_form import (
    UpdateProtocolForm,
    UpdateProtocolFormCommand,
)
from chem_vault.domain.workspace_config.protocol_form import ProtocolForm
from chem_vault.interface.dependencies import (
    AuthDep,
    CreateProtocolFormDep,
    DeleteProtocolFormDep,
    ListProtocolFormsDep,
    UpdateProtocolFormDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/protocol-forms", tags=["protocol-forms"])


class ProtocolFormResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    protocol_type: str | None = None
    is_default: bool
    readout_templates: list[dict]
    condition_templates: list[dict] | None = None
    ontology_defaults: list[dict] | None = None
    version: int

    @classmethod
    def from_domain(cls, form: ProtocolForm) -> ProtocolFormResponse:
        return cls(
            id=form.id,
            workspace_id=form.workspace_id,
            name=form.name,
            description=form.description,
            protocol_type=form.protocol_type,
            is_default=form.is_default,
            readout_templates=[asdict(r) for r in form.readout_templates],
            condition_templates=[asdict(c) for c in form.condition_templates] if form.condition_templates else None,
            ontology_defaults=[asdict(o) for o in form.ontology_defaults] if form.ontology_defaults else None,
            version=form.version,
        )


class CreateProtocolFormBody(BaseModel):
    name: str
    description: str | None = None
    protocol_type: str | None = None
    is_default: bool = False
    readout_templates: list[dict]
    condition_templates: list[dict] | None = None
    ontology_defaults: list[dict] | None = None


class UpdateProtocolFormBody(BaseModel):
    name: str | None = None
    description: str | None = None
    protocol_type: str | None = None
    is_default: bool | None = None
    readout_templates: list[dict] | None = None
    condition_templates: list[dict] | None = None
    ontology_defaults: list[dict] | None = None


@router.get("", response_model=list[ProtocolFormResponse])
async def list_protocol_forms(
    auth: AuthDep,
    use_case: ListProtocolFormsDep,
) -> list[ProtocolFormResponse]:
    query = ListProtocolFormsQuery(workspace_id=auth.workspace_id)
    forms = result_to_response(await use_case(query))
    return [ProtocolFormResponse.from_domain(f) for f in forms]


@router.post("", response_model=ProtocolFormResponse, status_code=201)
async def create_protocol_form(
    body: CreateProtocolFormBody,
    auth: AuthDep,
    use_case: CreateProtocolFormDep,
) -> ProtocolFormResponse:
    command = CreateProtocolFormCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        description=body.description,
        protocol_type=body.protocol_type,
        is_default=body.is_default,
        readout_templates=body.readout_templates,
        condition_templates=body.condition_templates,
        ontology_defaults=body.ontology_defaults,
    )
    form = result_to_response(await use_case(command, auth=auth))
    return ProtocolFormResponse.from_domain(form)


@router.patch("/{form_id}", response_model=ProtocolFormResponse)
async def update_protocol_form(
    form_id: uuid.UUID,
    body: UpdateProtocolFormBody,
    auth: AuthDep,
    use_case: UpdateProtocolFormDep,
) -> ProtocolFormResponse:
    from chem_vault.application.shared.sentinel import UNSET

    cmd_fields: dict[str, Any] = {
        "workspace_id": auth.workspace_id,
        "form_id": form_id,
    }
    for attr in ("name", "description", "protocol_type", "is_default", "readout_templates", "condition_templates", "ontology_defaults"):
        cmd_fields[attr] = getattr(body, attr) if attr in body.model_fields_set else UNSET

    command = UpdateProtocolFormCommand(**cmd_fields)
    form = result_to_response(await use_case(command, auth=auth))
    return ProtocolFormResponse.from_domain(form)


@router.delete("/{form_id}", status_code=204)
async def delete_protocol_form(
    form_id: uuid.UUID,
    auth: AuthDep,
    use_case: DeleteProtocolFormDep,
) -> None:
    command = DeleteProtocolFormCommand(
        workspace_id=auth.workspace_id,
        form_id=form_id,
    )
    result_to_response(await use_case(command, auth=auth))
