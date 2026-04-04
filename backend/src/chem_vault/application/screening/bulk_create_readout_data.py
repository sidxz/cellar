"""BulkCreateReadoutData — batch import of readout measurements."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.data_lock_guard import DataLockGuard
from chem_vault.domain.screening_assay.readout_data import ReadoutData
from chem_vault.domain.screening_assay.repository import ReadoutDataRepository
from chem_vault.domain.shared.enums import Qualifier
from chem_vault.domain.shared.errors import DomainError, ValidationError
from chem_vault.domain.shared.value_objects import QualifiedValue


@dataclass(frozen=True, kw_only=True)
class ReadoutDataItem:
    run_id: uuid.UUID
    well_id: uuid.UUID | None = None
    molecule_id: uuid.UUID
    batch_id: uuid.UUID
    readout_definition_id: uuid.UUID
    value_numeric: float | None = None
    value_qualifier: str | None = None
    value_text: str | None = None
    is_outlier: bool = False


@dataclass(frozen=True, kw_only=True)
class BulkCreateReadoutDataCommand(Command):
    workspace_id: uuid.UUID
    items: list[ReadoutDataItem]


@dataclass
class BulkReadoutResult:
    total_count: int = 0
    success_count: int = 0
    error_count: int = 0
    errors: list[dict] = field(default_factory=list)


class BulkCreateReadoutData:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ReadoutDataRepository,
        guard: DataLockGuard,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._guard = guard
        self._dispatcher = dispatcher

    async def __call__(
        self, input: BulkCreateReadoutDataCommand, auth: AuthContext | None = None
    ) -> Result[BulkReadoutResult, DomainError]:
        require_editor(auth)

        if not input.items:
            return Failure(ValidationError("No items provided"))

        async with self._uow:
            # Check locks for all unique run IDs — reject entire batch if any locked
            run_ids = {item.run_id for item in input.items}
            for run_id in run_ids:
                lock_result = await self._guard.guard_write(run_id)
                if isinstance(lock_result, Failure):
                    return lock_result  # type: ignore[return-value]

            result = BulkReadoutResult(total_count=len(input.items))
            entities: list[ReadoutData] = []

            for idx, item in enumerate(input.items):
                try:
                    value: QualifiedValue | None = None
                    if item.value_numeric is not None:
                        qualifier = (
                            Qualifier(item.value_qualifier)
                            if item.value_qualifier
                            else Qualifier.EQUAL
                        )
                        value = QualifiedValue(
                            value=item.value_numeric, qualifier=qualifier
                        )

                    rd = ReadoutData(
                        workspace_id=input.workspace_id,
                        run_id=item.run_id,
                        well_id=item.well_id,
                        molecule_id=item.molecule_id,
                        batch_id=item.batch_id,
                        readout_definition_id=item.readout_definition_id,
                        value=value,
                        value_text=item.value_text,
                        is_outlier=item.is_outlier,
                    )
                    entities.append(rd)
                    result.success_count += 1
                except Exception as e:
                    result.error_count += 1
                    result.errors.append({"index": idx, "error": str(e)})

            if entities:
                await self._repo.save_bulk(entities)

            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(result)
