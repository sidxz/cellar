"""UpdateBatch command — partial update of an existing batch."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.sentinel import UNSET
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.batch import Batch
from chem_vault.domain.inventory.repository import BatchRepository
from chem_vault.domain.shared.enums import AmountUnit, ConcentrationUnit
from chem_vault.domain.shared.errors import DomainError, NotFoundError
from chem_vault.domain.shared.value_objects import Amount, Concentration, StorageCondition


@dataclass(frozen=True, kw_only=True)
class UpdateBatchCommand(Command):
    workspace_id: uuid.UUID
    batch_id: uuid.UUID
    salt_entry_id: uuid.UUID | None | object = UNSET
    salt_name: str | None | object = UNSET
    salt_smiles: str | None | object = UNSET
    salt_stoichiometry: int | object = UNSET
    formula_weight: float | None | object = UNSET
    purity: float | None | object = UNSET
    amount_value: float | None = None
    amount_unit: str | None = None
    concentration_value: float | None | object = UNSET
    concentration_unit: str | None | object = UNSET
    appearance: str | None | object = UNSET
    expiry_date: date | None | object = UNSET
    notebook_reference: str | None | object = UNSET
    storage_conditions_notes: str | None | object = UNSET
    custom_fields: dict | None | object = UNSET


class UpdateBatch:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: BatchRepository,
        dispatcher: EventDispatcherProtocol,
        custom_field_validator=None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._custom_field_validator = custom_field_validator

    async def __call__(
        self, input: UpdateBatchCommand, auth: AuthContext | None = None
    ) -> Result[Batch, DomainError]:
        require_editor(auth)

        async with self._uow:
            batch = await self._repo.find_by_id(input.batch_id)
            if batch is None or batch.workspace_id != input.workspace_id:
                return Failure(NotFoundError("Batch", str(input.batch_id)))

            fields: dict[str, object] = {}
            for attr in ("salt_entry_id", "salt_name", "salt_smiles", "salt_stoichiometry", "formula_weight"):
                val = getattr(input, attr)
                if val is not UNSET:
                    fields[attr] = val
            if input.purity is not UNSET:
                fields["purity"] = input.purity
            if input.amount_value is not None and input.amount_unit is not None:
                fields["amount"] = Amount(value=input.amount_value, unit=AmountUnit(input.amount_unit))
            if input.concentration_value is not UNSET:
                if input.concentration_value is None:
                    fields["concentration"] = None
                elif input.concentration_unit is not UNSET and input.concentration_unit is not None:
                    fields["concentration"] = Concentration(
                        value=input.concentration_value, unit=ConcentrationUnit(input.concentration_unit)
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

            if self._custom_field_validator and input.custom_fields is not UNSET and input.custom_fields is not None:
                from chem_vault.domain.workspace_config.enums import FieldTarget
                from returns.pipeline import is_successful
                validation = await self._custom_field_validator.validate(
                    input.custom_fields, FieldTarget.BATCH, input.workspace_id
                )
                if not is_successful(validation):
                    return validation  # type: ignore[return-value]

            if fields:
                batch.update(**fields)
            await self._repo.save(batch)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(batch)
