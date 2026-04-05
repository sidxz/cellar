"""BulkCreateReadoutData — batch import of readout measurements."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.repository import MoleculeRepository
from chem_vault.domain.inventory.repository import BatchRepository
from chem_vault.domain.screening_assay.data_lock_guard import DataLockGuard
from chem_vault.domain.screening_assay.readout_data import ReadoutData
from chem_vault.domain.screening_assay.repository import (
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from chem_vault.domain.shared.enums import Qualifier
from chem_vault.domain.shared.errors import DomainError, ValidationError
from chem_vault.domain.shared.value_objects import QualifiedValue


@dataclass(frozen=True, kw_only=True)
class ReadoutDataItem:
    run_id: uuid.UUID
    well_id: uuid.UUID | None = None
    molecule_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    readout_definition_id: uuid.UUID | None = None
    # Human-readable alternatives for ID resolution
    registration_number: str | None = None
    batch_number: str | None = None
    readout_definition_name: str | None = None
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
        molecule_repo: MoleculeRepository | None = None,
        batch_repo: BatchRepository | None = None,
        run_repo: RunRepository | None = None,
        protocol_repo: ProtocolRepository | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._guard = guard
        self._dispatcher = dispatcher
        self._molecule_repo = molecule_repo
        self._batch_repo = batch_repo
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo

    async def _resolve_molecule_id(
        self,
        workspace_id: uuid.UUID,
        item: ReadoutDataItem,
        idx: int,
    ) -> Result[uuid.UUID, DomainError]:
        """Resolve molecule_id from the item, looking up by registration_number if needed."""
        if item.molecule_id is not None:
            return Success(item.molecule_id)
        if item.registration_number is not None:
            if self._molecule_repo is None:
                return Failure(ValidationError(
                    f"Item {idx}: registration_number provided but molecule resolver not available"
                ))
            mol = await self._molecule_repo.find_by_registration_number(
                workspace_id, item.registration_number
            )
            if mol is None:
                return Failure(ValidationError(
                    f"Item {idx}: molecule with registration_number "
                    f"'{item.registration_number}' not found"
                ))
            return Success(mol.id)
        return Failure(ValidationError(
            f"Item {idx}: either molecule_id or registration_number is required"
        ))

    async def _resolve_batch_id(
        self,
        workspace_id: uuid.UUID,
        item: ReadoutDataItem,
        idx: int,
    ) -> Result[uuid.UUID, DomainError]:
        """Resolve batch_id from the item, looking up by batch_number if needed."""
        if item.batch_id is not None:
            return Success(item.batch_id)
        if item.batch_number is not None:
            if self._batch_repo is None:
                return Failure(ValidationError(
                    f"Item {idx}: batch_number provided but batch resolver not available"
                ))
            batch = await self._batch_repo.find_by_batch_number(
                workspace_id, item.batch_number
            )
            if batch is None:
                return Failure(ValidationError(
                    f"Item {idx}: batch with batch_number "
                    f"'{item.batch_number}' not found"
                ))
            return Success(batch.id)
        return Failure(ValidationError(
            f"Item {idx}: either batch_id or batch_number is required"
        ))

    async def _resolve_readout_definition_id(
        self,
        item: ReadoutDataItem,
        idx: int,
        run_protocol_cache: dict[uuid.UUID, dict],
    ) -> Result[uuid.UUID, DomainError]:
        """Resolve readout_definition_id, looking up by name from the run's protocol if needed."""
        if item.readout_definition_id is not None:
            return Success(item.readout_definition_id)
        if item.readout_definition_name is not None:
            if self._run_repo is None or self._protocol_repo is None:
                return Failure(ValidationError(
                    f"Item {idx}: readout_definition_name provided but "
                    f"run/protocol resolver not available"
                ))
            # Cache protocol readout definitions per run to avoid repeated lookups
            if item.run_id not in run_protocol_cache:
                run = await self._run_repo.find_by_id(item.run_id)
                if run is None:
                    return Failure(ValidationError(
                        f"Item {idx}: run '{item.run_id}' not found"
                    ))
                protocol = await self._protocol_repo.find_by_id(run.protocol_id)
                if protocol is None:
                    return Failure(ValidationError(
                        f"Item {idx}: protocol for run '{item.run_id}' not found"
                    ))
                run_protocol_cache[item.run_id] = {
                    "definitions": protocol.readout_definitions,
                }

            definitions = run_protocol_cache[item.run_id]["definitions"]
            for rd in definitions:
                if rd.name == item.readout_definition_name:
                    return Success(rd.id)
            return Failure(ValidationError(
                f"Item {idx}: readout definition '{item.readout_definition_name}' "
                f"not found in protocol"
            ))
        return Failure(ValidationError(
            f"Item {idx}: either readout_definition_id or readout_definition_name is required"
        ))

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
            run_protocol_cache: dict[uuid.UUID, dict] = {}

            for idx, item in enumerate(input.items):
                # Resolve human-readable identifiers to UUIDs
                molecule_result = await self._resolve_molecule_id(
                    input.workspace_id, item, idx
                )
                if isinstance(molecule_result, Failure):
                    result.error_count += 1
                    result.errors.append({"index": idx, "error": str(molecule_result.failure())})
                    continue

                batch_result = await self._resolve_batch_id(
                    input.workspace_id, item, idx
                )
                if isinstance(batch_result, Failure):
                    result.error_count += 1
                    result.errors.append({"index": idx, "error": str(batch_result.failure())})
                    continue

                readout_def_result = await self._resolve_readout_definition_id(
                    item, idx, run_protocol_cache
                )
                if isinstance(readout_def_result, Failure):
                    result.error_count += 1
                    result.errors.append({"index": idx, "error": str(readout_def_result.failure())})
                    continue

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
                        molecule_id=molecule_result.unwrap(),
                        batch_id=batch_result.unwrap(),
                        readout_definition_id=readout_def_result.unwrap(),
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
