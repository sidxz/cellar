"""CreateProtocol use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.enums import (
    ConditionDataType,
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
    ReadoutNormalization,
)
from chem_vault.domain.screening_assay.protocol import (
    ConditionDefinition,
    Protocol,
    ReadoutDefinition,
)
from chem_vault.domain.screening_assay.repository import ProtocolRepository
from chem_vault.domain.shared.errors import AuthorizationError, DomainError


@dataclass(frozen=True, kw_only=True)
class CreateProtocolCommand(Command):
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    protocol_type: str
    target_id: uuid.UUID | None = None
    category: str | None = None
    readout_definitions: list[dict[str, Any]] = field(default_factory=list)
    condition_definitions: list[dict[str, Any]] = field(default_factory=list)


class CreateProtocol:
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
        self, input: CreateProtocolCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        if auth is None:
            return Failure(AuthorizationError("Authentication required to create a protocol"))
        require_editor(auth)

        # Use a temporary protocol_id for building owned entities;
        # Protocol.__init__ will rebind them to the actual aggregate ID.
        tmp_protocol_id = uuid.uuid4()

        readout_defs = [
            ReadoutDefinition(
                protocol_id=tmp_protocol_id,
                name=rd["name"],
                data_type=ReadoutDataType(rd["data_type"]),
                unit=rd.get("unit"),
                aggregation=ReadoutAggregation(rd["aggregation"]) if rd.get("aggregation") else ReadoutAggregation.NONE,
                precision=rd.get("precision"),
                normalization=ReadoutNormalization(rd["normalization"]) if rd.get("normalization") else ReadoutNormalization.NONE,
                is_calculated=rd.get("is_calculated", False),
                calculation_formula=rd.get("calculation_formula"),
                display_order=rd.get("display_order", 0),
            )
            for rd in input.readout_definitions
        ]

        condition_defs = [
            ConditionDefinition(
                protocol_id=tmp_protocol_id,
                name=cd["name"],
                data_type=ConditionDataType(cd["data_type"]),
                unit=cd.get("unit"),
                pick_list_values=cd.get("pick_list_values"),
            )
            for cd in input.condition_definitions
        ]

        async with self._uow:
            protocol = Protocol.create(
                workspace_id=input.workspace_id,
                name=input.name,
                description=input.description,
                protocol_type=ProtocolType(input.protocol_type),
                target_id=input.target_id,
                category=input.category,
                created_by=auth.user_id,
                readout_definitions=readout_defs,
                condition_definitions=condition_defs or None,
            )
            await self._repo.save(protocol)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(protocol)
