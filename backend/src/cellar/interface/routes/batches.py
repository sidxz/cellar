"""Batch API routes."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.inventory.batch_identifiers import (
    AddBatchIdentifierCommand,
    ListBatchIdentifiersQuery,
    RemoveBatchIdentifierCommand,
)
from cellar.application.inventory.bulk_add_batch_identifiers import (
    BulkAddBatchIdentifiersCommand,
    BulkIdentifierRow,
)
from cellar.application.inventory.create_batch import CreateBatchCommand
from cellar.application.inventory.get_batch import (
    GetBatchQuery,
    ListBatchesByMoleculeQuery,
)
from cellar.application.inventory.update_batch import UpdateBatchCommand
from cellar.application.shared.sentinel import UNSET
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.batch_identifier import BatchIdentifier
from cellar.interface.dependencies import (
    AddBatchIdentifierDep,
    AuthDep,
    BulkAddBatchIdentifiersDep,
    CreateBatchDep,
    GetBatchDep,
    ListBatchesByMoleculeDep,
    ListBatchIdentifiersDep,
    RemoveBatchIdentifierDep,
    UpdateBatchDep,
)
from cellar.interface.error_handlers import result_to_response

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


class BatchIdentifierResponse(BaseModel):
    id: uuid.UUID
    identifier: str
    identifier_type: str
    source: str

    @classmethod
    def from_domain(cls, i: BatchIdentifier) -> BatchIdentifierResponse:
        return cls(
            id=i.id,
            identifier=i.identifier,
            identifier_type=i.identifier_type,
            source=i.source,
        )


class AddBatchIdentifierBody(BaseModel):
    identifier: str
    identifier_type: str
    source: str


class MirrorSummarySkippedResponse(BaseModel):
    batch_number: str
    mirror_string: str
    reason: str


class MirrorSummaryResponse(BaseModel):
    created: int
    skipped: list[MirrorSummarySkippedResponse]

    @classmethod
    def from_domain(cls, summary) -> MirrorSummaryResponse:
        return cls(
            created=summary.created,
            skipped=[
                MirrorSummarySkippedResponse(
                    batch_number=s.batch_number,
                    mirror_string=s.mirror_string,
                    reason=s.reason,
                )
                for s in summary.skipped
            ],
        )


class CreateBatchResponse(BaseModel):
    batch: BatchResponse
    mirror_summary: MirrorSummaryResponse


@router.post("/batches", response_model=CreateBatchResponse, status_code=201)
async def create_batch(
    auth: AuthDep,
    body: CreateBatchRequest,
    uc: CreateBatchDep,
) -> CreateBatchResponse:
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
    outcome = result_to_response(await uc(cmd, auth=auth))
    return CreateBatchResponse(
        batch=BatchResponse.from_domain(outcome.batch),
        mirror_summary=MirrorSummaryResponse.from_domain(outcome.mirror_summary),
    )


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

    cmd = UpdateBatchCommand(
        workspace_id=auth.workspace_id,
        batch_id=batch_id,
        salt_entry_id=body.salt_entry_id if "salt_entry_id" in body.model_fields_set else UNSET,
        salt_name=body.salt_name if "salt_name" in body.model_fields_set else UNSET,
        salt_smiles=body.salt_smiles if "salt_smiles" in body.model_fields_set else UNSET,
        salt_stoichiometry=body.salt_stoichiometry
        if "salt_stoichiometry" in body.model_fields_set
        else UNSET,
        formula_weight=body.formula_weight if "formula_weight" in body.model_fields_set else UNSET,
        purity=body.purity if "purity" in body.model_fields_set else UNSET,
        amount_value=body.amount_value if "amount_value" in body.model_fields_set else UNSET,
        amount_unit=body.amount_unit if "amount_unit" in body.model_fields_set else UNSET,
        concentration_value=body.concentration_value
        if "concentration_value" in body.model_fields_set
        else UNSET,
        concentration_unit=body.concentration_unit
        if "concentration_unit" in body.model_fields_set
        else UNSET,
        appearance=body.appearance if "appearance" in body.model_fields_set else UNSET,
        expiry_date=body.expiry_date if "expiry_date" in body.model_fields_set else UNSET,
        notebook_reference=body.notebook_reference
        if "notebook_reference" in body.model_fields_set
        else UNSET,
        storage_conditions_notes=body.storage_conditions_notes
        if "storage_conditions_notes" in body.model_fields_set
        else UNSET,
        custom_fields=body.custom_fields if "custom_fields" in body.model_fields_set else UNSET,
    )
    result = await uc(cmd, auth=auth)
    return BatchResponse.from_domain(result_to_response(result))


# ---------------------------------------------------------------------------
# Batch identifier sub-resource endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/batches/{batch_id}/identifiers",
    response_model=list[BatchIdentifierResponse],
)
async def list_batch_identifiers(
    batch_id: uuid.UUID,
    auth: AuthDep,
    use_case: ListBatchIdentifiersDep,
) -> list[BatchIdentifierResponse]:
    """List all external identifiers on a batch."""
    query = ListBatchIdentifiersQuery(workspace_id=auth.workspace_id, batch_id=batch_id)
    identifiers = result_to_response(await use_case(query, auth=auth))
    return [BatchIdentifierResponse.from_domain(i) for i in identifiers]


@router.post(
    "/batches/{batch_id}/identifiers",
    response_model=list[BatchIdentifierResponse],
    status_code=201,
)
async def add_batch_identifier(
    batch_id: uuid.UUID,
    body: AddBatchIdentifierBody,
    auth: AuthDep,
    use_case: AddBatchIdentifierDep,
) -> list[BatchIdentifierResponse]:
    """Add an external identifier to a batch. Returns the updated list."""
    command = AddBatchIdentifierCommand(
        workspace_id=auth.workspace_id,
        batch_id=batch_id,
        identifier=body.identifier,
        identifier_type=body.identifier_type,
        source=body.source,
        registered_by=auth.user_id,
    )
    batch = result_to_response(await use_case(command, auth=auth))
    return [BatchIdentifierResponse.from_domain(i) for i in batch.identifiers]


@router.delete(
    "/batches/{batch_id}/identifiers/{identifier_id}",
    status_code=204,
)
async def remove_batch_identifier(
    batch_id: uuid.UUID,
    identifier_id: uuid.UUID,
    auth: AuthDep,
    use_case: RemoveBatchIdentifierDep,
) -> None:
    """Remove an external identifier from a batch."""
    command = RemoveBatchIdentifierCommand(
        workspace_id=auth.workspace_id,
        batch_id=batch_id,
        identifier_id=identifier_id,
    )
    result_to_response(await use_case(command, auth=auth))


# ---------------------------------------------------------------------------
# Bulk batch-identifier import endpoints
# ---------------------------------------------------------------------------


class BulkIdentifierRowBody(BaseModel):
    row_index: int
    cellar_batch_number: str | None = None
    cellar_molecule_reg_number: str | None = None
    cellar_batch_sequence: int | None = None
    external_identifier: str
    identifier_type: str = "external_lot"
    source: str | None = None


class BulkAddBatchIdentifiersRequest(BaseModel):
    source_default: str
    rows: list[BulkIdentifierRowBody]


class RowOutcomeResponse(BaseModel):
    row_index: int
    status: str
    external_identifier: str
    batch_id: uuid.UUID | None = None
    resolved_batch_number: str | None = None
    created: bool = False
    conflict_batch_id: uuid.UUID | None = None
    conflict_batch_number: str | None = None
    message: str | None = None


class BulkAddBatchIdentifiersResponse(BaseModel):
    outcomes: list[RowOutcomeResponse]
    counts: dict[str, int]


@router.post(
    "/batches/identifiers/preview-bulk",
    response_model=BulkAddBatchIdentifiersResponse,
)
async def preview_bulk_add_batch_identifiers(
    body: BulkAddBatchIdentifiersRequest,
    auth: AuthDep,
    use_case: BulkAddBatchIdentifiersDep,
) -> BulkAddBatchIdentifiersResponse:
    """Dry-run a bulk batch-identifier import. Returns per-row outcomes without committing."""
    rows = [
        BulkIdentifierRow(
            row_index=r.row_index,
            cellar_batch_number=r.cellar_batch_number,
            cellar_molecule_reg_number=r.cellar_molecule_reg_number,
            cellar_batch_sequence=r.cellar_batch_sequence,
            external_identifier=r.external_identifier,
            identifier_type=r.identifier_type,
            source=r.source,
        )
        for r in body.rows
    ]
    command = BulkAddBatchIdentifiersCommand(
        workspace_id=auth.workspace_id,
        importing_user_id=auth.user_id,
        source_default=body.source_default,
        dry_run=True,
        rows=rows,
    )
    result = result_to_response(await use_case(command, auth=auth))
    return BulkAddBatchIdentifiersResponse(
        outcomes=[RowOutcomeResponse(**o.__dict__) for o in result.outcomes],
        counts=result.counts,
    )


@router.post(
    "/batches/identifiers/bulk",
    response_model=BulkAddBatchIdentifiersResponse,
    status_code=201,
)
async def bulk_add_batch_identifiers(
    body: BulkAddBatchIdentifiersRequest,
    auth: AuthDep,
    use_case: BulkAddBatchIdentifiersDep,
) -> BulkAddBatchIdentifiersResponse:
    """Commit a bulk batch-identifier import. Only `resolved` rows are persisted."""
    rows = [
        BulkIdentifierRow(
            row_index=r.row_index,
            cellar_batch_number=r.cellar_batch_number,
            cellar_molecule_reg_number=r.cellar_molecule_reg_number,
            cellar_batch_sequence=r.cellar_batch_sequence,
            external_identifier=r.external_identifier,
            identifier_type=r.identifier_type,
            source=r.source,
        )
        for r in body.rows
    ]
    command = BulkAddBatchIdentifiersCommand(
        workspace_id=auth.workspace_id,
        importing_user_id=auth.user_id,
        source_default=body.source_default,
        dry_run=False,
        rows=rows,
    )
    result = result_to_response(await use_case(command, auth=auth))
    return BulkAddBatchIdentifiersResponse(
        outcomes=[RowOutcomeResponse(**o.__dict__) for o in result.outcomes],
        counts=result.counts,
    )
