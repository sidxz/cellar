"""UpdateBatch command — partial update of an existing batch."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from returns.pipeline import is_successful
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.application.workspace_config.custom_field_validator import CustomFieldValidator
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.shared.enums import AmountUnit, ConcentrationUnit
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.shared.value_objects import Amount, Concentration
from cellar.domain.workspace_config.enums import FieldTarget


@dataclass(frozen=True, kw_only=True)
class UpdateBatchCommand(Command):
    workspace_id: uuid.UUID
    batch_id: uuid.UUID
    salt_entry_id: uuid.UUID | object | None = UNSET
    salt_name: str | object | None = UNSET
    salt_smiles: str | object | None = UNSET
    salt_stoichiometry: int | object = UNSET
    formula_weight: float | object | None = UNSET
    purity: float | object | None = UNSET
    amount_value: float | None = None
    amount_unit: str | None = None
    concentration_value: float | object | None = UNSET
    concentration_unit: str | object | None = UNSET
    appearance: str | object | None = UNSET
    expiry_date: date | object | None = UNSET
    notebook_reference: str | object | None = UNSET
    storage_conditions_notes: str | object | None = UNSET
    custom_fields: dict[str, Any] | object | None = UNSET


class UpdateBatch:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: BatchRepository,
        dispatcher: EventDispatcherProtocol,
        custom_field_validator: CustomFieldValidator | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._custom_field_validator = custom_field_validator

    async def __call__(
        self, input: UpdateBatchCommand, auth: AuthContext | None = None
    ) -> Result[Batch, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            batch = await self._repo.find_by_id_in_workspace(input.workspace_id, input.batch_id)
            if batch is None:
                return Failure(NotFoundError("Batch", str(input.batch_id)))

            fields: dict[str, Any] = {}
            for attr in (
                "salt_entry_id",
                "salt_name",
                "salt_smiles",
                "salt_stoichiometry",
                "formula_weight",
            ):
                val = getattr(input, attr)
                if val is not UNSET:
                    fields[attr] = val
            if input.purity is not UNSET:
                fields["purity"] = input.purity
            if input.amount_value is not None and input.amount_unit is not None:
                fields["amount"] = Amount(
                    value=input.amount_value, unit=AmountUnit(input.amount_unit)
                )
            if input.concentration_value is not UNSET:
                if input.concentration_value is None:
                    fields["concentration"] = None
                elif (
                    input.concentration_unit is not UNSET and input.concentration_unit is not None
                ):
                    fields["concentration"] = Concentration(
                        value=input.concentration_value,
                        unit=ConcentrationUnit(input.concentration_unit),
                    )
            if input.appearance is not UNSET:
                fields["appearance"] = input.appearance
            if input.expiry_date is not UNSET:
                fields["expiry_date"] = input.expiry_date
            if input.notebook_reference is not UNSET:
                fields["notebook_reference"] = input.notebook_reference
            if input.storage_conditions_notes is not UNSET:
                fields["storage_conditions_notes"] = input.storage_conditions_notes
            if input.custom_fields is not UNSET:
                fields["custom_fields"] = input.custom_fields

            if (
                self._custom_field_validator
                and input.custom_fields is not UNSET
                and input.custom_fields is not None
            ):
                validation = await self._custom_field_validator.validate(
                    input.custom_fields, FieldTarget.BATCH, input.workspace_id
                )
                if not is_successful(validation):
                    return Failure(validation.failure())

            if fields:
                batch.update(**fields)
            await self._repo.save(batch)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(batch)
