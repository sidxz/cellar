"""CreateProtocol use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.screening._dose_response_config_serde import (
    deserialize_dose_response_config,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import (
    ConditionDataType,
    PosControlSignal,
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
    ReadoutNormalization,
)
from cellar.domain.screening_assay.protocol import (
    RESERVED_READOUT_NAMES,
    ConditionDefinition,
    Protocol,
    ReadoutDefinition,
    is_reserved_readout_name,
)
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.shared.enums import ConcentrationUnit
from cellar.domain.shared.errors import AuthorizationError, DomainError, ValidationError


@dataclass(frozen=True, kw_only=True)
class CreateProtocolCommand(Command):
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    protocol_type: str
    target_id: uuid.UUID | None = None
    category: str | None = None
    dose_unit: str = "uM"
    pos_control_signal: str = "high"
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
        require_editor(auth)
        if auth is None:
            return Failure(AuthorizationError("Authentication required"))

        # Reserved-name guard runs at the use-case boundary (the entity
        # constructor stays permissive so legacy DB rows hydrate cleanly).
        for rd in input.readout_definitions:
            rd_name = rd.get("name", "")
            if is_reserved_readout_name(rd_name):
                return Failure(
                    ValidationError(
                        f"ReadoutDefinition name '{rd_name}' collides with a "
                        f"reserved well-metadata name. Reserved: "
                        f"{sorted(RESERVED_READOUT_NAMES)}."
                    )
                )

        # Use a temporary protocol_id for building owned entities;
        # Protocol.__init__ will rebind them to the actual aggregate ID.
        tmp_protocol_id = uuid.uuid4()

        readout_defs = []
        for rd in input.readout_definitions:
            dr_config = None
            if rd.get("data_type") == "dose_response" and rd.get("dose_response_config"):
                dr_config = deserialize_dose_response_config(rd["dose_response_config"])

            # Resolve normalizations from new (preferred) or legacy
            # (single-value) request shape. Legacy NONE / "none" / missing →
            # empty set.
            raw_norms = rd.get("normalizations")
            if raw_norms is not None:
                resolved_norms: frozenset[ReadoutNormalization] = frozenset(
                    ReadoutNormalization(n) for n in raw_norms
                )
            elif rd.get("normalization"):
                legacy = ReadoutNormalization(rd["normalization"])
                resolved_norms = (
                    frozenset({legacy}) if legacy != ReadoutNormalization.NONE else frozenset()
                )
            else:
                resolved_norms = frozenset()

            readout_defs.append(
                ReadoutDefinition(
                    protocol_id=tmp_protocol_id,
                    name=rd["name"],
                    description=rd.get("description"),
                    data_type=ReadoutDataType(rd["data_type"]),
                    unit=rd.get("unit"),
                    aggregation=ReadoutAggregation(rd["aggregation"])
                    if rd.get("aggregation")
                    else ReadoutAggregation.NONE,
                    precision=rd.get("precision"),
                    normalizations=resolved_norms,
                    is_calculated=rd.get("is_calculated", False),
                    calculation_formula=rd.get("calculation_formula"),
                    display_order=rd.get("display_order", 0),
                    pick_list_values=rd.get("pick_list_values"),
                    dose_response_config=dr_config,
                )
            )

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
                dose_unit=ConcentrationUnit(input.dose_unit),
                pos_control_signal=PosControlSignal(input.pos_control_signal),
                readout_definitions=readout_defs,
                condition_definitions=condition_defs or None,
            )
            await self._repo.save(protocol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(protocol)
