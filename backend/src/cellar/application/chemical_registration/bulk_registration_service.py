"""BulkRegistrationService — orchestrates bulk import of molecules from a file.

Synchronous (single-request) processing. Will be migrated to Temporal
workflow in S49 for production-grade async execution with progress tracking.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.chemical_registration.protocols import (
    StructureProcessorProtocol,
)
from cellar.application.chemical_registration.register_molecule import (
    RegisterMolecule,
    RegisterMoleculeCommand,
    RegistrationOutcome,
    external_ids,
)
from cellar.application.chemical_registration.row_batch import (
    ApplyRowBatch,
    ApplyRowBatchCommand,
    row_batch_ids,
)
from cellar.application.inventory.batch_policy import should_create_batch
from cellar.application.inventory.create_batch import CreateBatch, CreateBatchCommand
from cellar.application.inventory.salt_matcher import SaltMatcher, compute_formula_weight
from cellar.application.inventory.sync_batch_identifier_mirrors import SyncBatchIdentifierMirrors
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.bulk_registration import BulkRegistration
from cellar.domain.chemical_registration.enums import (
    BulkRegistrationFileFormat,
    BulkRegistrationItemAction,
)
from cellar.domain.chemical_registration.repository import (
    BulkRegistrationRepository,
    MoleculeRepository,
)
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.shared.errors import DomainError, ValidationError
from cellar.domain.workspace_config.repository import WorkspaceSettingsRepository

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class BulkRegistrationItem:
    """Application-layer DTO for a single parsed molecule record."""

    row_index: int
    file_row: int = 0
    name: str | None = None
    smiles: str | None = None
    molecule_type: str = "small_molecule"
    # {"identifier", "identifier_type", "source"?, "decides"?}
    external_ids: list[dict[str, Any]] = field(default_factory=list)
    # {"identifier", "source", "identifier_type"?, "decides"?}
    batch_ids: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    batch_problem: str | None = None  # compound registers, no batch
    # Values the row had that are not stored (e.g. too long for an ID).
    warnings: list[str] = field(default_factory=list)
    # Batch fields
    amount_value: float | None = None
    amount_unit: str = "mg"
    salt_code: str | None = None
    salt_stoichiometry: int = 1
    purity: float | None = None
    batch_source: str = "synthesized"
    appearance: str | None = None


@dataclass(frozen=True, kw_only=True)
class StartBulkRegistrationCommand(Command):
    workspace_id: uuid.UUID
    source_file: str
    file_format: str
    items: list[BulkRegistrationItem]
    submitted_by: uuid.UUID
    originating_org_id: uuid.UUID
    create_batch_on_duplicate: bool | None = None  # None → use workspace default
    project_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass(frozen=True)
class BulkRegistrationItemResult:
    row_index: int
    success: bool
    is_new: bool = False
    molecule_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    batch_number: str | None = None
    salt_matched: bool = False
    error: str | None = None
    batch_error: str | None = None
    batch_skipped: bool = False
    # What was not stored, and why: the row's own values, stored-only IDs another
    # compound / batch holds; and notes.
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BulkRegistrationOutcome:
    bulk_registration: BulkRegistration
    item_results: list[BulkRegistrationItemResult]


class BulkRegistrationService:
    """Orchestrate bulk molecule registration from pre-parsed items.

    Flow:
    1. Create BulkRegistration aggregate
    2. For each item: delegate to RegisterMolecule use case, then create a Batch
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
        salt_matcher: SaltMatcher,
        batch_repo: BatchRepository,
        settings_repo: WorkspaceSettingsRepository,
        sync: SyncBatchIdentifierMirrors | None = None,
    ) -> None:
        self._uow = uow
        self._bulk_reg_repo = bulk_reg_repo
        self._mol_repo = mol_repo
        self._dispatcher = dispatcher
        self._structure_processor = structure_processor
        self._salt_matcher = salt_matcher
        self._batch_repo = batch_repo
        self._settings_repo = settings_repo
        self._sync = sync

    async def __call__(
        self,
        input: StartBulkRegistrationCommand,
        auth: AuthContext | None = None,
    ) -> Result[BulkRegistrationOutcome, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        try:
            file_format = BulkRegistrationFileFormat(input.file_format)
        except ValueError:
            return Failure(ValidationError(f"Unsupported file format: {input.file_format}"))

        if not input.items:
            return Failure(ValidationError("File contains no records"))

        # Read workspace default once per workflow; per-request override wins if set.
        async with self._uow:
            ws_settings = await self._settings_repo.find_by_workspace_id(input.workspace_id)
        workspace_default = ws_settings.create_batch_on_duplicate if ws_settings else False
        effective_policy_default = (
            input.create_batch_on_duplicate
            if input.create_batch_on_duplicate is not None
            else workspace_default
        )

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
            auth=auth,
            effective_policy_default=effective_policy_default,
            project_ids=input.project_ids,
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
        auth: AuthContext | None,
        effective_policy_default: bool,
        project_ids: list[uuid.UUID],
    ) -> list[BulkRegistrationItemResult]:
        results: list[BulkRegistrationItemResult] = []
        register_uc = RegisterMolecule(
            uow=self._uow,
            repo=self._mol_repo,
            dispatcher=self._dispatcher,
            structure_processor=self._structure_processor,
        )

        # Pending per-row outcomes — recorded onto the aggregate inside the
        # final "complete" UoW block so all writes commit atomically and we
        # don't nest UoWs across RegisterMolecule's own transaction.
        pending: list[dict] = []

        for item in items:
            if item.error:
                pending.append(
                    {
                        "row_index": item.row_index,
                        "action": BulkRegistrationItemAction.ERROR,
                        "error": item.error,
                    }
                )
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
                external_ids=external_ids(item.external_ids),
                originating_org_id=originating_org_id,
                registered_by=submitted_by,
                promote_name_as_identifier=has_explicit_name,
                project_ids=project_ids,
            )

            result = await register_uc(cmd, auth=auth)

            if isinstance(result, Failure):
                err = result.failure()
                pending.append(
                    {
                        "row_index": item.row_index,
                        "action": BulkRegistrationItemAction.ERROR,
                        "error": str(err),
                    }
                )
                results.append(
                    BulkRegistrationItemResult(
                        row_index=item.row_index,
                        success=False,
                        error=str(err),
                    )
                )
            else:
                outcome = result.unwrap()
                action = (
                    BulkRegistrationItemAction.REGISTERED
                    if outcome.is_new
                    else BulkRegistrationItemAction.DEDUPLICATED
                )

                # Consult policy: always batch new molecules; for dups, use effective default.
                create_batch_now = should_create_batch(
                    is_new_molecule=outcome.is_new,
                    # workflow-level decision already collapsed into effective_policy_default
                    override=None,
                    workspace_default=effective_policy_default,
                )

                batch_warnings: tuple[str, ...] = ()
                if item.batch_problem:
                    batch_id, batch_number, salt_matched = None, None, False
                    batch_err = item.batch_problem
                    batch_skipped = False
                elif item.batch_ids:
                    # The row names its batch: find or create exactly that batch.
                    (
                        batch_id,
                        batch_number,
                        salt_matched,
                        batch_err,
                        batch_warnings,
                    ) = await self._apply_row_batch(
                        item=item,
                        reg_outcome=outcome,
                        workspace_id=workspace_id,
                        submitted_by=submitted_by,
                        auth=auth,
                    )
                    batch_skipped = False
                elif create_batch_now:
                    (
                        batch_id,
                        batch_number,
                        salt_matched,
                        batch_err,
                    ) = await self._create_batch_for_item(
                        item=item,
                        reg_outcome=outcome,
                        workspace_id=workspace_id,
                        submitted_by=submitted_by,
                        auth=auth,
                    )
                    batch_skipped = False
                else:
                    batch_id, batch_number, salt_matched, batch_err = None, None, False, None
                    batch_skipped = True

                pending.append(
                    {
                        "row_index": item.row_index,
                        "action": action,
                        "molecule_id": outcome.molecule.id,
                        "molecule_name": outcome.molecule.name,
                        "registration_number": outcome.molecule.registration_number.value
                        if outcome.molecule.registration_number
                        else None,
                        "batch_id": batch_id,
                        "batch_number": batch_number,
                        "error": f"Compound registered, batch not created: {batch_err}"
                        if batch_err
                        else None,
                    }
                )

                results.append(
                    BulkRegistrationItemResult(
                        row_index=item.row_index,
                        success=batch_err is None,
                        is_new=outcome.is_new,
                        molecule_id=outcome.molecule.id,
                        batch_id=batch_id,
                        batch_number=batch_number,
                        salt_matched=salt_matched,
                        batch_error=batch_err,
                        batch_skipped=batch_skipped,
                        warnings=[
                            *item.warnings,
                            *outcome.notes,
                            *outcome.skipped_ids,
                            *batch_warnings,
                        ],
                    )
                )

        # Stash on the aggregate so the caller's "complete" UoW block flushes
        # them alongside the final aggregate save.
        for entry in pending:
            bulk_reg.record_item(**entry)

        return results

    def _new_create_batch(self) -> CreateBatch:
        return CreateBatch(
            uow=self._uow,
            repo=self._batch_repo,
            molecule_repo=self._mol_repo,
            dispatcher=self._dispatcher,
            sync=self._sync,
        )

    async def _apply_row_batch(
        self,
        *,
        item: BulkRegistrationItem,
        reg_outcome: RegistrationOutcome,
        workspace_id: uuid.UUID,
        submitted_by: uuid.UUID,
        auth: AuthContext | None,
    ) -> tuple[uuid.UUID | None, str | None, bool, str | None, tuple[str, ...]]:
        """``_create_batch_for_item``'s shape plus the skipped-ID warnings; a row-batch
        problem is reported as the batch error (the compound stays registered)."""
        batch_cmd, salt_matched = await self._batch_command_for_item(
            item=item,
            reg_outcome=reg_outcome,
            workspace_id=workspace_id,
            submitted_by=submitted_by,
        )
        apply = ApplyRowBatch(
            uow=self._uow,
            batch_repo=self._batch_repo,
            create_batch=self._new_create_batch(),
            dispatcher=self._dispatcher,
        )
        result = await apply(
            ApplyRowBatchCommand(
                workspace_id=workspace_id,
                molecule_id=reg_outcome.molecule.id,
                batch_ids=row_batch_ids(item.batch_ids),
                create=batch_cmd,
                actor=submitted_by,
            ),
            auth=auth,
        )
        if isinstance(result, Failure):
            return None, None, False, str(result.failure()), ()
        r = result.unwrap()
        if r.action == "problem":
            return None, None, False, r.problem, ()
        created = r.action == "created"
        return r.batch_id, r.batch_number, salt_matched and created, None, r.skipped

    async def _create_batch_for_item(
        self,
        *,
        item: BulkRegistrationItem,
        reg_outcome: RegistrationOutcome,
        workspace_id: uuid.UUID,
        submitted_by: uuid.UUID,
        auth: AuthContext | None,
    ) -> tuple[uuid.UUID | None, str | None, bool, str | None]:
        """Create a batch for a successfully registered molecule.

        Returns ``(batch_id, batch_number, salt_matched, batch_error)``.
        ``batch_error`` is ``None`` on success, otherwise a human-readable
        message describing why the batch creation failed.
        """
        batch_cmd, salt_matched = await self._batch_command_for_item(
            item=item,
            reg_outcome=reg_outcome,
            workspace_id=workspace_id,
            submitted_by=submitted_by,
        )
        batch_result = await self._new_create_batch()(batch_cmd, auth=auth)

        if isinstance(batch_result, Failure):
            err = batch_result.failure()
            logger.warning(
                "bulk_registration.batch_create_failed",
                molecule_id=str(reg_outcome.molecule.id),
                row_index=item.row_index,
                error=str(err),
            )
            return None, None, False, str(err)

        batch = batch_result.unwrap().batch
        return batch.id, batch.batch_number.value, salt_matched, None

    async def _batch_command_for_item(
        self,
        *,
        item: BulkRegistrationItem,
        reg_outcome: RegistrationOutcome,
        workspace_id: uuid.UUID,
        submitted_by: uuid.UUID,
    ) -> tuple[CreateBatchCommand, bool]:
        """Resolve salt and build the batch command for a registered molecule.

        Salt resolution priority:
        1. Explicit salt_code from the import row -> match_by_code
        2. Auto-detected salt from structure processing -> match_by_smiles
        3. No salt

        Returns ``(command, salt_matched)``.
        """
        molecule = reg_outcome.molecule
        detected_salt = reg_outcome.detected_salt

        salt_entry_id: uuid.UUID | None = None
        salt_name: str | None = None
        salt_smiles: str | None = None
        salt_stoichiometry: int = item.salt_stoichiometry
        formula_weight: float | None = None
        salt_matched = False

        # 1. Explicit salt code from import row
        if item.salt_code:
            entry = await self._salt_matcher.match_by_code(workspace_id, item.salt_code)
            if entry is not None:
                salt_entry_id = entry.id
                salt_name = entry.name
                salt_smiles = entry.smiles
                salt_matched = True
                if molecule.descriptors and molecule.descriptors.molecular_weight:
                    formula_weight = compute_formula_weight(
                        molecule.descriptors.molecular_weight,
                        entry.molecular_weight,
                        salt_stoichiometry,
                    )
        # 2. Auto-detected salt from structure processing
        elif detected_salt is not None:
            entry = await self._salt_matcher.match_by_smiles(
                workspace_id, detected_salt.salt_smiles
            )
            if entry is not None:
                salt_entry_id = entry.id
                salt_name = entry.name
                salt_smiles = entry.smiles
                salt_stoichiometry = detected_salt.stoichiometry
                salt_matched = True
                if molecule.descriptors and molecule.descriptors.molecular_weight:
                    formula_weight = compute_formula_weight(
                        molecule.descriptors.molecular_weight,
                        entry.molecular_weight,
                        salt_stoichiometry,
                    )
            else:
                # Detected salt not in catalog — pass through raw info
                salt_smiles = detected_salt.salt_smiles
                salt_stoichiometry = detected_salt.stoichiometry

        batch_cmd = CreateBatchCommand(
            workspace_id=workspace_id,
            molecule_id=molecule.id,
            source=item.batch_source,
            chemist=submitted_by,
            amount_value=item.amount_value if item.amount_value is not None else 0.0,
            amount_unit=item.amount_unit,
            salt_entry_id=salt_entry_id,
            salt_name=salt_name,
            salt_smiles=salt_smiles,
            salt_stoichiometry=salt_stoichiometry,
            formula_weight=formula_weight,
            purity=item.purity,
            appearance=item.appearance,
        )
        return batch_cmd, salt_matched
