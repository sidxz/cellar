"""Custom field definition CRUD endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.workspace_config.create_custom_field import (
    CreateCustomField,
    CreateCustomFieldCommand,
)
from chem_vault.application.workspace_config.delete_custom_field import (
    DeleteCustomField,
    DeleteCustomFieldCommand,
)
from chem_vault.application.workspace_config.list_custom_fields import (
    ListCustomFields,
    ListCustomFieldsQuery,
)
from chem_vault.application.workspace_config.update_custom_field import (
    UpdateCustomField,
    UpdateCustomFieldCommand,
    UNSET,
)
from chem_vault.domain.workspace_config.custom_field_definition import CustomFieldDefinition
from chem_vault.interface.dependencies import (
    AuthDep,
    CreateCustomFieldDep,
    DeleteCustomFieldDep,
    ListCustomFieldsDep,
    UpdateCustomFieldDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/custom-fields", tags=["custom-fields"])


class CustomFieldResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    label: str
    data_type: str
    applies_to: str
    is_required: bool
    default_value: Any | None = None
    display_order: int
    pick_list_values: list[str] | None = None
    vocabulary_id: uuid.UUID | None = None
    is_active: bool
    version: int

    @classmethod
    def from_domain(cls, cfd: CustomFieldDefinition) -> CustomFieldResponse:
        return cls(
            id=cfd.id,
            workspace_id=cfd.workspace_id,
            name=cfd.name,
            label=cfd.label,
            data_type=cfd.data_type.value,
            applies_to=cfd.applies_to.value,
            is_required=cfd.is_required,
            default_value=cfd.default_value,
            display_order=cfd.display_order,
            pick_list_values=cfd.pick_list_values,
            vocabulary_id=cfd.vocabulary_id,
            is_active=cfd.is_active,
            version=cfd.version,
        )


class CreateCustomFieldBody(BaseModel):
    name: str
    label: str
    data_type: str
    applies_to: str
    is_required: bool = False
    default_value: Any | None = None
    display_order: int = 0
    pick_list_values: list[str] | None = None
    vocabulary_id: uuid.UUID | None = None


class UpdateCustomFieldBody(BaseModel):
    label: str | None = None
    is_required: bool | None = None
    default_value: Any | None = None
    display_order: int | None = None
    pick_list_values: list[str] | None = None
    vocabulary_id: uuid.UUID | None = None
    is_active: bool | None = None


@router.get("", response_model=list[CustomFieldResponse])
async def list_custom_fields(
    auth: AuthDep,
    use_case: ListCustomFieldsDep,
    applies_to: str | None = None,
    active_only: bool = True,
) -> list[CustomFieldResponse]:
    query = ListCustomFieldsQuery(
        workspace_id=auth.workspace_id,
        applies_to=applies_to,
        active_only=active_only,
    )
    fields = result_to_response(await use_case(query))
    return [CustomFieldResponse.from_domain(f) for f in fields]


@router.post("", response_model=CustomFieldResponse, status_code=201)
async def create_custom_field(
    body: CreateCustomFieldBody,
    auth: AuthDep,
    use_case: CreateCustomFieldDep,
) -> CustomFieldResponse:
    command = CreateCustomFieldCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        label=body.label,
        data_type=body.data_type,
        applies_to=body.applies_to,
        is_required=body.is_required,
        default_value=body.default_value,
        display_order=body.display_order,
        pick_list_values=body.pick_list_values,
        vocabulary_id=body.vocabulary_id,
    )
    cfd = result_to_response(await use_case(command, auth=auth))
    return CustomFieldResponse.from_domain(cfd)


@router.patch("/{field_id}", response_model=CustomFieldResponse)
async def update_custom_field(
    field_id: uuid.UUID,
    body: UpdateCustomFieldBody,
    auth: AuthDep,
    use_case: UpdateCustomFieldDep,
) -> CustomFieldResponse:
    cmd_fields: dict[str, Any] = {
        "workspace_id": auth.workspace_id,
        "field_id": field_id,
    }
    for attr in (
        "label",
        "is_required",
        "default_value",
        "display_order",
        "pick_list_values",
        "vocabulary_id",
        "is_active",
    ):
        cmd_fields[attr] = getattr(body, attr) if attr in body.model_fields_set else UNSET

    command = UpdateCustomFieldCommand(**cmd_fields)
    cfd = result_to_response(await use_case(command, auth=auth))
    return CustomFieldResponse.from_domain(cfd)


@router.delete("/{field_id}", status_code=204)
async def delete_custom_field(
    field_id: uuid.UUID,
    auth: AuthDep,
    use_case: DeleteCustomFieldDep,
) -> None:
    command = DeleteCustomFieldCommand(
        workspace_id=auth.workspace_id,
        field_id=field_id,
    )
    result_to_response(await use_case(command, auth=auth))
