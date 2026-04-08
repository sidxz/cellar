"""Registration form template CRUD endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.workspace_config.create_registration_form import (
    CreateRegistrationFormCommand,
)
from chem_vault.application.workspace_config.delete_registration_form import (
    DeleteRegistrationFormCommand,
)
from chem_vault.application.workspace_config.get_registration_form import (
    GetRegistrationFormQuery,
)
from chem_vault.application.workspace_config.list_registration_forms import (
    ListRegistrationFormsQuery,
)
from chem_vault.application.workspace_config.update_registration_form import (
    UpdateRegistrationFormCommand,
    UNSET,
)
from chem_vault.domain.workspace_config.enums import FieldTarget
from chem_vault.domain.workspace_config.registration_form import RegistrationForm
from chem_vault.interface.dependencies import (
    AuthDep,
    CreateRegistrationFormDep,
    DeleteRegistrationFormDep,
    GetRegistrationFormDep,
    ListRegistrationFormsDep,
    UpdateRegistrationFormDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/registration-forms", tags=["registration-forms"])


class RegistrationFormResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    applies_to: str
    is_default: bool
    field_overrides: list[dict[str, Any]]
    version: int

    @classmethod
    def from_domain(cls, form: RegistrationForm) -> "RegistrationFormResponse":
        return cls(
            id=form.id,
            workspace_id=form.workspace_id,
            name=form.name,
            applies_to=form.applies_to.value,
            is_default=form.is_default,
            field_overrides=[o.model_dump() for o in form.field_overrides],
            version=form.version,
        )


class CreateRegistrationFormBody(BaseModel):
    name: str
    applies_to: FieldTarget
    is_default: bool = False
    field_overrides: list[dict[str, Any]] = []


class UpdateRegistrationFormBody(BaseModel):
    name: str | None = None
    is_default: bool | None = None
    field_overrides: list[dict[str, Any]] | None = None


@router.get("", response_model=list[RegistrationFormResponse])
async def list_registration_forms(
    auth: AuthDep,
    use_case: ListRegistrationFormsDep,
    applies_to: FieldTarget | None = None,
) -> list[RegistrationFormResponse]:
    query = ListRegistrationFormsQuery(
        workspace_id=auth.workspace_id,
        applies_to=applies_to,
    )
    forms = result_to_response(await use_case(query))
    return [RegistrationFormResponse.from_domain(f) for f in forms]


@router.get("/{form_id}", response_model=RegistrationFormResponse)
async def get_registration_form(
    form_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetRegistrationFormDep,
) -> RegistrationFormResponse:
    query = GetRegistrationFormQuery(workspace_id=auth.workspace_id, form_id=form_id)
    form = result_to_response(await use_case(query))
    return RegistrationFormResponse.from_domain(form)


@router.post("", response_model=RegistrationFormResponse, status_code=201)
async def create_registration_form(
    body: CreateRegistrationFormBody,
    auth: AuthDep,
    use_case: CreateRegistrationFormDep,
) -> RegistrationFormResponse:
    command = CreateRegistrationFormCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        applies_to=body.applies_to,
        is_default=body.is_default,
        field_overrides=body.field_overrides,
    )
    form = result_to_response(await use_case(command, auth=auth))
    return RegistrationFormResponse.from_domain(form)


@router.patch("/{form_id}", response_model=RegistrationFormResponse)
async def update_registration_form(
    form_id: uuid.UUID,
    body: UpdateRegistrationFormBody,
    auth: AuthDep,
    use_case: UpdateRegistrationFormDep,
) -> RegistrationFormResponse:
    cmd_fields: dict[str, Any] = {
        "workspace_id": auth.workspace_id,
        "form_id": form_id,
    }
    for attr in ("name", "is_default", "field_overrides"):
        cmd_fields[attr] = getattr(body, attr) if attr in body.model_fields_set else UNSET

    command = UpdateRegistrationFormCommand(**cmd_fields)
    form = result_to_response(await use_case(command, auth=auth))
    return RegistrationFormResponse.from_domain(form)


@router.delete("/{form_id}", status_code=204)
async def delete_registration_form(
    form_id: uuid.UUID,
    auth: AuthDep,
    use_case: DeleteRegistrationFormDep,
) -> None:
    command = DeleteRegistrationFormCommand(
        workspace_id=auth.workspace_id,
        form_id=form_id,
    )
    result_to_response(await use_case(command, auth=auth))
