"""Kiosk scan/confirm use cases — device-token principal, no user session (spec §9, §10).

The X-Kiosk-Token header is the ONLY credential: `_authenticate_device`
replaces the require_* guard stack. A device sees and acts on exactly its
own org's plates; anything else is an indistinguishable 404.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.inventory.barcode_resolution import resolve_barcode
from cellar.application.inventory.kiosk_devices import hash_kiosk_token
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.enums import LoanItemStatus
from cellar.domain.inventory.kiosk_device import KioskDevice
from cellar.domain.inventory.plate_loan import LoanItem, PlateLoan
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.inventory.repository import (
    KioskDeviceRepository,
    PlateLoanRepository,
    RegisteredPlateRepository,
)
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    DomainError,
    NotFoundError,
)

KIOSK_ACTION_BY_STATUS: dict[LoanItemStatus, str] = {
    LoanItemStatus.APPROVED: "checkout",
    LoanItemStatus.RETURN_PENDING: "return",
}


@dataclass(frozen=True, kw_only=True)
class ResolveScanQuery(Query):
    token: str
    barcode: str


@dataclass(frozen=True)
class KioskScanResult:
    plate: RegisteredPlate
    loan: PlateLoan
    item: LoanItem
    action: str


@dataclass(frozen=True, kw_only=True)
class ConfirmScanCommand(Command):
    token: str
    loan_id: uuid.UUID
    item_id: uuid.UUID


@dataclass(frozen=True)
class KioskConfirmResult:
    loan_id: uuid.UUID
    item_id: uuid.UUID
    new_status: str


async def _authenticate_device(repo: KioskDeviceRepository, token: str) -> KioskDevice:
    if not token:
        raise AuthorizationError("Missing kiosk token")
    device = await repo.find_active_by_token_hash(hash_kiosk_token(token))
    if device is None:
        raise AuthorizationError("Invalid or revoked kiosk token")
    return device


class ResolveScan:
    """Barcode → pending loan item + which confirm action applies."""

    def __init__(
        self,
        uow: UnitOfWork,
        device_repo: KioskDeviceRepository,
        plate_repo: RegisteredPlateRepository,
        loan_repo: PlateLoanRepository,
    ) -> None:
        self._uow = uow
        self._device_repo = device_repo
        self._plate_repo = plate_repo
        self._loan_repo = loan_repo

    async def __call__(self, input: ResolveScanQuery) -> Result[KioskScanResult, DomainError]:
        async with self._uow:
            device = await _authenticate_device(self._device_repo, input.token)
            plate = await resolve_barcode(self._plate_repo, device.workspace_id, input.barcode)
            if plate is None or plate.owner_org_id != device.org_id:
                # Foreign-org plates are invisible to a device — same 404 as unknown.
                return Failure(NotFoundError(f"Plate '{input.barcode.strip()}'"))
            loans = await self._loan_repo.find_by_workspace(
                device.workspace_id, status="open", plate_id=plate.id
            )
            hit = next(
                (
                    (loan, item)
                    for loan in loans
                    for item in loan.items
                    if item.plate_id == plate.id and item.status in KIOSK_ACTION_BY_STATUS
                ),
                None,
            )
            if hit is None:
                return Failure(
                    ConflictError(f"No pending kiosk action for plate '{plate.barcode}'")
                )
            loan, item = hit
            await self._device_repo.touch_last_seen(device.id)
            await self._uow.commit()
        return Success(
            KioskScanResult(
                plate=plate, loan=loan, item=item, action=KIOSK_ACTION_BY_STATUS[item.status]
            )
        )


class ConfirmScan:
    """Drive APPROVED→CHECKED_OUT or RETURN_PENDING→RETURNED for one item."""

    def __init__(
        self,
        uow: UnitOfWork,
        device_repo: KioskDeviceRepository,
        loan_repo: PlateLoanRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._device_repo = device_repo
        self._loan_repo = loan_repo
        self._dispatcher = dispatcher

    async def __call__(self, input: ConfirmScanCommand) -> Result[KioskConfirmResult, DomainError]:
        async with self._uow:
            device = await _authenticate_device(self._device_repo, input.token)
            loan = await self._loan_repo.find_by_id_in_workspace(
                device.workspace_id, input.loan_id
            )
            if loan is None or loan.owner_org_id != device.org_id:
                return Failure(NotFoundError("Loan"))
            item = next((i for i in loan.items if i.id == input.item_id), None)
            if item is None:
                return Failure(NotFoundError("Loan item"))
            action = KIOSK_ACTION_BY_STATUS.get(item.status)
            if action is None:
                return Failure(
                    ConflictError(
                        f"Item is '{item.status.value}' — nothing for a kiosk to confirm"
                    )
                )
            if action == "checkout":
                loan.confirm_checkout([input.item_id])
            else:
                loan.confirm_return([input.item_id])
            await self._device_repo.touch_last_seen(device.id)
            await self._loan_repo.save(loan)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(
            KioskConfirmResult(loan_id=loan.id, item_id=item.id, new_status=item.status.value)
        )
