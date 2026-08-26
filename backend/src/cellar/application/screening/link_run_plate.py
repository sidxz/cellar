"""Link / unlink a run plate to the physical inventory plate it was run on (S15 spec §5.2).

The link is optional by design; ``barcode`` accepts a barcode or a plate label
(``resolve_plate_reference``). A plate the caller may not view — or one that
doesn't exist — reports identically as not found. Locked runs raise
``ConflictError`` via ``Run._guard_not_locked`` like every other run mutation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_authenticated,
    require_editor,
    require_same_workspace,
)
from cellar.application.inventory.plate_reference import resolve_plate_reference
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.repository import RegisteredPlateRepository
from cellar.domain.screening_assay.repository import RunRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class LinkRunPlateCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    plate_id: uuid.UUID
    barcode: str


@dataclass(frozen=True, kw_only=True)
class UnlinkRunPlateCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    plate_id: uuid.UUID


@dataclass(frozen=True)
class RunPlateLink:
    plate_id: uuid.UUID
    registered_plate_id: uuid.UUID | None
    barcode: str | None
    plate_label: str | None


class LinkRunPlate:
    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        plate_repo: RegisteredPlateRepository,
        visibility: PlateVisibilityService,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._plate_repo = plate_repo
        self._visibility = visibility
        self._dispatcher = dispatcher

    async def __call__(
        self, input: LinkRunPlateCommand, auth: AuthContext | None = None
    ) -> Result[RunPlateLink, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            run = await self._run_repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))

            plate = await resolve_plate_reference(
                self._plate_repo, input.workspace_id, input.barcode
            )
            if plate is not None:
                excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
                borrowed = await self._visibility.borrowed_plate_ids(input.workspace_id, auth)
                if not self._visibility.can_view(plate, auth, excluded, borrowed):
                    plate = None
            if plate is None:
                return Failure(NotFoundError("RegisteredPlate", input.barcode))

            try:
                run.link_plate(input.plate_id, plate.id)
            except NotFoundError as exc:
                return Failure(exc)
            await self._run_repo.save(run)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(
            RunPlateLink(
                plate_id=input.plate_id,
                registered_plate_id=plate.id,
                barcode=plate.barcode.value,
                plate_label=plate.plate_label,
            )
        )


class UnlinkRunPlate:
    def __init__(
        self, uow: UnitOfWork, run_repo: RunRepository, dispatcher: EventDispatcherProtocol
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: UnlinkRunPlateCommand, auth: AuthContext | None = None
    ) -> Result[RunPlateLink, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            run = await self._run_repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            try:
                run.link_plate(input.plate_id, None)
            except NotFoundError as exc:
                return Failure(exc)
            await self._run_repo.save(run)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(
            RunPlateLink(
                plate_id=input.plate_id, registered_plate_id=None, barcode=None, plate_label=None
            )
        )
