"""Shipment API routes."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from lagom import Container
from pydantic import BaseModel

from chem_vault.application.inventory.preview_shipment_import import (
    ImportRow,
    PreviewShipmentImport,
)
from chem_vault.application.inventory.shipments import (
    AddShipmentItem,
    AddShipmentItemCommand,
    CreateShipment,
    CreateShipmentCommand,
    DeleteShipment,
    DeleteShipmentCommand,
    DeliverShipment,
    DeliverShipmentCommand,
    GetShipment,
    GetShipmentQuery,
    ListShipments,
    ListShipmentsQuery,
    MarkInTransitCommand,
    MarkShipmentInTransit,
    ReturnShipment,
    ReturnShipmentCommand,
    ShipmentItemInput,
    ShipShipment,
    ShipShipmentCommand,
    UpdateShipment,
    UpdateShipmentCommand,
)
from chem_vault.interface.dependencies import AuthDep, _get_use_case, get_container
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["shipments"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ShipmentItemResponse(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    amount_value: float
    amount_unit: str

    @classmethod
    def from_domain(cls, i) -> ShipmentItemResponse:  # type: ignore[no-untyped-def]
        return cls(
            id=i.id,
            sample_id=i.sample_id,
            amount_value=i.amount_shipped.value,
            amount_unit=i.amount_shipped.unit.value,
        )


class ShipmentResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    destination_org_id: uuid.UUID
    sender_id: uuid.UUID
    tracking_number: str | None = None
    carrier: str | None = None
    shipping_date: str | None = None
    expected_arrival_date: str | None = None
    received_date: str | None = None
    shipping_conditions: str | None = None
    status: str
    notes: str | None = None
    items: list[ShipmentItemResponse]

    @classmethod
    def from_domain(cls, s) -> ShipmentResponse:  # type: ignore[no-untyped-def]
        return cls(
            id=s.id,
            workspace_id=s.workspace_id,
            destination_org_id=s.destination_org_id,
            sender_id=s.sender_id,
            tracking_number=s.tracking_number,
            carrier=s.carrier,
            shipping_date=s.shipping_date.isoformat() if s.shipping_date else None,
            expected_arrival_date=s.expected_arrival_date.isoformat() if s.expected_arrival_date else None,
            received_date=s.received_date.isoformat() if s.received_date else None,
            shipping_conditions=s.shipping_conditions,
            status=s.status.value,
            notes=s.notes,
            items=[ShipmentItemResponse.from_domain(i) for i in s.items],
        )


class ShipmentSummaryResponse(BaseModel):
    """Lightweight for list endpoint — no items."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    destination_org_id: uuid.UUID
    tracking_number: str | None = None
    carrier: str | None = None
    status: str
    item_count: int

    @classmethod
    def from_domain(cls, s) -> ShipmentSummaryResponse:  # type: ignore[no-untyped-def]
        return cls(
            id=s.id,
            workspace_id=s.workspace_id,
            destination_org_id=s.destination_org_id,
            tracking_number=s.tracking_number,
            carrier=s.carrier,
            status=s.status.value,
            item_count=len(s.items),
        )


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class ShipmentItemRequest(BaseModel):
    sample_id: uuid.UUID
    amount_value: float
    amount_unit: str


class CreateShipmentRequest(BaseModel):
    destination_org_id: uuid.UUID
    carrier: str | None = None
    expected_arrival_date: date | None = None
    shipping_conditions: str | None = None
    notes: str | None = None
    items: list[ShipmentItemRequest]


class ShipRequest(BaseModel):
    tracking_number: str
    shipping_date: date | None = None


class DeliverRequest(BaseModel):
    received_date: date | None = None


class AddItemRequest(BaseModel):
    sample_id: uuid.UUID
    amount_value: float
    amount_unit: str


class UpdateShipmentRequest(BaseModel):
    carrier: str | None = None
    expected_arrival_date: date | None = None
    shipping_conditions: str | None = None
    notes: str | None = None


# --- Import preview models ---


class ImportRowRequest(BaseModel):
    compound: str
    batch: str
    sample: str
    amount: str


class PreviewImportRequest(BaseModel):
    rows: list[ImportRowRequest]


class FieldCorrectionResponse(BaseModel):
    field: str
    original: str
    corrected: str
    reason: str


class OriginalRowResponse(BaseModel):
    compound: str
    batch: str
    sample: str
    amount: str


class ResolvedRowResponse(BaseModel):
    row_number: int
    status: str  # "valid", "corrected", "error"
    original: OriginalRowResponse
    compound_id: str | None = None
    compound_display: str | None = None
    batch_id: str | None = None
    batch_display: str | None = None
    sample_id: str | None = None
    sample_display: str | None = None
    amount_value: float | None = None
    amount_unit: str | None = None
    corrections: list[FieldCorrectionResponse]
    errors: list[str]


class ImportPreviewResponse(BaseModel):
    rows: list[ResolvedRowResponse]
    total: int
    valid_count: int
    corrected_count: int
    error_count: int


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


CreateShipmentDep = Annotated[CreateShipment, Depends(_get_use_case(CreateShipment))]
GetShipmentDep = Annotated[GetShipment, Depends(_get_use_case(GetShipment))]
ListShipmentsDep = Annotated[ListShipments, Depends(_get_use_case(ListShipments))]
ShipShipmentDep = Annotated[ShipShipment, Depends(_get_use_case(ShipShipment))]
MarkShipmentInTransitDep = Annotated[MarkShipmentInTransit, Depends(_get_use_case(MarkShipmentInTransit))]
DeliverShipmentDep = Annotated[DeliverShipment, Depends(_get_use_case(DeliverShipment))]
ReturnShipmentDep = Annotated[ReturnShipment, Depends(_get_use_case(ReturnShipment))]
AddShipmentItemDep = Annotated[AddShipmentItem, Depends(_get_use_case(AddShipmentItem))]
UpdateShipmentDep = Annotated[UpdateShipment, Depends(_get_use_case(UpdateShipment))]
DeleteShipmentDep = Annotated[DeleteShipment, Depends(_get_use_case(DeleteShipment))]


def _get_preview_import(
    container: Annotated[Container, Depends(get_container)],
) -> PreviewShipmentImport:
    return container[PreviewShipmentImport]


PreviewImportDep = Annotated[PreviewShipmentImport, Depends(_get_preview_import)]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/shipments", response_model=ShipmentResponse, status_code=201)
async def create_shipment(
    body: CreateShipmentRequest, auth: AuthDep, uc: CreateShipmentDep
) -> ShipmentResponse:
    result = await uc(
        CreateShipmentCommand(
            workspace_id=auth.workspace_id,
            sender_id=auth.user_id,
            destination_org_id=body.destination_org_id,
            carrier=body.carrier,
            expected_arrival_date=body.expected_arrival_date,
            shipping_conditions=body.shipping_conditions,
            notes=body.notes,
            items=[
                ShipmentItemInput(
                    sample_id=item.sample_id,
                    amount_value=item.amount_value,
                    amount_unit=item.amount_unit,
                )
                for item in body.items
            ],
        ),
        auth=auth,
    )
    shipment = result_to_response(result)
    return ShipmentResponse.from_domain(shipment)


@router.get("/shipments", response_model=list[ShipmentSummaryResponse])
async def list_shipments(
    auth: AuthDep, uc: ListShipmentsDep, status: str | None = None
) -> list[ShipmentSummaryResponse]:
    result = await uc(
        ListShipmentsQuery(workspace_id=auth.workspace_id, status=status),
        auth=auth,
    )
    shipments = result_to_response(result)
    return [ShipmentSummaryResponse.from_domain(s) for s in shipments]


@router.post("/shipments/import/preview", response_model=ImportPreviewResponse)
async def preview_shipment_import(
    body: PreviewImportRequest, auth: AuthDep, uc: PreviewImportDep
) -> ImportPreviewResponse:
    """Validate and resolve CSV import rows before creating a shipment."""
    import_rows = [
        ImportRow(compound=r.compound, batch=r.batch, sample=r.sample, amount=r.amount)
        for r in body.rows
    ]
    result = await uc(auth.workspace_id, import_rows)
    return ImportPreviewResponse(
        rows=[
            ResolvedRowResponse(
                row_number=r.row_number,
                status=r.status,
                original=OriginalRowResponse(
                    compound=r.original.compound,
                    batch=r.original.batch,
                    sample=r.original.sample,
                    amount=r.original.amount,
                ),
                compound_id=r.compound_id,
                compound_display=r.compound_display,
                batch_id=r.batch_id,
                batch_display=r.batch_display,
                sample_id=r.sample_id,
                sample_display=r.sample_display,
                amount_value=r.amount_value,
                amount_unit=r.amount_unit,
                corrections=[
                    FieldCorrectionResponse(
                        field=c.field,
                        original=c.original,
                        corrected=c.corrected,
                        reason=c.reason,
                    )
                    for c in r.corrections
                ],
                errors=r.errors,
            )
            for r in result.rows
        ],
        total=result.total,
        valid_count=result.valid_count,
        corrected_count=result.corrected_count,
        error_count=result.error_count,
    )


@router.get("/shipments/{shipment_id}", response_model=ShipmentResponse)
async def get_shipment(
    shipment_id: uuid.UUID, auth: AuthDep, uc: GetShipmentDep
) -> ShipmentResponse:
    result = await uc(GetShipmentQuery(shipment_id=shipment_id), auth=auth)
    shipment = result_to_response(result)
    return ShipmentResponse.from_domain(shipment)


@router.patch("/shipments/{shipment_id}", response_model=ShipmentResponse)
async def update_shipment(
    shipment_id: uuid.UUID,
    body: UpdateShipmentRequest,
    auth: AuthDep,
    uc: UpdateShipmentDep,
) -> ShipmentResponse:
    from chem_vault.application.shared.sentinel import UNSET

    cmd = UpdateShipmentCommand(
        shipment_id=shipment_id,
        carrier=body.carrier if "carrier" in body.model_fields_set else UNSET,
        expected_arrival_date=body.expected_arrival_date if "expected_arrival_date" in body.model_fields_set else UNSET,
        shipping_conditions=body.shipping_conditions if "shipping_conditions" in body.model_fields_set else UNSET,
        notes=body.notes if "notes" in body.model_fields_set else UNSET,
    )
    result = await uc(cmd, auth=auth)
    shipment = result_to_response(result)
    return ShipmentResponse.from_domain(shipment)


@router.delete("/shipments/{shipment_id}", status_code=204)
async def delete_shipment(
    shipment_id: uuid.UUID, auth: AuthDep, uc: DeleteShipmentDep
) -> None:
    result = await uc(DeleteShipmentCommand(shipment_id=shipment_id), auth=auth)
    result_to_response(result)


@router.post("/shipments/{shipment_id}/ship", response_model=ShipmentResponse)
async def ship_shipment(
    shipment_id: uuid.UUID, body: ShipRequest, auth: AuthDep, uc: ShipShipmentDep
) -> ShipmentResponse:
    result = await uc(
        ShipShipmentCommand(
            shipment_id=shipment_id,
            tracking_number=body.tracking_number,
            shipping_date=body.shipping_date,
        ),
        auth=auth,
    )
    shipment = result_to_response(result)
    return ShipmentResponse.from_domain(shipment)


@router.post("/shipments/{shipment_id}/in-transit", response_model=ShipmentResponse)
async def mark_in_transit(
    shipment_id: uuid.UUID, auth: AuthDep, uc: MarkShipmentInTransitDep
) -> ShipmentResponse:
    result = await uc(MarkInTransitCommand(shipment_id=shipment_id), auth=auth)
    shipment = result_to_response(result)
    return ShipmentResponse.from_domain(shipment)


@router.post("/shipments/{shipment_id}/deliver", response_model=ShipmentResponse)
async def deliver_shipment(
    shipment_id: uuid.UUID, body: DeliverRequest, auth: AuthDep, uc: DeliverShipmentDep
) -> ShipmentResponse:
    result = await uc(
        DeliverShipmentCommand(
            shipment_id=shipment_id,
            received_date=body.received_date,
        ),
        auth=auth,
    )
    shipment = result_to_response(result)
    return ShipmentResponse.from_domain(shipment)


@router.post("/shipments/{shipment_id}/return", response_model=ShipmentResponse)
async def return_shipment(
    shipment_id: uuid.UUID, auth: AuthDep, uc: ReturnShipmentDep
) -> ShipmentResponse:
    result = await uc(ReturnShipmentCommand(shipment_id=shipment_id), auth=auth)
    shipment = result_to_response(result)
    return ShipmentResponse.from_domain(shipment)


@router.post("/shipments/{shipment_id}/items", response_model=ShipmentResponse, status_code=201)
async def add_shipment_item(
    shipment_id: uuid.UUID, body: AddItemRequest, auth: AuthDep, uc: AddShipmentItemDep
) -> ShipmentResponse:
    result = await uc(
        AddShipmentItemCommand(
            shipment_id=shipment_id,
            sample_id=body.sample_id,
            amount_value=body.amount_value,
            amount_unit=body.amount_unit,
        ),
        auth=auth,
    )
    shipment = result_to_response(result)
    return ShipmentResponse.from_domain(shipment)
