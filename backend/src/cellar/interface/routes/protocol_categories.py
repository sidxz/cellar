"""Protocol categories: each carries the name pattern its protocols follow."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.workspace_config.protocol_categories import (
    CreateProtocolCategoryCommand,
    DeleteProtocolCategoryCommand,
    ListProtocolCategoriesQuery,
    SeedDefaultProtocolCategoriesCommand,
    UpdateProtocolCategoryCommand,
)
from cellar.domain.workspace_config.protocol_category import ProtocolCategory
from cellar.interface.dependencies import (
    AuthDep,
    CreateProtocolCategoryDep,
    DeleteProtocolCategoryDep,
    ListProtocolCategoriesDep,
    SeedDefaultProtocolCategoriesDep,
    UpdateProtocolCategoryDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/protocol-categories", tags=["protocol-categories"])


class ProtocolCategoryResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    label: str
    name_pattern: str
    default_pattern: str
    version: int

    @classmethod
    def from_domain(cls, c: ProtocolCategory) -> ProtocolCategoryResponse:
        return cls(
            id=c.id,
            workspace_id=c.workspace_id,
            label=c.label,
            name_pattern=c.name_pattern,
            default_pattern=c.default_pattern,
            version=c.version,
        )


class CreateProtocolCategoryBody(BaseModel):
    label: str
    name_pattern: str | None = None
    model_config = {"extra": "forbid"}


class UpdateProtocolCategoryBody(BaseModel):
    label: str | None = None
    name_pattern: str | None = None
    model_config = {"extra": "forbid"}


@router.get("", response_model=list[ProtocolCategoryResponse])
async def list_protocol_categories(
    auth: AuthDep, use_case: ListProtocolCategoriesDep
) -> list[ProtocolCategoryResponse]:
    query = ListProtocolCategoriesQuery(workspace_id=auth.workspace_id)
    categories = result_to_response(await use_case(query, auth=auth))
    return [ProtocolCategoryResponse.from_domain(c) for c in categories]


@router.post("", response_model=ProtocolCategoryResponse, status_code=201)
async def create_protocol_category(
    body: CreateProtocolCategoryBody, auth: AuthDep, use_case: CreateProtocolCategoryDep
) -> ProtocolCategoryResponse:
    cmd = CreateProtocolCategoryCommand(
        workspace_id=auth.workspace_id, label=body.label, name_pattern=body.name_pattern
    )
    return ProtocolCategoryResponse.from_domain(result_to_response(await use_case(cmd, auth=auth)))


@router.post("/defaults", response_model=list[ProtocolCategoryResponse])
async def seed_default_protocol_categories(
    auth: AuthDep, use_case: SeedDefaultProtocolCategoriesDep
) -> list[ProtocolCategoryResponse]:
    """Add every shipped default category the workspace lacks (existing ones untouched)."""
    cmd = SeedDefaultProtocolCategoriesCommand(workspace_id=auth.workspace_id)
    categories = result_to_response(await use_case(cmd, auth=auth))
    return [ProtocolCategoryResponse.from_domain(c) for c in categories]


@router.patch("/{category_id}", response_model=ProtocolCategoryResponse)
async def update_protocol_category(
    category_id: uuid.UUID,
    body: UpdateProtocolCategoryBody,
    auth: AuthDep,
    use_case: UpdateProtocolCategoryDep,
) -> ProtocolCategoryResponse:
    cmd = UpdateProtocolCategoryCommand(
        workspace_id=auth.workspace_id,
        category_id=category_id,
        label=body.label,
        name_pattern=body.name_pattern,
    )
    return ProtocolCategoryResponse.from_domain(result_to_response(await use_case(cmd, auth=auth)))


@router.delete("/{category_id}", status_code=204)
async def delete_protocol_category(
    category_id: uuid.UUID, auth: AuthDep, use_case: DeleteProtocolCategoryDep
) -> None:
    cmd = DeleteProtocolCategoryCommand(workspace_id=auth.workspace_id, category_id=category_id)
    result_to_response(await use_case(cmd, auth=auth))
