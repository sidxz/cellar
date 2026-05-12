"""Use cases for managing readout definitions on DRAFT protocols."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.screening._dose_response_config_serde import (
    deserialize_dose_response_config,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import (
    ReadoutAggregation,
    ReadoutDataType,
    ReadoutNormalization,
)
from cellar.domain.screening_assay.formula_evaluator import FormulaEvaluator
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class AddReadoutDefinitionCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    name: str
    description: str | None = None
    data_type: str
    unit: str | None = None
    aggregation: str = "none"
    precision: int | None = None
    # List of formula names. Empty list / None means raw / no normalization.
    normalizations: list[str] | None = None
    is_calculated: bool = False
    calculation_formula: str | None = None
    display_order: int = 0
    # Each item is `{label, color?}` dict or a bare string (legacy);
    # the entity's _normalize_pick_list_values lifts strings to dicts.
    pick_list_values: list[dict | str] | None = None
    dose_response_config: dict | None = None


@dataclass(frozen=True, kw_only=True)
class RemoveReadoutDefinitionCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    definition_id: uuid.UUID


# Sentinel to distinguish "not provided" from "set to None" in partial updates.
_UNSET = object()


@dataclass(frozen=True, kw_only=True)
class UpdateReadoutDefinitionCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    definition_id: uuid.UUID
    name: str | None = None
    description: str | None | object = _UNSET
    data_type: str | None = None
    unit: str | None | object = _UNSET
    aggregation: str | None = None
    precision: int | None | object = _UNSET
    # List of formula names. ``_UNSET`` = leave unchanged; empty list =
    # clear all normalizations.
    normalizations: list[str] | None | object = _UNSET
    is_calculated: bool | None = None
    calculation_formula: str | None | object = _UNSET
    display_order: int | None = None
    pick_list_values: list[dict | str] | None | object = _UNSET
    dose_response_config: dict | None | object = _UNSET


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
        formula_evaluator: FormulaEvaluator | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._formula_evaluator = formula_evaluator

    async def __call__(
        self, input: AddReadoutDefinitionCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            # Validate formula if this is a calculated readout
            if input.is_calculated and input.calculation_formula and self._formula_evaluator:
                available_names = [rd.name for rd in protocol.readout_definitions]
                try:
                    self._formula_evaluator.validate(input.calculation_formula, available_names)
                except DomainError as exc:
                    return Failure(exc)

            # Build dose_response_config VO from dict if provided
            dr_config = None
            if input.data_type == "dose_response" and input.dose_response_config:
                dr_config = deserialize_dose_response_config(input.dose_response_config)

            resolved_normalizations = (
                frozenset(ReadoutNormalization(v) for v in input.normalizations)
                if input.normalizations
                else frozenset()
            )

            definition = ReadoutDefinition(
                protocol_id=protocol.id,
                name=input.name,
                description=input.description,
                data_type=ReadoutDataType(input.data_type),
                unit=input.unit,
                aggregation=ReadoutAggregation(input.aggregation),
                precision=input.precision,
                normalizations=resolved_normalizations,
                is_calculated=input.is_calculated,
                calculation_formula=input.calculation_formula,
                display_order=input.display_order,
                pick_list_values=input.pick_list_values,
                dose_response_config=dr_config,
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
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            protocol.remove_readout_definition(input.definition_id)
            await self._repo.save(protocol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(protocol)


class UpdateReadoutDefinition:
    """Edit a readout definition on a DRAFT protocol."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: ProtocolRepository,
        dispatcher: EventDispatcherProtocol,
        formula_evaluator: FormulaEvaluator | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._formula_evaluator = formula_evaluator

    async def __call__(
        self, input: UpdateReadoutDefinitionCommand, auth: AuthContext | None = None
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
            if input.description is not _UNSET:
                kwargs["description"] = input.description
            if input.data_type is not None:
                kwargs["data_type"] = ReadoutDataType(input.data_type)
            if input.unit is not _UNSET:
                kwargs["unit"] = input.unit
            if input.aggregation is not None:
                kwargs["aggregation"] = ReadoutAggregation(input.aggregation)
            if input.precision is not _UNSET:
                kwargs["precision"] = input.precision
            if input.normalizations is not _UNSET:
                norm_list = input.normalizations  # type: ignore[assignment]
                kwargs["normalizations"] = (
                    frozenset(ReadoutNormalization(v) for v in norm_list)
                    if norm_list is not None
                    else frozenset()
                )
            if input.is_calculated is not None:
                kwargs["is_calculated"] = input.is_calculated
            if input.calculation_formula is not _UNSET:
                kwargs["calculation_formula"] = input.calculation_formula
            if input.display_order is not None:
                kwargs["display_order"] = input.display_order
            if input.pick_list_values is not _UNSET:
                kwargs["pick_list_values"] = input.pick_list_values
            if input.dose_response_config is not _UNSET:
                cfg = input.dose_response_config
                if cfg is None:
                    kwargs["dose_response_config"] = None
                else:
                    kwargs["dose_response_config"] = deserialize_dose_response_config(cfg)  # type: ignore[arg-type]

            # Optional formula validation
            formula = kwargs.get("calculation_formula")
            is_calc = kwargs.get("is_calculated")
            if is_calc and formula and self._formula_evaluator:
                available_names = [
                    rd.name for rd in protocol.readout_definitions if rd.id != input.definition_id
                ]
                try:
                    self._formula_evaluator.validate(formula, available_names)
                except DomainError as exc:
                    return Failure(exc)

            try:
                protocol.update_readout_definition(input.definition_id, **kwargs)
            except DomainError as exc:
                return Failure(exc)

            await self._repo.save(protocol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(protocol)
