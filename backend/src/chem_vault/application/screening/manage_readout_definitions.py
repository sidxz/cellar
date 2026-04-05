"""Use cases for managing readout definitions on DRAFT protocols."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor, require_same_workspace
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.enums import (
    ReadoutAggregation,
    ReadoutDataType,
    ReadoutNormalization,
)
from chem_vault.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from chem_vault.domain.screening_assay.repository import ProtocolRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class AddReadoutDefinitionCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    name: str
    data_type: str
    unit: str | None = None
    aggregation: str = "none"
    precision: int | None = None
    normalization: str = "none"
    is_calculated: bool = False
    calculation_formula: str | None = None
    display_order: int = 0


@dataclass(frozen=True, kw_only=True)
class RemoveReadoutDefinitionCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    definition_id: uuid.UUID


# ---------------------------------------------------------------------------
# Use cases
# ---------------------------------------------------------------------------


class AddReadoutDefinition:
    """Add a readout definition to a DRAFT protocol."""

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
        self, input: AddReadoutDefinitionCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id(input.protocol_id)
            if protocol is None or protocol.workspace_id != input.workspace_id:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            require_same_workspace(auth, protocol.workspace_id)

            definition = ReadoutDefinition(
                protocol_id=protocol.id,
                name=input.name,
                data_type=ReadoutDataType(input.data_type),
                unit=input.unit,
                aggregation=ReadoutAggregation(input.aggregation),
                precision=input.precision,
                normalization=ReadoutNormalization(input.normalization),
                is_calculated=input.is_calculated,
                calculation_formula=input.calculation_formula,
                display_order=input.display_order,
            )

            protocol.add_readout_definition(definition)
            await self._repo.save(protocol)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(protocol)


class RemoveReadoutDefinition:
    """Remove a readout definition from a DRAFT protocol."""

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
        self, input: RemoveReadoutDefinitionCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id(input.protocol_id)
            if protocol is None or protocol.workspace_id != input.workspace_id:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            require_same_workspace(auth, protocol.workspace_id)

            protocol.remove_readout_definition(input.definition_id)
            await self._repo.save(protocol)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(protocol)
