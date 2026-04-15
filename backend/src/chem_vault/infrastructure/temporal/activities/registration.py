"""Registration activities — process a chunk of molecules through the registration pipeline.

Reuses existing RegisterMolecule + CreateBatch use cases. Each activity
invocation resolves fresh UoW + repos from the DI container.
"""

from __future__ import annotations

import logging
import uuid

from lagom import Container
from returns.result import Failure
from sqlalchemy.ext.asyncio import async_sessionmaker
from temporalio import activity

from chem_vault.application.chemical_registration.protocols import StructureProcessorProtocol
from chem_vault.application.chemical_registration.register_molecule import (
    ExternalId,
    RegisterMolecule,
    RegisterMoleculeCommand,
    RegistrationOutcome,
)
from chem_vault.application.inventory.create_batch import CreateBatch, CreateBatchCommand
from chem_vault.application.inventory.salt_matcher import SaltMatcher, compute_formula_weight
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.salt_entry_repository import (
    SQLAlchemySaltEntryRepository,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from chem_vault.infrastructure.temporal.activities.dtos import (
    ChunkInput,
    ChunkItem,
    ChunkItemResult,
    ChunkOutput,
)

logger = logging.getLogger(__name__)


class RegistrationActivities:
    """Temporal activities for molecule registration."""

    def __init__(self, container: Container) -> None:
        self._container = container

    @activity.defn
    async def process_chunk(self, input: ChunkInput) -> ChunkOutput:
        """Process a chunk of molecules sequentially through registration + batch creation."""
        c = self._container
        session_factory = c[async_sessionmaker]
        dispatcher = c[EventDispatcher]
        structure_processor = c[StructureProcessorProtocol]

        # RegisterMolecule and CreateBatch each manage their own UoW lifecycle
        # internally (async with self._uow:), so they need separate UoW instances
        # to avoid one closing the session that the other still needs.
        reg_uow = AsyncUnitOfWork(session_factory)
        register_uc = RegisterMolecule(
            uow=reg_uow,
            repo=SQLAlchemyMoleculeRepository(reg_uow),
            dispatcher=dispatcher,
            structure_processor=structure_processor,
        )

        ws_id = uuid.UUID(input.workspace_id)
        org_id = uuid.UUID(input.originating_org_id)
        submitted_by = uuid.UUID(input.submitted_by)

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
            if outcome.is_new:
                output.registered += 1
            else:
                output.duplicate += 1

            # Create batch — uses a fresh UoW since RegisterMolecule already closed its session
            batch_id, batch_number, salt_matched = await _create_batch(
                item=item,
                reg_outcome=outcome,
                workspace_id=ws_id,
                submitted_by=submitted_by,
                session_factory=session_factory,
                dispatcher=dispatcher,
            )

            output.results.append(
                ChunkItemResult(
                    row_index=item.row_index,
                    success=True,
                    is_new=outcome.is_new,
                    molecule_id=str(outcome.molecule.id),
                    batch_id=str(batch_id) if batch_id else None,
                    batch_number=batch_number,
                    salt_matched=salt_matched,
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
    return batch.id, batch.batch_number.value, salt_matched
