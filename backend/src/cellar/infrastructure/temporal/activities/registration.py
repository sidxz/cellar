"""Registration activities — process a chunk of molecules through the registration pipeline.

Reuses existing RegisterMolecule + CreateBatch use cases. Each activity
invocation resolves fresh UoW + repos from the DI container.
"""

from __future__ import annotations

import uuid
from typing import Callable

import structlog
from returns.result import Failure
from sqlalchemy.ext.asyncio import async_sessionmaker
from temporalio import activity

from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher

from cellar.application.chemical_registration.disclosure_service import DisclosureService
from cellar.application.chemical_registration.merge_service import MergeService
from cellar.application.chemical_registration.merge_side_effect_registry import (
    MergeSideEffectRegistry,
)
from cellar.application.chemical_registration.protocols import StructureProcessorProtocol
from cellar.application.chemical_registration.register_molecule import (
    ExternalId,
    RegisterMolecule,
    RegisterMoleculeCommand,
    RegistrationOutcome,
)
from cellar.application.inventory.batch_identifiers import (
    AddBatchIdentifier,
    AddBatchIdentifierCommand,
)
from cellar.application.inventory.batch_policy import should_create_batch
from cellar.application.inventory.create_batch import CreateBatch, CreateBatchCommand
from cellar.application.inventory.salt_matcher import SaltMatcher, compute_formula_weight
from cellar.domain.chemical_registration.enums import RegistrationAction
from cellar.domain.workspace_config.repository import WorkspaceSettingsRepository
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.disclosure_request_repository import (
    SQLAlchemyDisclosureRequestRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.merge_event_repository import (
    SQLAlchemyMergeEventRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.salt_entry_repository import (
    SQLAlchemySaltEntryRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.workspace_settings_repository import (
    SQLAlchemyWorkspaceSettingsRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.temporal.activities.dtos import (
    ChunkInput,
    ChunkItem,
    ChunkItemResult,
    ChunkOutput,
)

logger = structlog.get_logger(__name__)


class RegistrationActivities:
    """Temporal activities for molecule registration."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        dispatcher: EventDispatcher,
        structure_processor: StructureProcessorProtocol,
        side_effect_registry: MergeSideEffectRegistry,
        settings_repo_factory: Callable[
            [AsyncUnitOfWork], WorkspaceSettingsRepository
        ] = SQLAlchemyWorkspaceSettingsRepository,
    ) -> None:
        self._session_factory = session_factory
        self._dispatcher = dispatcher
        self._structure_processor = structure_processor
        self._side_effect_registry = side_effect_registry
        self._settings_repo_factory = settings_repo_factory

    @activity.defn
    async def process_chunk(self, input: ChunkInput) -> ChunkOutput:
        """Process a chunk of molecules sequentially through registration + batch creation."""
        session_factory = self._session_factory
        dispatcher = self._dispatcher
        structure_processor = self._structure_processor
        side_effect_registry = self._side_effect_registry

        # RegisterMolecule and CreateBatch each manage their own UoW lifecycle
        # internally (async with self._uow:), so they need separate UoW instances
        # to avoid one closing the session that the other still needs.
        reg_uow = AsyncUnitOfWork(session_factory)

        # DisclosureService gets its own independent UoW because it is a
        # standalone use case that manages its own transaction.
        ds_uow = AsyncUnitOfWork(session_factory)
        ds_mol_repo = SQLAlchemyMoleculeRepository(ds_uow)
        ds_merge_svc = MergeService(
            uow=ds_uow,
            molecule_repo=ds_mol_repo,
            merge_event_repo=SQLAlchemyMergeEventRepository(ds_uow),
            dispatcher=dispatcher,
            side_effect_registry=side_effect_registry,
        )
        disclosure_service = DisclosureService(
            uow=ds_uow,
            molecule_repo=ds_mol_repo,
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(ds_uow),
            structure_processor=structure_processor,
            merge_service=ds_merge_svc,
            dispatcher=dispatcher,
        )

        register_uc = RegisterMolecule(
            uow=reg_uow,
            repo=SQLAlchemyMoleculeRepository(reg_uow),
            dispatcher=dispatcher,
            structure_processor=structure_processor,
            disclosure_service=disclosure_service,
        )

        ws_id = uuid.UUID(input.workspace_id)
        org_id = uuid.UUID(input.originating_org_id)
        submitted_by = uuid.UUID(input.submitted_by)

        # Read workspace settings once per chunk to determine batch creation policy.
        ws_uow = AsyncUnitOfWork(session_factory)
        ws_repo = self._settings_repo_factory(ws_uow)
        async with ws_uow:
            ws_settings = await ws_repo.find_by_workspace_id(ws_id)
        workspace_default = ws_settings.create_batch_on_duplicate if ws_settings else False

        # Collapse chunk-level override: if the caller specified a value on
        # ChunkInput, use that; otherwise fall back to the workspace setting.
        effective_policy_default = (
            input.create_batch_on_duplicate
            if input.create_batch_on_duplicate is not None
            else workspace_default
        )

        output = ChunkOutput()

        for item in input.items:
            has_explicit_name = bool(item.name)
            cmd = RegisterMoleculeCommand(
                workspace_id=ws_id,
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
                originating_org_id=org_id,
                registered_by=submitted_by,
                promote_name_as_identifier=has_explicit_name,
            )

            result = await register_uc(cmd)

            if isinstance(result, Failure):
                output.error += 1
                output.results.append(
                    ChunkItemResult(
                        row_index=item.row_index,
                        success=False,
                        error=str(result.failure()),
                        cdd_molecule_id=item.cdd_molecule_id,
                        cdd_modified_at=item.cdd_modified_at,
                    )
                )
                continue

            outcome = result.unwrap()
            action = outcome.action

            # Track counts by action
            if action == RegistrationAction.REGISTERED:
                output.registered += 1
            elif action == RegistrationAction.DEDUPLICATED:
                output.duplicate += 1
            elif action == RegistrationAction.DISCLOSED:
                output.disclosed += 1
            elif action == RegistrationAction.MERGE_CANDIDATE:
                output.merge_candidate += 1
            elif action == RegistrationAction.CONFLICT:
                output.conflict += 1

            # Skip batch for merge candidates and conflicts — those molecules
            # haven't been finalized yet, so creating a batch would be premature.
            # Also skip batch for duplicate registrations when policy says so.
            batch_id: uuid.UUID | None = None
            batch_number: str | None = None
            salt_matched = False
            batch_skipped = False
            if action not in (RegistrationAction.MERGE_CANDIDATE, RegistrationAction.CONFLICT):
                create_batch_now = should_create_batch(
                    is_new_molecule=outcome.is_new,
                    override=None,  # workflow-level decision already collapsed into effective_policy_default
                    workspace_default=effective_policy_default,
                )
                if create_batch_now:
                    batch_id, batch_number, salt_matched = await _create_batch(
                        item=item,
                        reg_outcome=outcome,
                        workspace_id=ws_id,
                        submitted_by=submitted_by,
                        session_factory=session_factory,
                        dispatcher=dispatcher,
                    )
                else:
                    batch_skipped = True

            output.results.append(
                ChunkItemResult(
                    row_index=item.row_index,
                    success=True,
                    is_new=outcome.is_new,
                    action=action.value,
                    molecule_id=str(outcome.molecule.id),
                    batch_id=str(batch_id) if batch_id else None,
                    batch_number=batch_number,
                    salt_matched=salt_matched,
                    batch_skipped=batch_skipped,
                    needs_merge_confirmation=outcome.needs_merge_confirmation,
                    matched_molecule_id=str(outcome.matched_molecule_id)
                    if outcome.matched_molecule_id
                    else None,
                    disclosure_id=str(outcome.disclosure_id) if outcome.disclosure_id else None,
                    conflict_reason=outcome.conflict_reason,
                    cdd_molecule_id=item.cdd_molecule_id,
                    cdd_modified_at=item.cdd_modified_at,
                )
            )

            activity.heartbeat(f"chunk {input.chunk_index}: {item.row_index}")

        # Derive molecule-level counts by grouping results on row_index.
        # Priority: "new" wins over "existing", any success wins over "error".
        mol_outcomes: dict[int, str] = {}  # row_index -> "new" | "existing" | "error"
        for r in output.results:
            prev = mol_outcomes.get(r.row_index)
            if not r.success:
                # Only mark as error if no prior success for this molecule
                if prev is None:
                    mol_outcomes[r.row_index] = "error"
            elif r.is_new:
                # First registration — always wins
                mol_outcomes[r.row_index] = "new"
            else:
                # Duplicate registration — upgrade from error/None but not from "new"
                if prev != "new":
                    mol_outcomes[r.row_index] = "existing"
        for outcome in mol_outcomes.values():
            if outcome == "new":
                output.mol_registered += 1
            elif outcome == "existing":
                output.mol_duplicate += 1
            else:
                output.mol_error += 1

        return output


async def _create_batch(
    *,
    item: ChunkItem,
    reg_outcome: RegistrationOutcome,
    workspace_id: uuid.UUID,
    submitted_by: uuid.UUID,
    session_factory: async_sessionmaker,
    dispatcher,
) -> tuple[uuid.UUID | None, str | None, bool]:
    """Resolve salt and create a batch. Uses a fresh UoW for each call."""
    molecule = reg_outcome.molecule
    detected_salt = reg_outcome.detected_salt

    salt_entry_id: uuid.UUID | None = None
    salt_name: str | None = None
    salt_smiles: str | None = None
    salt_stoichiometry: int = item.salt_stoichiometry
    formula_weight: float | None = None
    salt_matched = False

    # Salt matching needs its own UoW (read-only lookup)
    if item.salt_code or detected_salt is not None:
        salt_uow = AsyncUnitOfWork(session_factory)
        salt_matcher = SaltMatcher(SQLAlchemySaltEntryRepository(salt_uow))
        async with salt_uow:
            if item.salt_code:
                entry = await salt_matcher.match_by_code(workspace_id, item.salt_code)
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
            elif detected_salt is not None:
                entry = await salt_matcher.match_by_smiles(workspace_id, detected_salt.salt_smiles)
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
                    salt_smiles = detected_salt.salt_smiles
                    salt_stoichiometry = detected_salt.stoichiometry

    # Batch creation uses its own UoW (CreateBatch manages it internally)
    batch_uow = AsyncUnitOfWork(session_factory)
    create_batch = CreateBatch(
        uow=batch_uow,
        repo=SQLAlchemyBatchRepository(batch_uow),
        molecule_repo=SQLAlchemyMoleculeRepository(batch_uow),
        dispatcher=dispatcher,
    )

    # Separate UoW for the alias-capture step; AddBatchIdentifier manages its own txn.
    alias_uow = AsyncUnitOfWork(session_factory)
    add_batch_alias = AddBatchIdentifier(
        uow=alias_uow,
        repo=SQLAlchemyBatchRepository(alias_uow),
        dispatcher=dispatcher,
    )

    # Merge CDD batch ID into custom_fields for plate well resolution
    custom_fields = None
    if item.cdd_batch_id is not None:
        custom_fields = {"cdd_batch_id": item.cdd_batch_id}

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
        vendor_catalog_number=item.vendor_catalog_number,
        custom_fields=custom_fields,
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

    # Capture the CDD batch id as a BatchIdentifier so future imports + plate
    # lookups can resolve via find_by_external_identifier (mirror of how
    # MoleculeIdentifier captures CDD molecule id). The custom_fields write
    # above stays as the existing plate-well-resolution mechanism for now.
    if item.cdd_batch_id is not None:
        alias_result = await add_batch_alias(
            AddBatchIdentifierCommand(
                workspace_id=workspace_id,
                batch_id=batch.id,
                identifier=str(item.cdd_batch_id),
                identifier_type="cdd_batch_id",
                source="CDD import",
                registered_by=submitted_by,
            ),
            auth=None,  # Temporal activities run as system; auth=None bypasses guard
        )
        if isinstance(alias_result, Failure):
            # Conflict on re-import is expected (identifier already exists for this
            # batch); log and continue. Other failures are also non-fatal: the batch
            # exists, only the alias capture failed.
            logger.warning(
                "Capturing CDD batch alias for cdd_batch_id=%s failed: %s",
                item.cdd_batch_id,
                alias_result.failure(),
            )

    return batch.id, batch.batch_number.value, salt_matched
