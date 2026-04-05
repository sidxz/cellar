"""CreateBatch use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor, require_same_workspace
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.repository import MoleculeRepository
from chem_vault.domain.inventory.batch import Batch
from chem_vault.domain.inventory.enums import BatchSource
from chem_vault.domain.inventory.repository import BatchRepository
from chem_vault.domain.shared.enums import AmountUnit, ConcentrationUnit
from chem_vault.domain.shared.errors import ConflictError, DomainError, NotFoundError
from chem_vault.domain.shared.value_objects import Amount, Concentration


@dataclass(frozen=True, kw_only=True)
class CreateBatchCommand(Command):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    source: str
    chemist: uuid.UUID
    amount_value: float
    amount_unit: str
    salt_form: str | None = None
    purity: float | None = None
    concentration_value: float | None = None
    concentration_unit: str | None = None
    supplier_org_id: uuid.UUID | None = None
    vendor_catalog_number: str | None = None
    vendor_lot_number: str | None = None
    synthesis_date: date | None = None
    expiry_date: date | None = None
    notebook_reference: str | None = None
    appearance: str | None = None
    custom_fields: dict | None = None


class CreateBatch:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: BatchRepository,
        molecule_repo: MoleculeRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._molecule_repo = molecule_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateBatchCommand, auth: AuthContext | None = None
    ) -> Result[Batch, DomainError]:
        require_editor(auth)

        async with self._uow:
            # Validate molecule exists, belongs to workspace, and is not tombstoned
            molecule = await self._molecule_repo.find_by_id(input.molecule_id)
            if molecule is None:
                return Failure(NotFoundError("Molecule"))
            require_same_workspace(auth, molecule.workspace_id)
            if molecule.is_tombstone:
                return Failure(
                    ConflictError("Cannot create batch for a merged molecule")
                )

            batch_number = await self._repo.next_batch_number(
                input.workspace_id, input.molecule_id
            )
            concentration = None
            if input.concentration_value is not None and input.concentration_unit is not None:
                concentration = Concentration(
                    value=input.concentration_value,
                    unit=ConcentrationUnit(input.concentration_unit),
                )

            batch = Batch.create(
                workspace_id=input.workspace_id,
                molecule_id=input.molecule_id,
                batch_number=batch_number,
                amount=Amount(value=input.amount_value, unit=AmountUnit(input.amount_unit)),
                source=BatchSource(input.source),
                chemist=input.chemist,
                salt_form=input.salt_form,
                purity=input.purity,
                concentration=concentration,
                supplier_org_id=input.supplier_org_id,
                vendor_catalog_number=input.vendor_catalog_number,
                vendor_lot_number=input.vendor_lot_number,
                synthesis_date=input.synthesis_date,
                expiry_date=input.expiry_date,
                notebook_reference=input.notebook_reference,
                appearance=input.appearance,
                custom_fields=input.custom_fields,
            )

            await self._repo.save(batch)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(batch)
