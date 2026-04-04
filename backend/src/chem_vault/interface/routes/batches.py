"""Batch API routes."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.inventory.create_batch import CreateBatchCommand
from chem_vault.application.inventory.get_batch import GetBatch, ListBatchesByMolecule
from chem_vault.application.inventory.create_batch import CreateBatch
from chem_vault.interface.dependencies import AuthDep
from chem_vault.interface.error_handlers import result_to_response

from typing import Annotated
from fastapi import Depends
from lagom import Container
from chem_vault.interface.dependencies import get_container

router = APIRouter(prefix="/api/v1", tags=["batches"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------

class BatchResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    batch_number: str
    salt_form: str | None = None
    purity: float | None = None
    amount_value: float
    amount_unit: str
    source: str
    chemist: uuid.UUID
    supplier_org_id: uuid.UUID | None = None
    vendor_catalog_number: str | None = None
    vendor_lot_number: str | None = None
    synthesis_date: date | None = None
    expiry_date: date | None = None
    appearance: str | None = None

    @classmethod
    def from_domain(cls, b) -> BatchResponse:  # type: ignore[no-untyped-def]
        return cls(
            id=b.id,
            workspace_id=b.workspace_id,
            molecule_id=b.molecule_id,
            batch_number=b.batch_number.value,
            salt_form=b.salt_form,
            purity=b.purity,
            amount_value=b.amount.value,
            amount_unit=b.amount.unit.value,
            source=b.source.value,
            chemist=b.chemist,
            supplier_org_id=b.supplier_org_id,
            vendor_catalog_number=b.vendor_catalog_number,
            vendor_lot_number=b.vendor_lot_number,
            synthesis_date=b.synthesis_date,
            expiry_date=b.expiry_date,
            appearance=b.appearance,
        )


class CreateBatchRequest(BaseModel):
    molecule_id: uuid.UUID
    source: str
    amount_value: float
    amount_unit: str
    salt_form: str | None = None
    purity: float | None = None
    concentration_value: float | None = None
    concentration_unit: str | None = None
    supplier_org_id: uuid.UUID | None = None
    vendor_catalog_number: str | None = None
    vendor_lot_number: str | None = None
    synthesis_date: date | None = None
    expiry_date: date | None = None
    notebook_reference: str | None = None
    appearance: str | None = None
    custom_fields: dict | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _get_create_batch(container: Annotated[Container, Depends(get_container)]) -> CreateBatch:
    return container[CreateBatch]

def _get_batch(container: Annotated[Container, Depends(get_container)]) -> GetBatch:
    return container[GetBatch]

def _get_list_batches(container: Annotated[Container, Depends(get_container)]) -> ListBatchesByMolecule:
    return container[ListBatchesByMolecule]


@router.post("/batches", response_model=BatchResponse, status_code=201)
async def create_batch(
    auth: AuthDep,
    body: CreateBatchRequest,
    uc: Annotated[CreateBatch, Depends(_get_create_batch)],
) -> BatchResponse:
    cmd = CreateBatchCommand(
        workspace_id=auth.workspace_id,
        molecule_id=body.molecule_id,
        source=body.source,
        chemist=auth.user_id,
        amount_value=body.amount_value,
        amount_unit=body.amount_unit,
        salt_form=body.salt_form,
        purity=body.purity,
        concentration_value=body.concentration_value,
        concentration_unit=body.concentration_unit,
        supplier_org_id=body.supplier_org_id,
        vendor_catalog_number=body.vendor_catalog_number,
        vendor_lot_number=body.vendor_lot_number,
        synthesis_date=body.synthesis_date,
        expiry_date=body.expiry_date,
        notebook_reference=body.notebook_reference,
        appearance=body.appearance,
        custom_fields=body.custom_fields,
    )
    result = await uc(cmd, auth=auth)
    batch = result_to_response(result)
    return BatchResponse.from_domain(batch)


@router.get("/batches/{batch_id}", response_model=BatchResponse)
async def get_batch(
    batch_id: uuid.UUID,
    auth: AuthDep,
    uc: Annotated[GetBatch, Depends(_get_batch)],
) -> BatchResponse:
    result = await uc(batch_id)
    batch = result_to_response(result)
    return BatchResponse.from_domain(batch)


@router.get("/molecules/{molecule_id}/batches", response_model=list[BatchResponse])
async def list_batches_by_molecule(
    molecule_id: uuid.UUID,
    auth: AuthDep,
    uc: Annotated[ListBatchesByMolecule, Depends(_get_list_batches)],
) -> list[BatchResponse]:
    result = await uc(molecule_id)
    batches = result_to_response(result)
    return [BatchResponse.from_domain(b) for b in batches]
