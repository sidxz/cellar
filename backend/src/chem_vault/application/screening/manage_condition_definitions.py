"""Use cases for managing condition definitions on DRAFT protocols."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.enums import ConditionDataType
from chem_vault.domain.screening_assay.protocol import ConditionDefinition, Protocol
from chem_vault.domain.screening_assay.repository import ProtocolRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class AddConditionDefinitionCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    name: str
    data_type: str
    unit: str | None = None
    pick_list_values: list[str] | None = None


@dataclass(frozen=True, kw_only=True)
class RemoveConditionDefinitionCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    definition_id: uuid.UUID


_UNSET = object()


@dataclass(frozen=True, kw_only=True)
class UpdateConditionDefinitionCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    definition_id: uuid.UUID
    name: str | None = None
    data_type: str | None = None
    unit: str | None | object = _UNSET
    pick_list_values: list[str] | None | object = _UNSET


# ---------------------------------------------------------------------------
# Use cases
# ---------------------------------------------------------------------------


class AddConditionDefinition:
    """Add a condition definition to a DRAFT protocol."""

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
        self, input: AddConditionDefinitionCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            definition = ConditionDefinition(
                protocol_id=protocol.id,
                name=input.name,
                data_type=ConditionDataType(input.data_type),
                unit=input.unit,
                pick_list_values=input.pick_list_values,
            )

            protocol.add_condition_definition(definition)
            await self._repo.save(protocol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(protocol)


class RemoveConditionDefinition:
    """Remove a condition definition from a DRAFT protocol."""

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
        self, input: RemoveConditionDefinitionCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            protocol.remove_condition_definition(input.definition_id)
            await self._repo.save(protocol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(protocol)


class UpdateConditionDefinition:
    """Edit a condition definition on a DRAFT protocol."""

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
        self, input: UpdateConditionDefinitionCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            kwargs: dict = {}
            if input.name is not None:
                kwargs["name"] = input.name
            if input.data_type is not None:
                kwargs["data_type"] = ConditionDataType(input.data_type)
            if input.unit is not _UNSET:
                kwargs["unit"] = input.unit
            if input.pick_list_values is not _UNSET:
                kwargs["pick_list_values"] = input.pick_list_values

            try:
                protocol.update_condition_definition(input.definition_id, **kwargs)
            except DomainError as exc:
                return Failure(exc)

            await self._repo.save(protocol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(protocol)
