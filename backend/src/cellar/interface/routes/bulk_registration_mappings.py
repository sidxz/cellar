"""Saved column mappings for the bulk-registration wizard."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.chemical_registration.bulk_registration_mappings import (
    CreateBulkRegistrationMappingCommand,
    DeleteBulkRegistrationMappingCommand,
    ListBulkRegistrationMappingsQuery,
    UpdateBulkRegistrationMappingCommand,
)
from cellar.domain.chemical_registration.bulk_registration_mapping import (
    BulkRegistrationMapping,
)
from cellar.interface.dependencies import (
    AuthDep,
    CreateBulkRegistrationMappingDep,
    DeleteBulkRegistrationMappingDep,
    ListBulkRegistrationMappingsDep,
    UpdateBulkRegistrationMappingDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.routes.bulk_registration import ColumnMappingColumnBody

router = APIRouter(prefix="/api/v1/bulk-registration-mappings", tags=["bulk-registration"])


class BulkRegistrationMappingResponse(BaseModel):
    id: uuid.UUID
    name: str
    columns: list[ColumnMappingColumnBody]
    created_by: uuid.UUID
    created_at: datetime | None
    updated_at: datetime | None


class CreateBulkRegistrationMappingRequest(BaseModel):
    name: str
    columns: list[ColumnMappingColumnBody]


class UpdateBulkRegistrationMappingRequest(BaseModel):
    name: str | None = None
    columns: list[ColumnMappingColumnBody] | None = None


def _to_response(m: BulkRegistrationMapping) -> BulkRegistrationMappingResponse:
    return BulkRegistrationMappingResponse(
        id=m.id,
        name=m.name,
        columns=[ColumnMappingColumnBody.model_validate(c) for c in m.columns],
        created_by=m.created_by,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _columns(cols: list[ColumnMappingColumnBody]) -> list[dict[str, Any]]:
    return [c.model_dump(mode="json") for c in cols]


@router.get("", response_model=list[BulkRegistrationMappingResponse])
async def list_bulk_registration_mappings(
    auth: AuthDep, uc: ListBulkRegistrationMappingsDep
) -> list[BulkRegistrationMappingResponse]:
    result = await uc(ListBulkRegistrationMappingsQuery(workspace_id=auth.workspace_id), auth=auth)
    return [_to_response(m) for m in result_to_response(result)]


@router.post("", response_model=BulkRegistrationMappingResponse, status_code=201)
async def create_bulk_registration_mapping(
    auth: AuthDep,
    body: CreateBulkRegistrationMappingRequest,
    uc: CreateBulkRegistrationMappingDep,
) -> BulkRegistrationMappingResponse:
    result = await uc(
        CreateBulkRegistrationMappingCommand(
            workspace_id=auth.workspace_id,
            name=body.name,
            columns=_columns(body.columns),
            created_by=auth.user_id,
        ),
        auth=auth,
    )
    return _to_response(result_to_response(result))


@router.patch("/{mapping_id}", response_model=BulkRegistrationMappingResponse)
async def update_bulk_registration_mapping(
    mapping_id: uuid.UUID,
    auth: AuthDep,
    body: UpdateBulkRegistrationMappingRequest,
    uc: UpdateBulkRegistrationMappingDep,
) -> BulkRegistrationMappingResponse:
    result = await uc(
        UpdateBulkRegistrationMappingCommand(
            workspace_id=auth.workspace_id,
            mapping_id=mapping_id,
            name=body.name,
            columns=_columns(body.columns) if body.columns is not None else None,
        ),
        auth=auth,
    )
    return _to_response(result_to_response(result))


@router.delete("/{mapping_id}", status_code=204)
async def delete_bulk_registration_mapping(
    mapping_id: uuid.UUID, auth: AuthDep, uc: DeleteBulkRegistrationMappingDep
) -> None:
    result_to_response(
        await uc(
            DeleteBulkRegistrationMappingCommand(
                workspace_id=auth.workspace_id, mapping_id=mapping_id
            ),
            auth=auth,
        )
    )
