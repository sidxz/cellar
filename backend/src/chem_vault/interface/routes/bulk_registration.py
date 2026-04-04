"""Bulk registration API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from chem_vault.application.chemical_registration.bulk_registration_service import (
    BulkRegistrationItem,
    BulkRegistrationItemResult,
    StartBulkRegistrationCommand,
)
from chem_vault.domain.chemical_registration.enums import BulkRegistrationFileFormat
from chem_vault.infrastructure.parsers.chemical_file_parser import get_parser
from chem_vault.interface.dependencies import AuthDep, BulkRegistrationServiceDep
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/bulk-registrations", tags=["bulk-registration"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class BulkRegistrationItemResponse(BaseModel):
    row_index: int
    success: bool
    is_new: bool = False
    molecule_id: uuid.UUID | None = None
    error: str | None = None

    @classmethod
    def from_item(cls, item: BulkRegistrationItemResult) -> BulkRegistrationItemResponse:
        return cls(
            row_index=item.row_index,
            success=item.success,
            is_new=item.is_new,
            molecule_id=item.molecule_id,
            error=item.error,
        )


class BulkRegistrationResponse(BaseModel):
    id: uuid.UUID
    status: str
    total_count: int
    registered_count: int
    duplicate_count: int
    error_count: int
    items: list[BulkRegistrationItemResponse]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", response_model=BulkRegistrationResponse, status_code=201)
async def start_bulk_registration(
    auth: AuthDep,
    service: BulkRegistrationServiceDep,
    file: UploadFile = File(...),
    originating_org_id: uuid.UUID = Form(...),
    file_format: str = Form(...),
) -> BulkRegistrationResponse:
    """Upload a file (SDF, CSV, XLSX) to register molecules in bulk."""
    content = await file.read()

    # Parse in the interface layer (infrastructure dependency stays out of application)
    fmt = BulkRegistrationFileFormat(file_format)
    parser = get_parser(fmt)
    parsed = parser.parse(content, file.filename or "unknown")

    # Convert infrastructure DTOs to application DTOs
    items = [
        BulkRegistrationItem(
            row_index=p.row_index,
            name=p.name,
            smiles=p.smiles,
            molecule_type=p.molecule_type,
            external_ids=p.external_ids,
            error=p.error,
        )
        for p in parsed
    ]

    cmd = StartBulkRegistrationCommand(
        workspace_id=auth.workspace_id,
        source_file=file.filename or "unknown",
        file_format=file_format,
        items=items,
        submitted_by=auth.user_id,
        originating_org_id=originating_org_id,
    )

    result = await service.execute(cmd, auth=auth)
    outcome = result_to_response(result)

    return BulkRegistrationResponse(
        id=outcome.bulk_registration.id,
        status=outcome.bulk_registration.status.value,
        total_count=outcome.bulk_registration.total_count,
        registered_count=outcome.bulk_registration.registered_count,
        duplicate_count=outcome.bulk_registration.duplicate_count,
        error_count=outcome.bulk_registration.error_count,
        items=[BulkRegistrationItemResponse.from_item(i) for i in outcome.item_results],
    )
