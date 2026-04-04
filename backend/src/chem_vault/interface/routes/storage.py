"""Storage location API routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from lagom import Container
from pydantic import BaseModel

from chem_vault.application.inventory.manage_storage import (
    CreateStorageLocation,
    CreateStorageLocationCommand,
    GetStorageLocationChildren,
    ListStorageLocations,
)
from chem_vault.interface.dependencies import AuthDep, get_container
from chem_vault.interface.error_handlers import result_to_response

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
    def from_domain(cls, loc) -> StorageLocationResponse:  # type: ignore[no-untyped-def]
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


# ---------------------------------------------------------------------------
# Deps
# ---------------------------------------------------------------------------

def _create(c: Annotated[Container, Depends(get_container)]) -> CreateStorageLocation:
    return c[CreateStorageLocation]

def _list(c: Annotated[Container, Depends(get_container)]) -> ListStorageLocations:
    return c[ListStorageLocations]

def _children(c: Annotated[Container, Depends(get_container)]) -> GetStorageLocationChildren:
    return c[GetStorageLocationChildren]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", response_model=StorageLocationResponse, status_code=201)
async def create_storage_location(
    auth: AuthDep,
    body: CreateStorageLocationRequest,
    uc: Annotated[CreateStorageLocation, Depends(_create)],
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


@router.get("", response_model=list[StorageLocationResponse])
async def list_storage_locations(
    auth: AuthDep,
    uc: Annotated[ListStorageLocations, Depends(_list)],
) -> list[StorageLocationResponse]:
    result = await uc(auth.workspace_id)
    locations = result_to_response(result)
    return [StorageLocationResponse.from_domain(loc) for loc in locations]


@router.get("/{location_id}/children", response_model=list[StorageLocationResponse])
async def get_children(
    location_id: uuid.UUID,
    auth: AuthDep,
    uc: Annotated[GetStorageLocationChildren, Depends(_children)],
) -> list[StorageLocationResponse]:
    result = await uc(location_id)
    children = result_to_response(result)
    return [StorageLocationResponse.from_domain(loc) for loc in children]
