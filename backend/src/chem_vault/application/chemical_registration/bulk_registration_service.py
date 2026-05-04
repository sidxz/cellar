"""BulkRegistrationService — orchestrates bulk import of molecules from a file.

Synchronous (single-request) processing. Will be migrated to Temporal
workflow in S49 for production-grade async execution with progress tracking.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.chemical_registration.protocols import (
    DetectedSaltDTO,
    StructureProcessorProtocol,
)
from chem_vault.application.chemical_registration.register_molecule import (
    ExternalId,
    RegisterMolecule,
    RegisterMoleculeCommand,
    RegistrationOutcome,
)
from chem_vault.application.inventory.create_batch import CreateBatch, CreateBatchCommand
from chem_vault.application.inventory.salt_matcher import SaltMatcher, compute_formula_weight
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.bulk_registration import BulkRegistration
from chem_vault.domain.chemical_registration.enums import BulkRegistrationFileFormat
from chem_vault.domain.chemical_registration.repository import (
    BulkRegistrationRepository,
    MoleculeRepository,
)
from chem_vault.domain.inventory.repository import BatchRepository
from chem_vault.domain.shared.errors import DomainError, ValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BulkRegistrationItem:
    """Application-layer DTO for a single parsed molecule record."""

    row_index: int
    name: str | None = None
    smiles: str | None = None
    molecule_type: str = "small_molecule"
    external_ids: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None
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
    ) -> None:
        self._uow = uow
        self._bulk_reg_repo = bulk_reg_repo
        self._mol_repo = mol_repo
        self._dispatcher = dispatcher
        self._structure_processor = structure_processor
        self._salt_matcher = salt_matcher
        self._batch_repo = batch_repo

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

                # Create a batch for the registered molecule
                batch_id, batch_number, salt_matched = await self._create_batch_for_item(
                    item=item,
                    reg_outcome=outcome,
                    workspace_id=workspace_id,
                    submitted_by=submitted_by,
                )

                results.append(
                    BulkRegistrationItemResult(
                        row_index=item.row_index,
                        success=True,
                        is_new=outcome.is_new,
                        molecule_id=outcome.molecule.id,
                        batch_id=batch_id,
                        batch_number=batch_number,
                        salt_matched=salt_matched,
                    )
                )

        return results

    async def _create_batch_for_item(
        self,
        *,
        item: BulkRegistrationItem,
        reg_outcome: RegistrationOutcome,
        workspace_id: uuid.UUID,
        submitted_by: uuid.UUID,
    ) -> tuple[uuid.UUID | None, str | None, bool]:
        """Resolve salt and create a batch for a successfully registered molecule.

        Salt resolution priority:
        1. Explicit salt_code from the import row -> match_by_code
        2. Auto-detected salt from structure processing -> match_by_smiles
        3. No salt

        Returns (batch_id, batch_number, salt_matched).
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

        create_batch = CreateBatch(
            uow=self._uow,
            repo=self._batch_repo,
            molecule_repo=self._mol_repo,
            dispatcher=self._dispatcher,
        )

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

        batch_result = await create_batch(batch_cmd)

        if isinstance(batch_result, Failure):
            logger.warning(
                "Batch creation failed for molecule %s row %d: %s",
                molecule.id,
                item.row_index,
                batch_result.failure(),
            )
            return None, None, False

        batch = batch_result.unwrap()
        return batch.id, batch.batch_number.value, salt_matched
