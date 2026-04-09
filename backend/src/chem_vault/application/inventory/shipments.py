"""Shipment use cases — create, retrieve, and lifecycle management."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.repository import SampleRepository, ShipmentRepository
from chem_vault.domain.inventory.shipment import Shipment, ShipmentItem
from chem_vault.domain.shared.enums import AmountUnit
from chem_vault.application.shared.sentinel import UNSET
from chem_vault.domain.inventory.enums import ShipmentStatus
from chem_vault.domain.shared.errors import DomainError, NotFoundError, ValidationError
from chem_vault.domain.shared.value_objects import Amount


# ---------------------------------------------------------------------------
# Data carriers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ShipmentItemInput:
    """Data carrier for a single shipment item in a create command."""

    sample_id: uuid.UUID
    amount_value: float
    amount_unit: str


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CreateShipmentCommand(Command):
    workspace_id: uuid.UUID
    sender_id: uuid.UUID
    destination_org_id: uuid.UUID
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
    sample_id: uuid.UUID
    amount_value: float
    amount_unit: str


@dataclass(frozen=True, kw_only=True)
class UpdateShipmentCommand(Command):
    workspace_id: uuid.UUID
    shipment_id: uuid.UUID
    carrier: str | None | object = UNSET
    expected_arrival_date: date | None | object = UNSET
    shipping_conditions: str | None | object = UNSET
    notes: str | None | object = UNSET


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
# Use cases
# ---------------------------------------------------------------------------


class CreateShipment:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ShipmentRepository,
        dispatcher: EventDispatcherProtocol,
        sample_repo: SampleRepository | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._sample_repo = sample_repo

    async def __call__(
        self, input: CreateShipmentCommand, auth: AuthContext | None = None
    ) -> Result[Shipment, DomainError]:
        require_editor(auth)

        async with self._uow:
            # Verify all samples belong to this workspace
            if self._sample_repo is not None:
                for item_input in input.items:
                    sample = await self._sample_repo.find_by_id_in_workspace(
                        input.workspace_id, item_input.sample_id
                    )
                    if sample is None:
                        return Failure(NotFoundError("Sample", str(item_input.sample_id)))

            # Build a placeholder shipment_id so items have a valid ref before creation
            placeholder_shipment_id = uuid.uuid4()
            items = [
                ShipmentItem(
                    shipment_id=placeholder_shipment_id,
                    sample_id=item_input.sample_id,
                    amount_shipped=Amount(
                        value=item_input.amount_value,
                        unit=AmountUnit(item_input.amount_unit),
                    ),
                )
                for item_input in input.items
            ]

            shipment = Shipment.create(
                workspace_id=input.workspace_id,
                destination_org_id=input.destination_org_id,
                sender_id=input.sender_id,
                carrier=input.carrier,
                expected_arrival_date=input.expected_arrival_date,
                shipping_conditions=input.shipping_conditions,
                notes=input.notes,
                items=items,
            )
            # Shipment.create() now fixes item.shipment_id internally

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
        async with self._uow:
            shipments = await self._repo.find_by_workspace(
                input.workspace_id, status=input.status
            )
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
        sample_repo: SampleRepository | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._sample_repo = sample_repo

    async def __call__(
        self, input: AddShipmentItemCommand, auth: AuthContext | None = None
    ) -> Result[Shipment, DomainError]:
        require_editor(auth)

        async with self._uow:
            shipment = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.shipment_id
            )
            if shipment is None:
                return Failure(NotFoundError("Shipment", str(input.shipment_id)))

            # Verify sample belongs to this workspace
            if self._sample_repo is not None:
                sample = await self._sample_repo.find_by_id_in_workspace(
                    input.workspace_id, input.sample_id
                )
                if sample is None:
                    return Failure(NotFoundError("Sample", str(input.sample_id)))

            item = ShipmentItem(
                shipment_id=shipment.id,
                sample_id=input.sample_id,
                amount_shipped=Amount(
                    value=input.amount_value,
                    unit=AmountUnit(input.amount_unit),
                ),
            )
            shipment.add_item(item)

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
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: UpdateShipmentCommand, auth: AuthContext | None = None
    ) -> Result[Shipment, DomainError]:
        require_editor(auth)
        async with self._uow:
            shipment = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.shipment_id
            )
            if shipment is None:
                return Failure(NotFoundError("Shipment", str(input.shipment_id)))

            if shipment.status != ShipmentStatus.PREPARING:
                return Failure(ValidationError("Can only update shipments in preparing status"))

            if input.carrier is not UNSET:
                shipment.carrier = input.carrier
            if input.expected_arrival_date is not UNSET:
                shipment.expected_arrival_date = input.expected_arrival_date
            if input.shipping_conditions is not UNSET:
                shipment.shipping_conditions = input.shipping_conditions
            if input.notes is not UNSET:
                shipment.notes = input.notes

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
