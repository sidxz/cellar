"""CreateSample use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.inventory.enums import ContainerType
from cellar.domain.inventory.repository import BatchRepository, SampleRepository
from cellar.domain.inventory.sample import Sample
from cellar.domain.shared.enums import AmountUnit, ConcentrationUnit
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError
from cellar.domain.shared.value_objects import Amount, Barcode, Concentration


@dataclass(frozen=True, kw_only=True)
class CreateSampleCommand(Command):
    workspace_id: uuid.UUID
    batch_id: uuid.UUID
    barcode: str
    container_type: str
    amount_value: float
    amount_unit: str
    concentration_value: float | None = None
    concentration_unit: str | None = None
    solvent: str | None = None
    location_id: uuid.UUID | None = None
    low_stock_threshold: float | None = None


class CreateSample:
    def __init__(
        self,
        uow: UnitOfWork,
        batch_repo: BatchRepository,
        sample_repo: SampleRepository,
        molecule_repo: MoleculeRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._batch_repo = batch_repo
        self._sample_repo = sample_repo
        self._molecule_repo = molecule_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateSampleCommand, auth: AuthContext | None = None
    ) -> Result[Sample, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            batch = await self._batch_repo.find_by_id_in_workspace(
                input.workspace_id, input.batch_id
            )
            if batch is None:
                return Failure(NotFoundError("Batch", str(input.batch_id)))

            # Guard: parent molecule must not be tombstoned
            molecule = await self._molecule_repo.find_by_id_in_workspace(
                input.workspace_id, batch.molecule_id
            )
            if molecule is not None and molecule.is_tombstone:
                return Failure(
                    ConflictError("Cannot create sample — parent molecule has been merged")
                )

            concentration = None
            if input.concentration_value is not None and input.concentration_unit is not None:
                concentration = Concentration(
                    value=input.concentration_value,
                    unit=ConcentrationUnit(input.concentration_unit),
                )

            sample = Sample.create(
                workspace_id=input.workspace_id,
                batch_id=input.batch_id,
                barcode=Barcode(value=input.barcode),
                container_type=ContainerType(input.container_type),
                amount=Amount(value=input.amount_value, unit=AmountUnit(input.amount_unit)),
                concentration=concentration,
                solvent=input.solvent,
                location_id=input.location_id,
                low_stock_threshold=input.low_stock_threshold,
            )

            await self._sample_repo.save(sample)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(sample)
