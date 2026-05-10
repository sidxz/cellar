"""Batch API routes."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.inventory.create_batch import CreateBatch, CreateBatchCommand
from chem_vault.application.inventory.get_batch import (
    GetBatch,
    GetBatchQuery,
    ListBatchesByMolecule,
    ListBatchesByMoleculeQuery,
)
from chem_vault.application.inventory.update_batch import UpdateBatch, UpdateBatchCommand
from chem_vault.domain.inventory.batch import Batch
from chem_vault.interface.dependencies import (
    AuthDep,
    CreateBatchDep,
    GetBatchDep,
    ListBatchesByMoleculeDep,
    UpdateBatchDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["batches"])


class BatchResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    batch_number: str
    version: int
    salt_entry_id: uuid.UUID | None = None
    salt_name: str | None = None
    salt_smiles: str | None = None
    salt_stoichiometry: int = 1
    formula_weight: float | None = None
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
    def from_domain(cls, b: Batch) -> BatchResponse:
        return cls(
            id=b.id,
            workspace_id=b.workspace_id,
            molecule_id=b.molecule_id,
            batch_number=b.batch_number.value,
            version=b.version,
            salt_entry_id=b.salt_entry_id,
            salt_name=b.salt_name,
            salt_smiles=b.salt_smiles,
            salt_stoichiometry=b.salt_stoichiometry,
            formula_weight=b.formula_weight,
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
    salt_entry_id: uuid.UUID | None = None
    salt_name: str | None = None
    salt_smiles: str | None = None
    salt_stoichiometry: int = 1
    formula_weight: float | None = None
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


class UpdateBatchRequest(BaseModel):
    salt_entry_id: uuid.UUID | None = None
    salt_name: str | None = None
    salt_smiles: str | None = None
    salt_stoichiometry: int | None = None
    formula_weight: float | None = None
    purity: float | None = None
    amount_value: float | None = None
    amount_unit: str | None = None
    concentration_value: float | None = None
    concentration_unit: str | None = None
    appearance: str | None = None
    expiry_date: date | None = None
    notebook_reference: str | None = None
    storage_conditions_notes: str | None = None
    custom_fields: dict | None = None


@router.post("/batches", response_model=BatchResponse, status_code=201)
async def create_batch(
    auth: AuthDep,
    body: CreateBatchRequest,
    uc: CreateBatchDep,
) -> BatchResponse:
    cmd = CreateBatchCommand(
        workspace_id=auth.workspace_id,
        molecule_id=body.molecule_id,
        source=body.source,
        chemist=auth.user_id,
        amount_value=body.amount_value,
        amount_unit=body.amount_unit,
        salt_entry_id=body.salt_entry_id,
        salt_name=body.salt_name,
        salt_smiles=body.salt_smiles,
        salt_stoichiometry=body.salt_stoichiometry,
        formula_weight=body.formula_weight,
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
    return BatchResponse.from_domain(result_to_response(result))


@router.get("/batches/{batch_id}", response_model=BatchResponse)
async def get_batch(
    batch_id: uuid.UUID,
    auth: AuthDep,
    uc: GetBatchDep,
) -> BatchResponse:
    result = await uc(
        GetBatchQuery(workspace_id=auth.workspace_id, batch_id=batch_id),
        auth=auth,
    )
    return BatchResponse.from_domain(result_to_response(result))


@router.get("/molecules/{molecule_id}/batches", response_model=list[BatchResponse])
async def list_batches_by_molecule(
    molecule_id: uuid.UUID,
    auth: AuthDep,
    uc: ListBatchesByMoleculeDep,
) -> list[BatchResponse]:
    result = await uc(
        ListBatchesByMoleculeQuery(workspace_id=auth.workspace_id, molecule_id=molecule_id),
        auth=auth,
    )
    batches = result_to_response(result)
    return [BatchResponse.from_domain(b) for b in batches]


@router.patch("/batches/{batch_id}", response_model=BatchResponse)
async def update_batch(
    batch_id: uuid.UUID,
    body: UpdateBatchRequest,
    auth: AuthDep,
    uc: UpdateBatchDep,
) -> BatchResponse:
    from chem_vault.application.shared.sentinel import UNSET

    cmd = UpdateBatchCommand(
        workspace_id=auth.workspace_id,
        batch_id=batch_id,
        salt_entry_id=body.salt_entry_id if "salt_entry_id" in body.model_fields_set else UNSET,
        salt_name=body.salt_name if "salt_name" in body.model_fields_set else UNSET,
        salt_smiles=body.salt_smiles if "salt_smiles" in body.model_fields_set else UNSET,
        salt_stoichiometry=body.salt_stoichiometry if "salt_stoichiometry" in body.model_fields_set else UNSET,
        formula_weight=body.formula_weight if "formula_weight" in body.model_fields_set else UNSET,
        purity=body.purity if "purity" in body.model_fields_set else UNSET,
        amount_value=body.amount_value if "amount_value" in body.model_fields_set else UNSET,
        amount_unit=body.amount_unit if "amount_unit" in body.model_fields_set else UNSET,
        concentration_value=body.concentration_value if "concentration_value" in body.model_fields_set else UNSET,
        concentration_unit=body.concentration_unit if "concentration_unit" in body.model_fields_set else UNSET,
        appearance=body.appearance if "appearance" in body.model_fields_set else UNSET,
        expiry_date=body.expiry_date if "expiry_date" in body.model_fields_set else UNSET,
        notebook_reference=body.notebook_reference if "notebook_reference" in body.model_fields_set else UNSET,
        storage_conditions_notes=body.storage_conditions_notes if "storage_conditions_notes" in body.model_fields_set else UNSET,
        custom_fields=body.custom_fields if "custom_fields" in body.model_fields_set else UNSET,
    )
    result = await uc(cmd, auth=auth)
    return BatchResponse.from_domain(result_to_response(result))
