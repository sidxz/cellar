"""BulkRegistrationService — orchestrates bulk import of molecules from a file.

Synchronous (single-request) processing. Will be migrated to Temporal
workflow in S49 for production-grade async execution with progress tracking.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.bulk_registration import BulkRegistration
from chem_vault.domain.chemical_registration.enums import BulkRegistrationFileFormat
from chem_vault.domain.chemical_registration.repository import (
    BulkRegistrationRepository,
    MoleculeRepository,
)
from chem_vault.application.chemical_registration.protocols import StructureProcessorProtocol
from chem_vault.application.chemical_registration.register_molecule import (
    ExternalId,
    RegisterMolecule,
    RegisterMoleculeCommand,
)
from chem_vault.domain.shared.errors import DomainError, ValidationError


@dataclass(frozen=True)
class BulkRegistrationItem:
    """Application-layer DTO for a single parsed molecule record."""

    row_index: int
    name: str | None = None
    smiles: str | None = None
    molecule_type: str = "small_molecule"
    external_ids: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True, kw_only=True)
class StartBulkRegistrationCommand(Command):
    workspace_id: uuid.UUID
    source_file: str
    file_format: str
    items: list[BulkRegistrationItem]
    submitted_by: uuid.UUID
    originating_org_id: uuid.UUID


@dataclass(frozen=True)
class BulkRegistrationItemResult:
    row_index: int
    success: bool
    is_new: bool = False
    molecule_id: uuid.UUID | None = None
    error: str | None = None


@dataclass(frozen=True)
class BulkRegistrationOutcome:
    bulk_registration: BulkRegistration
    item_results: list[BulkRegistrationItemResult]


class BulkRegistrationService:
    """Orchestrate bulk molecule registration from pre-parsed items.

    Flow:
    1. Create BulkRegistration aggregate
    2. For each item: delegate to RegisterMolecule use case
    3. Track progress counters
    4. Complete the BulkRegistration
    """

    def __init__(
        self,
        uow: UnitOfWork,
        bulk_reg_repo: BulkRegistrationRepository,
        mol_repo: MoleculeRepository,
        dispatcher: EventDispatcherProtocol,
        structure_processor: StructureProcessorProtocol,
    ) -> None:
        self._uow = uow
        self._bulk_reg_repo = bulk_reg_repo
        self._mol_repo = mol_repo
        self._dispatcher = dispatcher
        self._structure_processor = structure_processor

    async def __call__(
        self,
        input: StartBulkRegistrationCommand,
        auth: AuthContext | None = None,
    ) -> Result[BulkRegistrationOutcome, DomainError]:
        require_editor(auth)

        try:
            file_format = BulkRegistrationFileFormat(input.file_format)
        except ValueError:
            return Failure(ValidationError(f"Unsupported file format: {input.file_format}"))

        if not input.items:
            return Failure(ValidationError("File contains no records"))

        # 1. Create BulkRegistration tracking aggregate
        async with self._uow:
            bulk_reg = BulkRegistration.create(
                workspace_id=input.workspace_id,
                source_file=input.source_file,
                file_format=file_format,
                submitted_by=input.submitted_by,
                total_count=len(input.items),
            )
            bulk_reg.start_processing()
            await self._bulk_reg_repo.save(bulk_reg)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)

        # 2. Process each item sequentially (within-batch dedup)
        item_results = await self._process_items(
            items=input.items,
            bulk_reg=bulk_reg,
            workspace_id=input.workspace_id,
            originating_org_id=input.originating_org_id,
            submitted_by=input.submitted_by,
        )

        # 3. Complete
        async with self._uow:
            bulk_reg.complete()
            await self._bulk_reg_repo.save(bulk_reg)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)

        return Success(
            BulkRegistrationOutcome(
                bulk_registration=bulk_reg,
                item_results=item_results,
            )
        )

    async def _process_items(
        self,
        *,
        items: list[BulkRegistrationItem],
        bulk_reg: BulkRegistration,
        workspace_id: uuid.UUID,
        originating_org_id: uuid.UUID,
        submitted_by: uuid.UUID,
    ) -> list[BulkRegistrationItemResult]:
        results: list[BulkRegistrationItemResult] = []
        register_uc = RegisterMolecule(
            uow=self._uow,
            repo=self._mol_repo,
            dispatcher=self._dispatcher,
            structure_processor=self._structure_processor,
        )

        for item in items:
            if item.error:
                bulk_reg.record_error()
                results.append(
                    BulkRegistrationItemResult(
                        row_index=item.row_index,
                        success=False,
                        error=item.error,
                    )
                )
                continue

            has_explicit_name = bool(item.name)
            cmd = RegisterMoleculeCommand(
                workspace_id=workspace_id,
                name=item.name or f"Compound-{item.row_index + 1}",
                smiles=item.smiles,
                molecule_type=item.molecule_type,
                external_ids=[
                    ExternalId(
                        identifier=eid["identifier"],
                        identifier_type=eid["identifier_type"],
                    )
                    for eid in item.external_ids
                ],
                originating_org_id=originating_org_id,
                registered_by=submitted_by,
                promote_name_as_identifier=has_explicit_name,
            )

            result = await register_uc(cmd)

            if isinstance(result, Failure):
                bulk_reg.record_error()
                err = result.failure()
                results.append(
                    BulkRegistrationItemResult(
                        row_index=item.row_index,
                        success=False,
                        error=str(err),
                    )
                )
            else:
                outcome = result.unwrap()
                if outcome.is_new:
                    bulk_reg.record_registered()
                else:
                    bulk_reg.record_duplicate()
                results.append(
                    BulkRegistrationItemResult(
                        row_index=item.row_index,
                        success=True,
                        is_new=outcome.is_new,
                        molecule_id=outcome.molecule.id,
                    )
                )

        return results
