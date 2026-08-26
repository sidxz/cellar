"""Shipment use cases — create, retrieve, and lifecycle management."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_editor,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.inventory.plate_loans import _loan_visible
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.enums import ShipmentDirection, ShipmentItemType, ShipmentStatus
from cellar.domain.inventory.repository import (
    PlateLoanRepository,
    RegisteredPlateRepository,
    SampleRepository,
    ShipmentRepository,
)
from cellar.domain.inventory.shipment import Shipment, ShipmentItem
from cellar.domain.shared.enums import AmountUnit
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.shared.value_objects import Amount

# ---------------------------------------------------------------------------
# Data carriers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ShipmentItemInput:
    """A plate or a sample to put in the box. Samples need an amount; plates ship whole."""

    item_type: ShipmentItemType
    item_id: uuid.UUID
    amount_value: float | None = None
    amount_unit: str | None = None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CreateShipmentCommand(Command):
    workspace_id: uuid.UUID
    sender_id: uuid.UUID
    destination_org_id: uuid.UUID
    direction: ShipmentDirection = ShipmentDirection.OUTBOUND
    loan_id: uuid.UUID | None = None
    carrier: str | None = None
    expected_arrival_date: date | None = None
    shipping_conditions: str | None = None
    notes: str | None = None
    items: list[ShipmentItemInput] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class ShipShipmentCommand(Command):
    workspace_id: uuid.UUID
    shipment_id: uuid.UUID
    tracking_number: str
    shipping_date: date | None = None


@dataclass(frozen=True, kw_only=True)
class MarkInTransitCommand(Command):
    workspace_id: uuid.UUID
    shipment_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class DeliverShipmentCommand(Command):
    workspace_id: uuid.UUID
    shipment_id: uuid.UUID
    received_date: date | None = None


@dataclass(frozen=True, kw_only=True)
class ReturnShipmentCommand(Command):
    workspace_id: uuid.UUID
    shipment_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class AddShipmentItemCommand(Command):
    workspace_id: uuid.UUID
    shipment_id: uuid.UUID
    item: ShipmentItemInput


@dataclass(frozen=True, kw_only=True)
class UpdateShipmentCommand(Command):
    workspace_id: uuid.UUID
    shipment_id: uuid.UUID
    carrier: str | None | object = UNSET
    expected_arrival_date: date | None | object = UNSET
    shipping_conditions: str | None | object = UNSET
    notes: str | None | object = UNSET
    loan_id: uuid.UUID | None | object = UNSET


@dataclass(frozen=True, kw_only=True)
class DeleteShipmentCommand(Command):
    workspace_id: uuid.UUID
    shipment_id: uuid.UUID


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class GetShipmentQuery(Query):
    workspace_id: uuid.UUID
    shipment_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListShipmentsQuery(Query):
    workspace_id: uuid.UUID
    status: str | None = None


# ---------------------------------------------------------------------------
# Item resolution + loan validation (shared by Create / AddItem / Update)
# ---------------------------------------------------------------------------


async def _build_items(
    inputs: list[ShipmentItemInput],
    *,
    workspace_id: uuid.UUID,
    shipment_id: uuid.UUID,
    auth: AuthContext | None,
    plate_repo: RegisteredPlateRepository,
    sample_repo: SampleRepository,
    visibility: PlateVisibilityService,
) -> Result[list[ShipmentItem], DomainError]:
    """Resolve every input to a workspace-scoped, visible plate or sample.

    Missing and hidden plates report identically (no existence oracle). Plates on
    active loan to the caller's org count as visible — the borrower ships them back.
    """
    excluded: set[uuid.UUID] = set()
    borrowed: set[uuid.UUID] = set()
    if any(i.item_type is ShipmentItemType.PLATE for i in inputs):
        excluded = await visibility.excluded_org_ids(workspace_id, auth)
        borrowed = await visibility.borrowed_plate_ids(workspace_id, auth)
    items: list[ShipmentItem] = []
    for inp in inputs:
        if inp.item_type is ShipmentItemType.PLATE:
            plate = await plate_repo.find_by_id_in_workspace(workspace_id, inp.item_id)
            if plate is None or not visibility.can_view(plate, auth, excluded, borrowed):
                return Failure(NotFoundError("RegisteredPlate", str(inp.item_id)))
        elif await sample_repo.find_by_id_in_workspace(workspace_id, inp.item_id) is None:
            return Failure(NotFoundError("Sample", str(inp.item_id)))
        amount = (
            Amount(value=inp.amount_value, unit=AmountUnit(inp.amount_unit))
            if inp.amount_value is not None and inp.amount_unit is not None
            else None
        )
        try:
            items.append(
                ShipmentItem(
                    shipment_id=shipment_id,
                    item_type=inp.item_type,
                    item_id=inp.item_id,
                    amount_shipped=amount,
                )
            )
        except ValidationError as exc:
            return Failure(exc)
    return Success(items)


async def _check_loan(
    loan_id: uuid.UUID,
    *,
    workspace_id: uuid.UUID,
    auth: AuthContext | None,
    loan_repo: PlateLoanRepository,
    visibility: PlateVisibilityService,
) -> NotFoundError | None:
    """The loan must exist in the workspace and be visible to the caller (else 404)."""
    loan = await loan_repo.find_by_id_in_workspace(workspace_id, loan_id)
    if loan is None:
        return NotFoundError("PlateLoan", str(loan_id))
    excluded = await visibility.excluded_org_ids(workspace_id, auth)
    if not _loan_visible(loan, auth, excluded):
        return NotFoundError("PlateLoan", str(loan_id))
    return None


# ---------------------------------------------------------------------------
# Use cases
# ---------------------------------------------------------------------------


class CreateShipment:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ShipmentRepository,
        dispatcher: EventDispatcherProtocol,
        *,
        sample_repo: SampleRepository,
        plate_repo: RegisteredPlateRepository,
        visibility: PlateVisibilityService,
        loan_repo: PlateLoanRepository,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._sample_repo = sample_repo
        self._plate_repo = plate_repo
        self._visibility = visibility
        self._loan_repo = loan_repo

    async def __call__(
        self, input: CreateShipmentCommand, auth: AuthContext | None = None
    ) -> Result[Shipment, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            if input.loan_id is not None:
                err = await _check_loan(
                    input.loan_id,
                    workspace_id=input.workspace_id,
                    auth=auth,
                    loan_repo=self._loan_repo,
                    visibility=self._visibility,
                )
                if err is not None:
                    return Failure(err)

            # Placeholder shipment_id — Shipment.create() repoints items to its own id.
            built = await _build_items(
                input.items,
                workspace_id=input.workspace_id,
                shipment_id=uuid.uuid4(),
                auth=auth,
                plate_repo=self._plate_repo,
                sample_repo=self._sample_repo,
                visibility=self._visibility,
            )
            if isinstance(built, Failure):
                return built

            shipment = Shipment.create(
                workspace_id=input.workspace_id,
                destination_org_id=input.destination_org_id,
                sender_id=input.sender_id,
                direction=input.direction,
                loan_id=input.loan_id,
                carrier=input.carrier,
                expected_arrival_date=input.expected_arrival_date,
                shipping_conditions=input.shipping_conditions,
                notes=input.notes,
                items=built.unwrap(),
            )

            await self._repo.save(shipment)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(shipment)


class GetShipment:
    def __init__(self, uow: UnitOfWork, repo: ShipmentRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetShipmentQuery, auth: AuthContext | None = None
    ) -> Result[Shipment, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            shipment = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.shipment_id
            )
            if shipment is None:
                return Failure(NotFoundError("Shipment", str(input.shipment_id)))
            return Success(shipment)


class ListShipments:
    def __init__(self, uow: UnitOfWork, repo: ShipmentRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListShipmentsQuery, auth: AuthContext | None = None
    ) -> Result[list[Shipment], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            shipments = await self._repo.find_by_workspace(input.workspace_id, status=input.status)
            return Success(shipments)


class ShipShipment:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ShipmentRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: ShipShipmentCommand, auth: AuthContext | None = None
    ) -> Result[Shipment, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            shipment = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.shipment_id
            )
            if shipment is None:
                return Failure(NotFoundError("Shipment", str(input.shipment_id)))

            shipment.ship(input.tracking_number, shipping_date=input.shipping_date)

            await self._repo.save(shipment)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(shipment)


class MarkShipmentInTransit:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ShipmentRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: MarkInTransitCommand, auth: AuthContext | None = None
    ) -> Result[Shipment, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            shipment = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.shipment_id
            )
            if shipment is None:
                return Failure(NotFoundError("Shipment", str(input.shipment_id)))

            shipment.mark_in_transit()

            await self._repo.save(shipment)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(shipment)


class DeliverShipment:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ShipmentRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DeliverShipmentCommand, auth: AuthContext | None = None
    ) -> Result[Shipment, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            shipment = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.shipment_id
            )
            if shipment is None:
                return Failure(NotFoundError("Shipment", str(input.shipment_id)))

            shipment.deliver(received_date=input.received_date)

            await self._repo.save(shipment)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(shipment)


class ReturnShipment:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ShipmentRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: ReturnShipmentCommand, auth: AuthContext | None = None
    ) -> Result[Shipment, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            shipment = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.shipment_id
            )
            if shipment is None:
                return Failure(NotFoundError("Shipment", str(input.shipment_id)))

            shipment.return_shipment()

            await self._repo.save(shipment)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(shipment)


class AddShipmentItem:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ShipmentRepository,
        dispatcher: EventDispatcherProtocol,
        *,
        sample_repo: SampleRepository,
        plate_repo: RegisteredPlateRepository,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._sample_repo = sample_repo
        self._plate_repo = plate_repo
        self._visibility = visibility

    async def __call__(
        self, input: AddShipmentItemCommand, auth: AuthContext | None = None
    ) -> Result[Shipment, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            shipment = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.shipment_id
            )
            if shipment is None:
                return Failure(NotFoundError("Shipment", str(input.shipment_id)))

            built = await _build_items(
                [input.item],
                workspace_id=input.workspace_id,
                shipment_id=shipment.id,
                auth=auth,
                plate_repo=self._plate_repo,
                sample_repo=self._sample_repo,
                visibility=self._visibility,
            )
            if isinstance(built, Failure):
                return built
            shipment.add_item(built.unwrap()[0])

            await self._repo.save(shipment)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(shipment)


class UpdateShipment:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ShipmentRepository,
        dispatcher: EventDispatcherProtocol,
        *,
        loan_repo: PlateLoanRepository,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._loan_repo = loan_repo
        self._visibility = visibility

    async def __call__(
        self, input: UpdateShipmentCommand, auth: AuthContext | None = None
    ) -> Result[Shipment, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            shipment = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.shipment_id
            )
            if shipment is None:
                return Failure(NotFoundError("Shipment", str(input.shipment_id)))

            if input.loan_id is not UNSET and input.loan_id is not None:
                err = await _check_loan(
                    input.loan_id,  # type: ignore[arg-type]
                    workspace_id=input.workspace_id,
                    auth=auth,
                    loan_repo=self._loan_repo,
                    visibility=self._visibility,
                )
                if err is not None:
                    return Failure(err)

            try:
                shipment.update_details(
                    carrier=input.carrier if input.carrier is not UNSET else ...,
                    expected_arrival_date=input.expected_arrival_date
                    if input.expected_arrival_date is not UNSET
                    else ...,
                    shipping_conditions=input.shipping_conditions
                    if input.shipping_conditions is not UNSET
                    else ...,
                    notes=input.notes if input.notes is not UNSET else ...,
                    loan_id=input.loan_id if input.loan_id is not UNSET else ...,
                )
            except ValidationError as exc:
                return Failure(exc)

            await self._repo.save(shipment)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(shipment)


class DeleteShipment:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ShipmentRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DeleteShipmentCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            shipment = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.shipment_id
            )
            if shipment is None:
                return Failure(NotFoundError("Shipment", str(input.shipment_id)))

            if shipment.status != ShipmentStatus.PREPARING:
                return Failure(ValidationError("Can only delete shipments in preparing status"))

            await self._repo.delete(shipment.workspace_id, shipment.id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
