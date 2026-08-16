"""Kiosk endpoints — X-Kiosk-Token authed, excluded from Duar middleware.

The org directory is display-data only: a Duar outage must never block
a physical handout, so name resolution is best-effort.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Header
from pydantic import BaseModel

from cellar.application.inventory.kiosk import ConfirmScanCommand, ResolveScanQuery
from cellar.interface.dependencies import (
    ConfirmScanDep,
    OrgDirectoryDep,
    ResolveScanDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/kiosk", tags=["kiosk"])

KioskTokenHeader = Annotated[str | None, Header(alias="X-Kiosk-Token")]


class KioskScanBody(BaseModel):
    barcode: str


class KioskScanResponse(BaseModel):
    plate_id: uuid.UUID
    barcode: str
    plate_label: str
    loan_id: uuid.UUID
    item_id: uuid.UUID
    item_status: str
    action: str  # "checkout" | "return"
    borrower_org_id: uuid.UUID
    borrower_org_name: str | None
    due_date: date | None


class KioskConfirmBody(BaseModel):
    loan_id: uuid.UUID
    item_id: uuid.UUID


class KioskConfirmResponse(BaseModel):
    loan_id: uuid.UUID
    item_id: uuid.UUID
    new_status: str


@router.post("/scan", response_model=KioskScanResponse)
async def kiosk_scan(
    body: KioskScanBody,
    uc: ResolveScanDep,
    directory: OrgDirectoryDep,
    x_kiosk_token: KioskTokenHeader = None,
) -> KioskScanResponse:
    result = result_to_response(
        await uc(ResolveScanQuery(token=x_kiosk_token or "", barcode=body.barcode))
    )
    borrower_org_name: str | None = None
    try:
        orgs = await directory.list_orgs()
        borrower_org_name = next(
            (o.name for o in orgs if o.id == result.loan.borrower_org_id), None
        )
    except Exception:  # directory outage must not block the kiosk
        borrower_org_name = None
    return KioskScanResponse(
        plate_id=result.plate.id,
        barcode=result.plate.barcode.value,
        plate_label=result.plate.plate_label,
        loan_id=result.loan.id,
        item_id=result.item.id,
        item_status=result.item.status.value,
        action=result.action,
        borrower_org_id=result.loan.borrower_org_id,
        borrower_org_name=borrower_org_name,
        due_date=result.loan.due_date,
    )


@router.post("/confirm", response_model=KioskConfirmResponse)
async def kiosk_confirm(
    body: KioskConfirmBody,
    uc: ConfirmScanDep,
    x_kiosk_token: KioskTokenHeader = None,
) -> KioskConfirmResponse:
    result = result_to_response(
        await uc(
            ConfirmScanCommand(
                token=x_kiosk_token or "", loan_id=body.loan_id, item_id=body.item_id
            )
        )
    )
    return KioskConfirmResponse(
        loan_id=result.loan_id, item_id=result.item_id, new_status=result.new_status
    )
