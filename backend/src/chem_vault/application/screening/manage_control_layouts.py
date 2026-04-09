"""Use cases for managing control layouts on DRAFT protocols."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.enums import PlateFormat
from chem_vault.domain.screening_assay.protocol import Protocol
from chem_vault.domain.screening_assay.repository import PlateTemplateRepository, ProtocolRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class SetControlLayoutCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    plate_format: str
    template_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RemoveControlLayoutCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    plate_format: str


# ---------------------------------------------------------------------------
# Use cases
# ---------------------------------------------------------------------------


class SetControlLayout:
    """Set a default control layout (plate template) for a plate format on a DRAFT protocol."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: ProtocolRepository,
        dispatcher: EventDispatcherProtocol,
        plate_template_repo: PlateTemplateRepository | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._plate_template_repo = plate_template_repo

    async def __call__(
        self, input: SetControlLayoutCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        async with self._uow:
            # Verify template belongs to this workspace
            if self._plate_template_repo is not None:
                template = await self._plate_template_repo.find_by_id_in_workspace(
                    input.workspace_id, input.template_id
                )
                if template is None:
                    return Failure(NotFoundError("PlateTemplate", str(input.template_id)))

            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            protocol.set_control_layout(
                PlateFormat(input.plate_format), input.template_id
            )
            await self._repo.save(protocol)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(protocol)


class RemoveControlLayout:
    """Remove a default control layout for a plate format from a DRAFT protocol."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: ProtocolRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RemoveControlLayoutCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            protocol.remove_control_layout(PlateFormat(input.plate_format))
            await self._repo.save(protocol)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(protocol)
