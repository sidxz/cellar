"""BulkRegistrationService — orchestrates bulk import of molecules from a file.

Synchronous (single-request) processing. Will be migrated to Temporal
workflow in S49 for production-grade async execution with progress tracking.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

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
from chem_vault.infrastructure.parsers.chemical_file_parser import (
    ParsedMoleculeItem,
    get_parser,
)


@dataclass(frozen=True, kw_only=True)
class StartBulkRegistrationCommand(Command):
    workspace_id: uuid.UUID
    source_file: str
    file_format: str
    file_content: bytes
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
    """Orchestrate bulk molecule registration from a parsed file.

    Flow:
    1. Parse file into items
    2. Create BulkRegistration aggregate
    3. For each item: delegate to RegisterMolecule use case
    4. Track progress counters
    5. Complete the BulkRegistration
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

    async def execute(
        self,
        cmd: StartBulkRegistrationCommand,
        auth: AuthContext | None = None,
    ) -> Result[BulkRegistrationOutcome, DomainError]:
        require_editor(auth)

        # 1. Parse
        try:
            file_format = BulkRegistrationFileFormat(cmd.file_format)
        except ValueError:
            return Failure(ValidationError(f"Unsupported file format: {cmd.file_format}"))

        parser = get_parser(file_format)
        items = parser.parse(cmd.file_content, cmd.source_file)

        if not items:
            return Failure(ValidationError("File contains no records"))

        # 2. Create BulkRegistration tracking aggregate
        async with self._uow:
            bulk_reg = BulkRegistration.create(
                workspace_id=cmd.workspace_id,
                source_file=cmd.source_file,
                file_format=file_format,
                submitted_by=cmd.submitted_by,
                total_count=len(items),
            )
            bulk_reg.start_processing()
            await self._bulk_reg_repo.save(bulk_reg)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)

        # 3. Process each item sequentially (within-batch dedup)
        item_results = await self._process_items(
            items=items,
            bulk_reg=bulk_reg,
            workspace_id=cmd.workspace_id,
            originating_org_id=cmd.originating_org_id,
            submitted_by=cmd.submitted_by,
        )

        # 4. Complete
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
        items: list[ParsedMoleculeItem],
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
