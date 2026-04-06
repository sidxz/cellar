"""RegisteredPlate use cases — CRUD, status transitions, derive, well mapping."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.enums import PlateStatus, PlateType
from chem_vault.domain.inventory.registered_plate import RegisteredPlate
from chem_vault.domain.inventory.repository import BatchRepository, RegisteredPlateRepository
from chem_vault.domain.screening_assay.enums import PlateFormat
from chem_vault.domain.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError
from chem_vault.domain.shared.value_objects import Barcode

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

_SENTINEL = object()  # unique sentinel distinct from None and ...


@dataclass(frozen=True, kw_only=True)
class RegisterPlateCommand(Command):
    workspace_id: uuid.UUID
    barcode: str
    plate_label: str
    format: str
    plate_type: str
    registered_by: uuid.UUID
    well_map: dict | None = None
    storage_location_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None
    parent_plate_id: uuid.UUID | None = None
    notes: str | None = None


@dataclass(frozen=True, kw_only=True)
class UpdatePlateCommand(Command):
    workspace_id: uuid.UUID
    plate_id: uuid.UUID
    plate_label: str | None = None
    plate_type: str | None = None
    # Sentinel-style optional nullable fields — default to ... to signal "not provided"
    notes: str | None = ...  # type: ignore[assignment]
    project_id: uuid.UUID | None = ...  # type: ignore[assignment]
    storage_location_id: uuid.UUID | None = ...  # type: ignore[assignment]


@dataclass(frozen=True, kw_only=True)
class MapWellsCommand(Command):
    workspace_id: uuid.UUID
    plate_id: uuid.UUID
    well_map: dict


@dataclass(frozen=True, kw_only=True)
class ChangeStatusCommand(Command):
    workspace_id: uuid.UUID
    plate_id: uuid.UUID
    new_status: str


@dataclass(frozen=True, kw_only=True)
class DerivePlateCommand(Command):
    workspace_id: uuid.UUID
    parent_plate_id: uuid.UUID
    barcode: str
    plate_label: str
    registered_by: uuid.UUID
    plate_type: str = "daughter"
    storage_location_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    notes: str | None = None


@dataclass(frozen=True, kw_only=True)
class DeletePlateCommand(Command):
    workspace_id: uuid.UUID
    plate_id: uuid.UUID


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class GetPlateQuery(Query):
    workspace_id: uuid.UUID
    plate_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListPlatesQuery(Query):
    workspace_id: uuid.UUID
    barcode: str | None = None
    plate_label: str | None = None
    plate_type: str | None = None
    status: str | None = None
    format: str | None = None
    storage_location_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class ListChildrenQuery(Query):
    workspace_id: uuid.UUID
    parent_plate_id: uuid.UUID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _not_found(plate_id: uuid.UUID) -> Failure:
    return Failure(NotFoundError(f"RegisteredPlate {plate_id}"))


# ---------------------------------------------------------------------------
# Use Cases
# ---------------------------------------------------------------------------


class RegisterPlate:
    """Register a new physical plate in the inventory."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: RegisteredPlateRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RegisterPlateCommand, auth: AuthContext | None = None
    ) -> Result[RegisteredPlate, DomainError]:
        require_editor(auth)

        async with self._uow:
            # Barcode uniqueness check
            existing = await self._repo.find_by_barcode(input.workspace_id, input.barcode)
            if existing is not None:
                return Failure(ConflictError(f"Plate with barcode '{input.barcode}' already exists"))

            plate = RegisteredPlate.register(
                workspace_id=input.workspace_id,
                barcode=Barcode(value=input.barcode),
                plate_label=input.plate_label,
                format=PlateFormat(input.format),
                plate_type=PlateType(input.plate_type),
                registered_by=input.registered_by,
                storage_location_id=input.storage_location_id,
                parent_plate_id=input.parent_plate_id,
                notes=input.notes,
            )

            if input.well_map:
                plate.map_wells(input.well_map)

            await self._repo.save(plate)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(plate)


class GetPlate:
    """Retrieve a single registered plate by ID."""

    def __init__(self, uow: UnitOfWork, repo: RegisteredPlateRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetPlateQuery, auth: AuthContext | None = None
    ) -> Result[RegisteredPlate, DomainError]:
        async with self._uow:
            plate = await self._repo.find_by_id(input.plate_id)
            if plate is None:
                return _not_found(input.plate_id)
            if plate.workspace_id != input.workspace_id:
                return _not_found(input.plate_id)
            return Success(plate)


class ListPlates:
    """Search/list registered plates with optional filters."""

    def __init__(self, uow: UnitOfWork, repo: RegisteredPlateRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListPlatesQuery, auth: AuthContext | None = None
    ) -> Result[list[RegisteredPlate], DomainError]:
        async with self._uow:
            plates = await self._repo.search(
                input.workspace_id,
                barcode=input.barcode,
                plate_label=input.plate_label,
                plate_type=input.plate_type,
                status=input.status,
                format=input.format,
                storage_location_id=input.storage_location_id,
                project_id=input.project_id,
            )
            return Success(plates)


class UpdatePlate:
    """Update mutable fields on an existing plate."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: RegisteredPlateRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: UpdatePlateCommand, auth: AuthContext | None = None
    ) -> Result[RegisteredPlate, DomainError]:
        require_editor(auth)

        async with self._uow:
            plate = await self._repo.find_by_id(input.plate_id)
            if plate is None or plate.workspace_id != input.workspace_id:
                return _not_found(input.plate_id)

            # Build kwargs — only include fields that were explicitly provided
            kwargs: dict = {}
            if input.plate_label is not None:
                kwargs["plate_label"] = input.plate_label
            if input.plate_type is not None:
                kwargs["plate_type"] = PlateType(input.plate_type)
            # Sentinel-style: include if not the default ellipsis
            if input.notes is not ...:
                kwargs["notes"] = input.notes

            plate.update(**kwargs)

            await self._repo.save(plate)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(plate)


class MapWells:
    """Assign batch/concentration data to wells on a plate."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: RegisteredPlateRepository,
        batch_repo: BatchRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._batch_repo = batch_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: MapWellsCommand, auth: AuthContext | None = None
    ) -> Result[RegisteredPlate, DomainError]:
        require_editor(auth)

        async with self._uow:
            plate = await self._repo.find_by_id(input.plate_id)
            if plate is None or plate.workspace_id != input.workspace_id:
                return _not_found(input.plate_id)

            # Validate and resolve batch references (accept UUID or batch number)
            resolved_map = dict(input.well_map)
            seen_refs: dict[str, uuid.UUID] = {}
            for pos, entry in resolved_map.items():
                if not isinstance(entry, dict) or not entry.get("batch_id"):
                    continue
                raw = entry["batch_id"].strip()
                if raw in seen_refs:
                    entry["batch_id"] = str(seen_refs[raw])
                    continue
                # Try as UUID first
                try:
                    bid = uuid.UUID(raw)
                    batch = await self._batch_repo.find_by_id(bid)
                except ValueError:
                    # Not a UUID — resolve as batch number
                    batch = await self._batch_repo.find_by_batch_number(
                        input.workspace_id, raw
                    )
                if batch is None:
                    return Failure(ValidationError(f"Batch '{raw}' not found"))
                entry["batch_id"] = str(batch.id)
                seen_refs[raw] = batch.id

            plate.map_wells(resolved_map)

            await self._repo.save(plate)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(plate)


class ChangeStatus:
    """Transition a plate to a new lifecycle status."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: RegisteredPlateRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: ChangeStatusCommand, auth: AuthContext | None = None
    ) -> Result[RegisteredPlate, DomainError]:
        require_editor(auth)

        async with self._uow:
            plate = await self._repo.find_by_id(input.plate_id)
            if plate is None or plate.workspace_id != input.workspace_id:
                return _not_found(input.plate_id)

            plate.transition_status(PlateStatus(input.new_status))

            await self._repo.save(plate)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(plate)


class DerivePlate:
    """Derive a child plate from a parent, copying the well map."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: RegisteredPlateRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DerivePlateCommand, auth: AuthContext | None = None
    ) -> Result[RegisteredPlate, DomainError]:
        require_editor(auth)

        async with self._uow:
            parent = await self._repo.find_by_id(input.parent_plate_id)
            if parent is None or parent.workspace_id != input.workspace_id:
                return Failure(NotFoundError(f"RegisteredPlate {input.parent_plate_id}"))

            # Barcode uniqueness check for child
            existing = await self._repo.find_by_barcode(input.workspace_id, input.barcode)
            if existing is not None:
                return Failure(ConflictError(f"Plate with barcode '{input.barcode}' already exists"))

            child = parent.derive(
                barcode=Barcode(value=input.barcode),
                plate_label=input.plate_label,
                plate_type=PlateType(input.plate_type),
                registered_by=input.registered_by,
                storage_location_id=input.storage_location_id,
            )

            await self._repo.save(child)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(child)


class DeletePlate:
    """Delete a registered plate if it has no child plates."""

    def __init__(self, uow: UnitOfWork, repo: RegisteredPlateRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: DeletePlateCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)

        async with self._uow:
            plate = await self._repo.find_by_id(input.plate_id)
            if plate is None or plate.workspace_id != input.workspace_id:
                return _not_found(input.plate_id)

            children = await self._repo.find_children(input.plate_id)
            if children:
                return Failure(
                    ConflictError(
                        f"Cannot delete plate '{plate.barcode.value}': it has {len(children)} child plate(s)"
                    )
                )

            await self._repo.delete(input.workspace_id, input.plate_id)
            await self._uow.commit()
            return Success(None)


class ListChildren:
    """List child plates derived from a given parent plate."""

    def __init__(self, uow: UnitOfWork, repo: RegisteredPlateRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListChildrenQuery, auth: AuthContext | None = None
    ) -> Result[list[RegisteredPlate], DomainError]:
        async with self._uow:
            children = await self._repo.find_children(input.parent_plate_id)
            return Success(children)
