"""Inventory hub API routes — global batch list with molecule context."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from chem_vault.application.inventory.list_batches_global import (
    ListBatchesGlobal,
    ListBatchesGlobalQuery,
)
from chem_vault.interface.dependencies import AuthDep, ListBatchesGlobalDep
from chem_vault.interface.error_handlers import result_to_response
from chem_vault.interface.pagination import PaginatedResponse

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
    cursor: str | None = None,
    page_size: int | None = None,
) -> PaginatedResponse[BatchListItemResponse]:
    """List all batches across all molecules with molecule context and sample counts."""
    query = ListBatchesGlobalQuery(
        workspace_id=auth.workspace_id,
        search=search,
        sources=source,
        expiring_within_days=expiring_within_days,
        cursor=cursor,
        limit=page_size,
    )
    page = result_to_response(await uc(query, auth=auth))
    return PaginatedResponse(
        items=[BatchListItemResponse(**row) for row in page.items],
        next_cursor=page.next_cursor,
    )
