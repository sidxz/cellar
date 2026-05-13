"""Storage location API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.inventory.delete_storage_location import (
    DeleteStorageLocation,
    DeleteStorageLocationCommand,
)
from cellar.application.inventory.manage_storage import (
    CreateStorageLocation,
    CreateStorageLocationCommand,
    GetStorageLocationChildren,
    GetStorageLocationChildrenQuery,
    ListStorageLocations,
    ListStorageLocationsQuery,
)
from cellar.application.inventory.update_storage_location import (
    UpdateStorageLocation,
    UpdateStorageLocationCommand,
)
from cellar.interface.dependencies import (
    AuthDep,
    CreateStorageLocationDep,
    DeleteStorageLocationDep,
    GetStorageLocationChildrenDep,
    ListStorageLocationsDep,
    UpdateStorageLocationDep,
)
from cellar.domain.inventory.storage_location import StorageLocation
from cellar.interface.error_handlers import result_to_response
from cellar.interface.pagination import PaginatedResponse, clamp_limit, parse_cursor
from cellar.application.shared.sentinel import UNSET

router = APIRouter(prefix="/api/v1/storage-locations", tags=["storage"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class StorageLocationResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    type: str
    parent_id: uuid.UUID | None = None
    barcode: str | None = None
    temperature: str | None = None
    rows: int | None = None
    columns: int | None = None
    capacity: int | None = None

    @classmethod
    def from_domain(cls, loc: StorageLocation) -> StorageLocationResponse:
        return cls(
            id=loc.id,
            workspace_id=loc.workspace_id,
            name=loc.name,
            type=loc.type.value,
            parent_id=loc.parent_id,
            barcode=loc.barcode.value if loc.barcode else None,
            temperature=loc.temperature,
            rows=loc.rows,
            columns=loc.columns,
            capacity=loc.capacity,
        )


class CreateStorageLocationRequest(BaseModel):
    name: str
    type: str
    parent_id: uuid.UUID | None = None
    barcode: str | None = None
    temperature: str | None = None
    rows: int | None = None
    columns: int | None = None
    capacity: int | None = None


class UpdateStorageLocationRequest(BaseModel):
    name: str | None = None
    barcode: str | None = None
    temperature: str | None = None
    rows: int | None = None
    columns: int | None = None
    capacity: int | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", response_model=StorageLocationResponse, status_code=201)
async def create_storage_location(
    auth: AuthDep,
    body: CreateStorageLocationRequest,
    uc: CreateStorageLocationDep,
) -> StorageLocationResponse:
    cmd = CreateStorageLocationCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        type=body.type,
        parent_id=body.parent_id,
        barcode=body.barcode,
        temperature=body.temperature,
        rows=body.rows,
        columns=body.columns,
        capacity=body.capacity,
    )
    result = await uc(cmd, auth=auth)
    return StorageLocationResponse.from_domain(result_to_response(result))


@router.get("", response_model=PaginatedResponse[StorageLocationResponse])
async def list_storage_locations(
    auth: AuthDep,
    uc: ListStorageLocationsDep,
    cursor: str | None = None,
    limit: int | None = None,
) -> PaginatedResponse[StorageLocationResponse]:
    query = ListStorageLocationsQuery(
        workspace_id=auth.workspace_id,
        cursor_id=parse_cursor(cursor),
        limit=clamp_limit(limit),
    )
    page = result_to_response(await uc(query, auth=auth))
    return PaginatedResponse(
        items=[StorageLocationResponse.from_domain(loc) for loc in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{location_id}/children", response_model=list[StorageLocationResponse])
async def get_children(
    location_id: uuid.UUID,
    auth: AuthDep,
    uc: GetStorageLocationChildrenDep,
) -> list[StorageLocationResponse]:
    result = await uc(
        GetStorageLocationChildrenQuery(workspace_id=auth.workspace_id, parent_id=location_id),
        auth=auth,
    )
    children = result_to_response(result)
    return [StorageLocationResponse.from_domain(loc) for loc in children]


@router.patch("/{location_id}", response_model=StorageLocationResponse)
async def update_storage_location(
    location_id: uuid.UUID,
    body: UpdateStorageLocationRequest,
    auth: AuthDep,
    uc: UpdateStorageLocationDep,
) -> StorageLocationResponse:

    cmd = UpdateStorageLocationCommand(
        workspace_id=auth.workspace_id,
        location_id=location_id,
        name=body.name if "name" in body.model_fields_set else UNSET,
        barcode=body.barcode if "barcode" in body.model_fields_set else UNSET,
        temperature=body.temperature if "temperature" in body.model_fields_set else UNSET,
        rows=body.rows if "rows" in body.model_fields_set else UNSET,
        columns=body.columns if "columns" in body.model_fields_set else UNSET,
        capacity=body.capacity if "capacity" in body.model_fields_set else UNSET,
    )
    result = await uc(cmd, auth=auth)
    return StorageLocationResponse.from_domain(result_to_response(result))


@router.delete("/{location_id}", status_code=204)
async def delete_storage_location(
    location_id: uuid.UUID,
    auth: AuthDep,
    uc: DeleteStorageLocationDep,
) -> None:
    cmd = DeleteStorageLocationCommand(workspace_id=auth.workspace_id, location_id=location_id)
    result_to_response(await uc(cmd, auth=auth))
