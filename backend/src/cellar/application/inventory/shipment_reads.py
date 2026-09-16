"""Shipment read side (S17 §5) — resolve barcodes to items, item/loan → shipments, item labels.

Reader Protocol + rows live here (single consumer); the SQLAlchemy implementation
is ``infrastructure.persistence.sqlalchemy.inventory.shipments_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_editor,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.inventory.barcode_resolution import resolve_barcode
from cellar.application.inventory.plate_loans import _loan_visible
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.enums import ShipmentItemType
from cellar.domain.inventory.repository import (
    PlateLoanRepository,
    RegisteredPlateRepository,
    SampleRepository,
)
from cellar.domain.inventory.shipment import Shipment
from cellar.domain.shared.errors import DomainError, NotFoundError

ItemKey = tuple[ShipmentItemType, uuid.UUID]


@dataclass(frozen=True)
class ShipmentLink:
    """One shipment as seen from a plate, a sample or a loan (newest first).

    ``amount_*`` is that item's shipped amount for item reads; None for loan reads
    and for plate items (plates ship whole).
    """

    shipment_id: uuid.UUID
    direction: str
    status: str
    destination_org_id: uuid.UUID
    tracking_number: str | None
    carrier: str | None
    shipping_date: date | None
    received_date: date | None
    amount_value: float | None
    amount_unit: str | None
    created_at: datetime


@dataclass(frozen=True)
class ItemLabel:
    """Display identity of a shipped item: plate → plate_label; sample → batch number."""

    barcode: str
    label: str


@runtime_checkable
class ShipmentsReader(Protocol):
    async def shipments_for_item(
        self, workspace_id: uuid.UUID, item_type: ShipmentItemType, item_id: uuid.UUID
    ) -> list[ShipmentLink]: ...

    async def shipments_for_loan(
        self, workspace_id: uuid.UUID, loan_id: uuid.UUID
    ) -> list[ShipmentLink]: ...

    async def item_labels(
        self, workspace_id: uuid.UUID, plate_ids: list[uuid.UUID], sample_ids: list[uuid.UUID]
    ) -> dict[ItemKey, ItemLabel]: ...


async def enrich_shipments(
    workspace_id: uuid.UUID, shipments: list[Shipment], reader: ShipmentsReader
) -> dict[ItemKey, ItemLabel]:
    """One plate fetch + one sample fetch for any number of shipments (no N+1)."""
    plate_ids = sorted(
        {i.item_id for s in shipments for i in s.items if i.item_type is ShipmentItemType.PLATE}
    )
    sample_ids = sorted(
        {i.item_id for s in shipments for i in s.items if i.item_type is ShipmentItemType.SAMPLE}
    )
    if not plate_ids and not sample_ids:
        return {}
    return await reader.item_labels(workspace_id, plate_ids, sample_ids)


# ---------------------------------------------------------------------------
# Resolve barcodes → items (the dialog's paste box)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedItem:
    barcode: str
    item_type: ShipmentItemType
    item_id: uuid.UUID
    label: str


@dataclass(frozen=True)
class UnresolvedItem:
    barcode: str
    error: str


@dataclass(frozen=True, kw_only=True)
class ResolveShipmentItemsQuery(Query):
    workspace_id: uuid.UUID
    barcodes: list[str]


class ResolveShipmentItems:
    """Each barcode → plate (resolver chain + visibility) else sample else unresolved.

    A hidden plate reports exactly like an unknown barcode — no existence oracle.
    Blank lines are dropped.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        plate_repo: RegisteredPlateRepository,
        sample_repo: SampleRepository,
        visibility: PlateVisibilityService,
        reader: ShipmentsReader,
    ) -> None:
        self._uow = uow
        self._plate_repo = plate_repo
        self._sample_repo = sample_repo
        self._visibility = visibility
        self._reader = reader

    async def __call__(
        self, input: ResolveShipmentItemsQuery, auth: AuthContext | None = None
    ) -> Result[list[ResolvedItem | UnresolvedItem], DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        ws = input.workspace_id
        async with self._uow:
            excluded = await self._visibility.excluded_org_ids(ws, auth)
            borrowed = await self._visibility.borrowed_plate_ids(ws, auth)
            hits: list[tuple[str, ItemKey | None]] = []
            for raw in input.barcodes:
                cleaned = raw.strip()
                if not cleaned:
                    continue
                plate = await resolve_barcode(self._plate_repo, ws, cleaned)
                if plate is not None and self._visibility.can_view(
                    plate, auth, excluded, borrowed
                ):
                    hits.append((raw, (ShipmentItemType.PLATE, plate.id)))
                    continue
                sample = await self._sample_repo.find_by_barcode(ws, cleaned)
                hits.append((raw, (ShipmentItemType.SAMPLE, sample.id) if sample else None))
            labels = await self._reader.item_labels(
                ws,
                [k[1] for _, k in hits if k and k[0] is ShipmentItemType.PLATE],
                [k[1] for _, k in hits if k and k[0] is ShipmentItemType.SAMPLE],
            )
        return Success(
            [
                ResolvedItem(raw, key[0], key[1], labels[key].label)
                if key
                else UnresolvedItem(raw, f"Unknown barcode '{raw.strip()}'")
                for raw, key in hits
            ]
        )


# ---------------------------------------------------------------------------
# Link reads — plate / sample / loan → shipments
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ListShipmentsForItemQuery(Query):
    workspace_id: uuid.UUID
    item_type: ShipmentItemType
    item_id: uuid.UUID


class ListShipmentsForItem:
    """Plate → plate visibility (hidden 404s like missing); sample → workspace only."""

    def __init__(
        self,
        uow: UnitOfWork,
        plate_repo: RegisteredPlateRepository,
        sample_repo: SampleRepository,
        visibility: PlateVisibilityService,
        reader: ShipmentsReader,
    ) -> None:
        self._uow = uow
        self._plate_repo = plate_repo
        self._sample_repo = sample_repo
        self._visibility = visibility
        self._reader = reader

    async def __call__(
        self, input: ListShipmentsForItemQuery, auth: AuthContext | None = None
    ) -> Result[list[ShipmentLink], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        ws = input.workspace_id
        async with self._uow:
            if input.item_type is ShipmentItemType.PLATE:
                plate = await self._plate_repo.find_by_id_in_workspace(ws, input.item_id)
                if plate is not None:
                    excluded = await self._visibility.excluded_org_ids(ws, auth)
                    borrowed = await self._visibility.borrowed_plate_ids(ws, auth)
                if plate is None or not self._visibility.can_view(plate, auth, excluded, borrowed):
                    return Failure(NotFoundError("RegisteredPlate", str(input.item_id)))
            elif await self._sample_repo.find_by_id_in_workspace(ws, input.item_id) is None:
                return Failure(NotFoundError("Sample", str(input.item_id)))
            return Success(
                await self._reader.shipments_for_item(ws, input.item_type, input.item_id)
            )


@dataclass(frozen=True, kw_only=True)
class ListShipmentsForLoanQuery(Query):
    workspace_id: uuid.UUID
    loan_id: uuid.UUID


class ListShipmentsForLoan:
    """Same loan visibility as ``GetLoan`` — a hidden loan 404s like a missing one."""

    def __init__(
        self,
        uow: UnitOfWork,
        loan_repo: PlateLoanRepository,
        visibility: PlateVisibilityService,
        reader: ShipmentsReader,
    ) -> None:
        self._uow = uow
        self._loan_repo = loan_repo
        self._visibility = visibility
        self._reader = reader

    async def __call__(
        self, input: ListShipmentsForLoanQuery, auth: AuthContext | None = None
    ) -> Result[list[ShipmentLink], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        ws = input.workspace_id
        async with self._uow:
            loan = await self._loan_repo.find_by_id_in_workspace(ws, input.loan_id)
            if loan is None:
                return Failure(NotFoundError("PlateLoan", str(input.loan_id)))
            excluded = await self._visibility.excluded_org_ids(ws, auth)
            if not _loan_visible(loan, auth, excluded):
                return Failure(NotFoundError("PlateLoan", str(input.loan_id)))
            return Success(await self._reader.shipments_for_loan(ws, input.loan_id))
