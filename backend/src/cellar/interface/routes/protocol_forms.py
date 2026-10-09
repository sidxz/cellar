"""Protocol form CRUD endpoints."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.shared.sentinel import UNSET
from cellar.application.workspace_config.create_protocol_form import (
    CreateProtocolFormCommand,
)
from cellar.application.workspace_config.delete_protocol_form import (
    DeleteProtocolFormCommand,
)
from cellar.application.workspace_config.list_protocol_forms import (
    ListProtocolFormsQuery,
)
from cellar.application.workspace_config.protocol_form_defaults import (
    SeedDefaultProtocolFormsCommand,
)
from cellar.application.workspace_config.update_protocol_form import (
    UpdateProtocolFormCommand,
)
from cellar.domain.workspace_config.protocol_form import ProtocolForm
from cellar.interface.dependencies import (
    AuthDep,
    CreateProtocolFormDep,
    DeleteProtocolFormDep,
    ListProtocolFormsDep,
    SeedDefaultProtocolFormsDep,
    UpdateProtocolFormDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/protocol-forms", tags=["protocol-forms"])


class ProtocolFormReadoutTemplate(BaseModel):
    name: str
    data_type: str
    unit: str | None = None
    aggregation: str = "none"
    normalization: str = "none"
    is_calculated: bool = False
    calculation_formula: str | None = None
    pick_list_values: list[Any] | None = None
    dose_response_config: dict[str, Any] | None = None


class ProtocolFormConditionTemplate(BaseModel):
    name: str
    data_type: str
    unit: str | None = None
    pick_list_values: list[str] | None = None


class ProtocolFormOntologyDefaultTemplate(BaseModel):
    slot_name: str
    terms: list[dict[str, Any]] = []


class ProtocolFormResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    protocol_type: str | None = None
    is_default: bool
    category_id: uuid.UUID | None = None
    assay_format_from_target: bool = False
    readout_templates: list[ProtocolFormReadoutTemplate]
    condition_templates: list[ProtocolFormConditionTemplate] | None = None
    ontology_defaults: list[ProtocolFormOntologyDefaultTemplate] | None = None
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
            category_id=form.category_id,
            assay_format_from_target=form.assay_format_from_target,
            readout_templates=[
                ProtocolFormReadoutTemplate(**asdict(r)) for r in form.readout_templates
            ],
            condition_templates=[
                ProtocolFormConditionTemplate(**asdict(c)) for c in form.condition_templates
            ]
            if form.condition_templates
            else None,
            ontology_defaults=[
                ProtocolFormOntologyDefaultTemplate(**asdict(o)) for o in form.ontology_defaults
            ]
            if form.ontology_defaults
            else None,
            version=form.version,
        )


class CreateProtocolFormBody(BaseModel):
    name: str
    description: str | None = None
    protocol_type: str | None = None
    is_default: bool = False
    category_id: uuid.UUID | None = None
    assay_format_from_target: bool = False
    readout_templates: list[ProtocolFormReadoutTemplate]
    condition_templates: list[ProtocolFormConditionTemplate] | None = None
    ontology_defaults: list[ProtocolFormOntologyDefaultTemplate] | None = None


class UpdateProtocolFormBody(BaseModel):
    name: str | None = None
    description: str | None = None
    protocol_type: str | None = None
    is_default: bool | None = None
    category_id: uuid.UUID | None = None
    assay_format_from_target: bool | None = None
    readout_templates: list[ProtocolFormReadoutTemplate] | None = None
    condition_templates: list[ProtocolFormConditionTemplate] | None = None
    ontology_defaults: list[ProtocolFormOntologyDefaultTemplate] | None = None


@router.get("", response_model=list[ProtocolFormResponse])
async def list_protocol_forms(
    auth: AuthDep,
    use_case: ListProtocolFormsDep,
) -> list[ProtocolFormResponse]:
    query = ListProtocolFormsQuery(workspace_id=auth.workspace_id)
    forms = result_to_response(await use_case(query, auth=auth))
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
        category_id=body.category_id,
        assay_format_from_target=body.assay_format_from_target,
        readout_templates=[t.model_dump() for t in body.readout_templates],
        condition_templates=[t.model_dump() for t in body.condition_templates]
        if body.condition_templates is not None
        else None,
        ontology_defaults=[t.model_dump() for t in body.ontology_defaults]
        if body.ontology_defaults is not None
        else None,
    )
    form = result_to_response(await use_case(command, auth=auth))
    return ProtocolFormResponse.from_domain(form)


@router.post("/defaults", response_model=list[ProtocolFormResponse])
async def add_default_protocol_forms(
    auth: AuthDep, use_case: SeedDefaultProtocolFormsDep
) -> list[ProtocolFormResponse]:
    """Add every shipped default form the workspace lacks (existing forms untouched); returns
    the forms it added."""
    forms = result_to_response(
        await use_case(SeedDefaultProtocolFormsCommand(workspace_id=auth.workspace_id), auth=auth)
    )
    return [ProtocolFormResponse.from_domain(f) for f in forms]


@router.patch("/{form_id}", response_model=ProtocolFormResponse)
async def update_protocol_form(
    form_id: uuid.UUID,
    body: UpdateProtocolFormBody,
    auth: AuthDep,
    use_case: UpdateProtocolFormDep,
) -> ProtocolFormResponse:

    cmd_fields: dict[str, Any] = {
        "workspace_id": auth.workspace_id,
        "form_id": form_id,
    }
    for attr in (
        "name",
        "description",
        "protocol_type",
        "is_default",
        "category_id",
        "assay_format_from_target",
    ):
        cmd_fields[attr] = getattr(body, attr) if attr in body.model_fields_set else UNSET
    for attr in ("readout_templates", "condition_templates", "ontology_defaults"):
        if attr in body.model_fields_set:
            templates = getattr(body, attr)
            cmd_fields[attr] = None if templates is None else [t.model_dump() for t in templates]
        else:
            cmd_fields[attr] = UNSET

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
