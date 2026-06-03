"""BulkCreateReadoutData — batch import of readout measurements."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.screening_assay.data_lock_guard import DataLockGuard
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.repository import (
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from cellar.domain.shared.enums import Qualifier
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.shared.value_objects import QualifiedValue


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
    errors: list[dict[str, Any]] = field(default_factory=list)


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
                return Failure(
                    ValidationError(
                        f"Item {idx}: registration_number provided but molecule resolver not available"
                    )
                )
            mol = await self._molecule_repo.find_by_registration_number(
                workspace_id, item.registration_number
            )
            if mol is None:
                return Failure(
                    ValidationError(
                        f"Item {idx}: molecule with registration_number "
                        f"'{item.registration_number}' not found"
                    )
                )
            return Success(mol.id)
        return Failure(
            ValidationError(f"Item {idx}: either molecule_id or registration_number is required")
        )

    async def _resolve_batch_id(
        self,
        workspace_id: uuid.UUID,
        item: ReadoutDataItem,
        idx: int,
        *,
        require_batch: bool = True,
    ) -> Result[uuid.UUID | None, DomainError]:
        """Resolve batch_id from the item, looking up by batch_number if needed.

        When ``require_batch`` is False, an item carrying neither ``batch_id`` nor
        ``batch_number`` resolves to ``Success(None)`` (a compound-only row) rather
        than failing. A batch identifier, if supplied, is always resolved (and any
        resolution failure surfaced) regardless of ``require_batch``.
        """
        if item.batch_id is not None:
            return Success(item.batch_id)
        if item.batch_number is not None:
            if self._batch_repo is None:
                return Failure(
                    ValidationError(
                        f"Item {idx}: batch_number provided but batch resolver not available"
                    )
                )
            batch = await self._batch_repo.find_by_batch_number(workspace_id, item.batch_number)
            if batch is None:
                return Failure(
                    ValidationError(
                        f"Item {idx}: batch with batch_number '{item.batch_number}' not found"
                    )
                )
            return Success(batch.id)
        if not require_batch:
            return Success(None)
        return Failure(ValidationError(f"Item {idx}: either batch_id or batch_number is required"))

    async def _ensure_run_protocol_loaded(
        self,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        idx: int,
        run_protocol_cache: dict[uuid.UUID, dict[str, Any]],
    ) -> Result[dict[str, Any], DomainError]:
        """Cache (and return) the readout definitions for a run's protocol."""
        if run_id in run_protocol_cache:
            return Success(run_protocol_cache[run_id])
        if self._run_repo is None or self._protocol_repo is None:
            return Failure(ValidationError(f"Item {idx}: run/protocol resolver not available"))
        run = await self._run_repo.find_by_id_in_workspace(workspace_id, run_id)
        if run is None:
            return Failure(ValidationError(f"Item {idx}: run '{run_id}' not found"))
        protocol = await self._protocol_repo.find_by_id_in_workspace(workspace_id, run.protocol_id)
        if protocol is None:
            return Failure(ValidationError(f"Item {idx}: protocol for run '{run_id}' not found"))
        cache_entry = {"definitions": protocol.readout_definitions}
        run_protocol_cache[run_id] = cache_entry
        return Success(cache_entry)

    async def _resolve_readout_definition_id(
        self,
        workspace_id: uuid.UUID,
        item: ReadoutDataItem,
        idx: int,
        run_protocol_cache: dict[uuid.UUID, dict[str, Any]],
    ) -> Result[uuid.UUID, DomainError]:
        """Resolve readout_definition_id and verify it belongs to the run's protocol."""
        cache_result = await self._ensure_run_protocol_loaded(
            workspace_id, item.run_id, idx, run_protocol_cache
        )
        if isinstance(cache_result, Failure):
            # If the resolver isn't wired AND the caller supplied a UUID, fall
            # through to trust the caller (legacy callers without protocol_repo).
            if item.readout_definition_id is not None and self._protocol_repo is None:
                return Success(item.readout_definition_id)
            return cache_result
        definitions = cache_result.unwrap()["definitions"]
        defs_by_id = {rd.id: rd for rd in definitions}
        defs_by_name = {rd.name: rd for rd in definitions}

        if item.readout_definition_id is not None:
            if item.readout_definition_id not in defs_by_id:
                return Failure(
                    ValidationError(
                        f"Item {idx}: readout_definition_id '{item.readout_definition_id}' "
                        f"does not belong to the run's protocol"
                    )
                )
            return Success(item.readout_definition_id)
        if item.readout_definition_name is not None:
            rd = defs_by_name.get(item.readout_definition_name)
            if rd is None:
                return Failure(
                    ValidationError(
                        f"Item {idx}: readout definition '{item.readout_definition_name}' "
                        f"not found in protocol"
                    )
                )
            return Success(rd.id)
        return Failure(
            ValidationError(
                f"Item {idx}: either readout_definition_id or readout_definition_name is required"
            )
        )

    @staticmethod
    def _build_value(item: ReadoutDataItem) -> QualifiedValue | None:
        """Map an item's numeric value + qualifier to a QualifiedValue (or None)."""
        if item.value_numeric is None:
            return None
        qualifier = Qualifier(item.value_qualifier) if item.value_qualifier else Qualifier.EQUAL
        return QualifiedValue(value=item.value_numeric, qualifier=qualifier)

    async def __call__(
        self,
        input: BulkCreateReadoutDataCommand,
        auth: AuthContext | None = None,
        *,
        upsert: bool = False,
        require_batch: bool = True,
    ) -> Result[BulkReadoutResult, DomainError]:
        require_editor(auth)

        if not input.items:
            return Failure(ValidationError("No items provided"))

        async with self._uow:
            # Verify all referenced runs belong to this workspace
            run_ids = {item.run_id for item in input.items}
            if self._run_repo is not None:
                for run_id in run_ids:
                    run = await self._run_repo.find_by_id_in_workspace(input.workspace_id, run_id)
                    if run is None:
                        return Failure(NotFoundError("Run", str(run_id)))

            # Check locks for all unique run IDs — reject entire batch if any locked
            for run_id in run_ids:
                try:
                    await self._guard.guard_write(input.workspace_id, run_id)
                except DomainError as exc:
                    return Failure(exc)

            result = BulkReadoutResult(total_count=len(input.items))
            entities: list[ReadoutData] = []
            run_protocol_cache: dict[uuid.UUID, dict[str, Any]] = {}

            for idx, item in enumerate(input.items):
                has_batch = item.batch_id is not None or item.batch_number is not None
                has_molecule = item.molecule_id is not None or item.registration_number is not None

                # When batch is optional, a batch-less item must still carry a
                # molecule so we never persist a row with neither identity.
                if not require_batch and not has_batch and not has_molecule:
                    result.error_count += 1
                    result.errors.append(
                        {"index": idx, "error": f"Item {idx}: a molecule or batch is required"}
                    )
                    continue

                # Resolve human-readable identifiers to UUIDs
                molecule_result = await self._resolve_molecule_id(input.workspace_id, item, idx)
                if isinstance(molecule_result, Failure):
                    result.error_count += 1
                    result.errors.append({"index": idx, "error": str(molecule_result.failure())})
                    continue

                batch_result = await self._resolve_batch_id(
                    input.workspace_id, item, idx, require_batch=require_batch
                )
                if isinstance(batch_result, Failure):
                    result.error_count += 1
                    result.errors.append({"index": idx, "error": str(batch_result.failure())})
                    continue

                readout_def_result = await self._resolve_readout_definition_id(
                    input.workspace_id, item, idx, run_protocol_cache
                )
                if isinstance(readout_def_result, Failure):
                    result.error_count += 1
                    result.errors.append(
                        {"index": idx, "error": str(readout_def_result.failure())}
                    )
                    continue

                molecule_id = molecule_result.unwrap()
                batch_id = batch_result.unwrap()
                readout_definition_id = readout_def_result.unwrap()

                try:
                    value = self._build_value(item)

                    existing: ReadoutData | None = None
                    if upsert:
                        existing = await self._repo.find_wellless_by_keys(
                            workspace_id=input.workspace_id,
                            run_id=item.run_id,
                            molecule_id=molecule_id,
                            batch_id=batch_id,
                            readout_definition_id=readout_definition_id,
                        )

                    if existing is not None:
                        # Overwrite the existing endpoint value in place; the row
                        # keeps its PK so the repo UPDATEs (latest-wins).
                        existing.update_value(
                            value=value,
                            value_text=item.value_text,
                            is_outlier=item.is_outlier,
                        )
                        await self._repo.save(existing)
                    else:
                        rd = ReadoutData(
                            workspace_id=input.workspace_id,
                            run_id=item.run_id,
                            well_id=item.well_id,
                            molecule_id=molecule_id,
                            batch_id=batch_id,
                            readout_definition_id=readout_definition_id,
                            value=value,
                            value_text=item.value_text,
                            is_outlier=item.is_outlier,
                        )
                        entities.append(rd)
                    result.success_count += 1
                except (ValueError, TypeError) as e:
                    result.error_count += 1
                    result.errors.append({"index": idx, "error": str(e)})

            if entities:
                await self._repo.save_bulk(entities)

            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(result)
