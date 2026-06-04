"""Inventory hub API routes — global batch and sample lists with molecule context."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from cellar.application.inventory.get_inventory_summary import (
    GetInventorySummaryQuery,
)
from cellar.application.inventory.list_batches_global import (
    ListBatchesGlobalQuery,
)
from cellar.application.inventory.list_samples_global import (
    ListSamplesGlobalQuery,
)
from cellar.application.inventory.manage_storage import (
    ListStorageLocationsQuery,
)
from cellar.interface.dependencies import (
    AuthDep,
    GetInventorySummaryDep,
    ListBatchesGlobalDep,
    ListSamplesGlobalDep,
    ListStorageLocationsWithCountsDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.pagination import PaginatedResponse

router = APIRouter(prefix="/api/v1", tags=["inventory-hub"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class BatchListItemResponse(BaseModel):
    id: uuid.UUID
    batch_number: str
    molecule_id: uuid.UUID
    molecule_name: str
    molecule_registration_number: str
    source: str
    amount_value: float
    amount_unit: str
    purity: float | None = None
    salt_name: str | None = None
    appearance: str | None = None
    expiry_date: date | None = None
    sample_count: int
    has_low_stock_sample: bool
    created_at: datetime


class SampleListItemResponse(BaseModel):
    id: uuid.UUID
    barcode: str
    batch_id: uuid.UUID
    batch_number: str
    molecule_id: uuid.UUID
    molecule_name: str
    molecule_registration_number: str
    container_type: str
    amount_value: float
    amount_unit: str
    status: str
    solvent: str | None = None
    freeze_thaw_count: int
    low_stock_threshold: float | None = None
    location_id: uuid.UUID | None = None
    location_name: str | None = None
    location_type: str | None = None
    created_at: datetime


class ActivityItemResponse(BaseModel):
    description: str
    entity_type: str
    entity_id: uuid.UUID
    occurred_at: datetime


class InventorySummaryResponse(BaseModel):
    low_stock_count: int
    expiring_soon_count: int
    pending_requests_count: int
    recent_activity: list[ActivityItemResponse]


class StorageLocationWithCountResponse(BaseModel):
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
    sample_count: int = 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/batches", response_model=PaginatedResponse[BatchListItemResponse])
async def list_batches_global(
    auth: AuthDep,
    uc: ListBatchesGlobalDep,
    search: str | None = None,
    source: list[str] | None = Query(None),
    expiring_within_days: int | None = None,
    tags: list[uuid.UUID] | None = Query(default=None),
    tag_logic: Literal["any", "all"] = Query(default="any"),
    cursor: str | None = None,
    page_size: int | None = None,
) -> PaginatedResponse[BatchListItemResponse]:
    """List all batches across all molecules with molecule context and sample counts."""
    query = ListBatchesGlobalQuery(
        workspace_id=auth.workspace_id,
        search=search,
        sources=source,
        expiring_within_days=expiring_within_days,
        tags=tags,
        tag_logic=tag_logic,
        cursor=cursor,
        limit=page_size,
    )
    page = result_to_response(await uc(query, auth=auth))
    return PaginatedResponse(
        items=[BatchListItemResponse(**row) for row in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/samples", response_model=PaginatedResponse[SampleListItemResponse])
async def list_samples_global(
    auth: AuthDep,
    uc: ListSamplesGlobalDep,
    search: str | None = None,
    status: list[str] | None = Query(None),
    location_id: uuid.UUID | None = None,
    container_type: list[str] | None = Query(None),
    low_stock: bool = False,
    cursor: str | None = None,
    page_size: int | None = None,
) -> PaginatedResponse[SampleListItemResponse]:
    """List all samples across all batches with batch/molecule/location context."""
    query = ListSamplesGlobalQuery(
        workspace_id=auth.workspace_id,
        search=search,
        statuses=status,
        location_id=location_id,
        container_types=container_type,
        low_stock=low_stock,
        cursor=cursor,
        limit=page_size,
    )
    page = result_to_response(await uc(query, auth=auth))
    return PaginatedResponse(
        items=[SampleListItemResponse(**row) for row in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/inventory/summary", response_model=InventorySummaryResponse)
async def get_inventory_summary(
    auth: AuthDep,
    uc: GetInventorySummaryDep,
) -> InventorySummaryResponse:
    """Dashboard metrics: low stock, expiring batches, pending requests, recent activity."""
    query = GetInventorySummaryQuery(workspace_id=auth.workspace_id)
    summary = result_to_response(await uc(query, auth=auth))
    return InventorySummaryResponse(
        low_stock_count=summary.low_stock_count,
        expiring_soon_count=summary.expiring_soon_count,
        pending_requests_count=summary.pending_requests_count,
        recent_activity=[
            ActivityItemResponse(
                description=a.description,
                entity_type=a.entity_type,
                entity_id=a.entity_id,
                occurred_at=a.occurred_at,
            )
            for a in summary.recent_activity
        ],
    )


@router.get(
    "/storage-locations-summary",
    response_model=list[StorageLocationWithCountResponse],
)
async def list_storage_locations_with_counts(
    auth: AuthDep,
    uc: ListStorageLocationsWithCountsDep,
) -> list[StorageLocationWithCountResponse]:
    """Storage locations with available-sample counts for the storage browser."""
    query = ListStorageLocationsQuery(workspace_id=auth.workspace_id)
    rows = result_to_response(await uc(query, auth=auth))
    return [StorageLocationWithCountResponse(**r) for r in rows]
