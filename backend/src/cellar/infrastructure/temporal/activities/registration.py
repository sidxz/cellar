"""Registration activities — process a chunk of molecules through the registration pipeline.

Reuses existing RegisterMolecule + CreateBatch use cases. Each activity
invocation resolves fresh UoW + repos from the DI container.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import structlog
from returns.result import Failure
from sqlalchemy.ext.asyncio import async_sessionmaker
from temporalio import activity

from cellar.application.chemical_registration.disclosure_service import DisclosureService
from cellar.application.chemical_registration.merge_service import MergeService
from cellar.application.chemical_registration.merge_side_effect_registry import (
    MergeSideEffectRegistry,
)
from cellar.application.chemical_registration.protocols import StructureProcessorProtocol
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
from cellar.application.shared.actor_context import set_current_actor
from cellar.domain.chemical_registration.enums import RegistrationAction
from cellar.domain.shared.errors import (
    ConcurrencyConflictError,
    DomainError,
    ServiceUnavailableError,
)
from cellar.domain.workspace_config.repository import WorkspaceSettingsRepository
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.disclosure_request_repository import (  # noqa: E501
    SQLAlchemyDisclosureRequestRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.merge_event_repository import (  # noqa: E501
    SQLAlchemyMergeEventRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (  # noqa: E501
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.salt_entry_repository import (
    SQLAlchemySaltEntryRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.workspace_settings_repository import (  # noqa: E501
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

# A row the domain refuses is that row's error and the chunk goes on. These pass,
# so they fail the chunk and Temporal retries it (done rows then match, not double).
_PASSING = (ServiceUnavailableError, ConcurrencyConflictError)


def _uuid(value: str | None) -> uuid.UUID | None:
    return uuid.UUID(value) if value else None


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
        # Audit actor for every event this activity dispatches (own asyncio task,
        # so the contextvar cannot leak into other activities).
        set_current_actor(uuid.UUID(input.submitted_by))
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
        submitted_by_org_id = _uuid(input.submitted_by_org_id)
        disclosed_by = _uuid(input.disclosed_by)
        disclosed_by_org_id = _uuid(input.disclosed_by_org_id)

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
        # A CDD molecule is one row per batch, all with its row_index: what is said about
        # the compound goes on its first row only, so a report counts it once.
        seen_rows: set[int] = set()

        for item in input.items:
            first_row = item.row_index not in seen_rows
            seen_rows.add(item.row_index)
            if item.error:
                # The parser could not read this row; it registers nothing.
                output.error += 1
                output.results.append(
                    ChunkItemResult(row_index=item.row_index, success=False, error=item.error)
                )
                continue

            has_explicit_name = bool(item.name)
            cmd = RegisterMoleculeCommand(
                workspace_id=ws_id,
                name=item.name or f"Compound-{item.row_index + 1}",
                smiles=item.smiles,
                molecule_type=item.molecule_type,
                external_ids=external_ids(item.external_ids),
                originating_org_id=org_id,
                registered_by=submitted_by,
                registered_by_org_id=submitted_by_org_id,
                disclosed_by=disclosed_by,
                disclosed_by_org_id=disclosed_by_org_id,
                promote_name_as_identifier=has_explicit_name,
                project_ids=[uuid.UUID(p) for p in input.project_ids],
            )

            try:
                result = await register_uc(cmd)
            except _PASSING:
                raise
            except DomainError as exc:  # raised, not returned: e.g. a constraint at commit
                logger.warning(
                    "registration.row_refused", row_index=item.row_index, error=str(exc)
                )
                result = Failure(exc)

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
            batch_problem: str | None = None
            batch_warnings: tuple[str, ...] = ()
            batch_action: str | None = None
            ids_added = 0
            if action not in (RegistrationAction.MERGE_CANDIDATE, RegistrationAction.CONFLICT):
                create_batch_now = should_create_batch(
                    is_new_molecule=outcome.is_new,
                    # workflow-level decision already collapsed into effective_policy_default
                    override=None,
                    workspace_default=effective_policy_default,
                )
                try:
                    if item.batch_problem:
                        batch_problem = item.batch_problem
                    elif item.batch_ids:
                        (
                            batch_id,
                            batch_number,
                            salt_matched,
                            batch_problem,
                            batch_warnings,
                            batch_action,
                            ids_added,
                        ) = await _apply_row_batch(
                            item=item,
                            reg_outcome=outcome,
                            workspace_id=ws_id,
                            submitted_by=submitted_by,
                            session_factory=session_factory,
                            dispatcher=dispatcher,
                        )
                    elif create_batch_now:
                        batch_id, batch_number, salt_matched = await _create_batch(
                            item=item,
                            reg_outcome=outcome,
                            workspace_id=ws_id,
                            submitted_by=submitted_by,
                            session_factory=session_factory,
                            dispatcher=dispatcher,
                        )
                        batch_action = "created" if batch_id else None
                    else:
                        batch_skipped = True
                except _PASSING:
                    raise
                except DomainError as exc:  # the compound stays registered
                    logger.warning(
                        "registration.batch_refused", row_index=item.row_index, error=str(exc)
                    )
                    batch_problem = str(exc)

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
                    # The compound is registered; this says why its batch is not.
                    error=f"Compound registered, batch not created: {batch_problem}"
                    if batch_problem
                    else None,
                    cdd_molecule_id=item.cdd_molecule_id,
                    cdd_modified_at=item.cdd_modified_at,
                    warnings=[
                        *item.warnings,
                        *((*outcome.notes, *outcome.skipped_ids) if first_row else ()),
                        *batch_warnings,
                    ],
                    batch_action=batch_action,
                    ids_added=outcome.ids_added + ids_added,
                    # a note (a structure left as it was) is a line, not a skipped value
                    values_skipped=len(item.warnings)
                    + (len(outcome.skipped_ids) if first_row else 0)
                    + len(batch_warnings),
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

        output.report = chunk_report(
            output, {i.row_index: i.name or f"Compound-{i.row_index + 1}" for i in input.items}
        )
        return output


def chunk_report(output: ChunkOutput, names: dict[int, str]) -> dict:
    """The run-report delta for one chunk (see ``CddMoleculeImport.record_report``).

    A problem is a row that failed, a compound whose batch could not be made, or a
    conflict; a skipped value is a warning that a value was not stored. Both, and notes
    (a structure the vault id left as it was), get a line. A compound that failed is
    one problem, not one per batch row.
    """
    lines: list[str] = []
    problems = 0
    failed: set[int] = set()
    for r in output.results:
        name = names.get(r.row_index, f"row {r.row_index + 1}")
        problem = r.error or (r.conflict_reason if r.action == "conflict" else None)
        if not r.success:
            if r.row_index in failed:
                continue
            failed.add(r.row_index)
        if problem:
            problems += 1
            lines.append(f"{name}: {problem}")
        lines.extend(f"{name}: {w}" for w in r.warnings)
    return {
        "compounds_added": output.mol_registered,
        "compounds_matched": output.mol_duplicate,
        "batches_created": sum(r.batch_action == "created" for r in output.results),
        "batches_matched": sum(r.batch_action == "existing" for r in output.results),
        "ids_added": sum(r.ids_added for r in output.results),
        "values_skipped": sum(r.values_skipped for r in output.results),
        "problems": problems,
        "problem_lines": lines,
    }


async def _create_batch(
    *,
    item: ChunkItem,
    reg_outcome: RegistrationOutcome,
    workspace_id: uuid.UUID,
    submitted_by: uuid.UUID,
    session_factory: async_sessionmaker,
    dispatcher,
) -> tuple[uuid.UUID | None, str | None, bool]:
    """A row without batch IDs: resolve salt and create a batch (the duplicate policy
    already said yes). Uses a fresh UoW for each call."""
    batch_cmd, salt_matched, create_batch = await _batch_command(
        item=item,
        reg_outcome=reg_outcome,
        workspace_id=workspace_id,
        submitted_by=submitted_by,
        session_factory=session_factory,
        dispatcher=dispatcher,
    )
    batch_result = await create_batch(batch_cmd)
    if isinstance(batch_result, Failure):
        logger.warning(
            "registration.batch_create_failed",
            molecule_id=str(reg_outcome.molecule.id),
            row_index=item.row_index,
            error=str(batch_result.failure()),
        )
        return None, None, False
    batch = batch_result.unwrap().batch
    return batch.id, batch.batch_number.value, salt_matched


async def _apply_row_batch(
    *,
    item: ChunkItem,
    reg_outcome: RegistrationOutcome,
    workspace_id: uuid.UUID,
    submitted_by: uuid.UUID,
    session_factory: async_sessionmaker,
    dispatcher,
) -> tuple[uuid.UUID | None, str | None, bool, str | None, tuple[str, ...], str | None, int]:
    """The row names its batch (``item.batch_ids``): find or create exactly that
    batch (``row_batch.ApplyRowBatch``). Returns ``(batch_id, batch_number,
    salt_matched, problem, skipped-ID warnings, batch action, IDs added)``; on a
    problem the compound stays registered."""
    batch_cmd, salt_matched, create_batch = await _batch_command(
        item=item,
        reg_outcome=reg_outcome,
        workspace_id=workspace_id,
        submitted_by=submitted_by,
        session_factory=session_factory,
        dispatcher=dispatcher,
    )
    row_uow = AsyncUnitOfWork(session_factory)
    apply = ApplyRowBatch(
        uow=row_uow,
        batch_repo=SQLAlchemyBatchRepository(row_uow),
        create_batch=create_batch,
        dispatcher=dispatcher,
    )
    result = await apply(
        ApplyRowBatchCommand(
            workspace_id=workspace_id,
            molecule_id=reg_outcome.molecule.id,
            batch_ids=row_batch_ids(item.batch_ids),
            create=batch_cmd,
            actor=submitted_by,
        )
    )
    if isinstance(result, Failure):
        logger.warning(
            "registration.row_batch_failed",
            molecule_id=str(reg_outcome.molecule.id),
            row_index=item.row_index,
            error=str(result.failure()),
        )
        return None, None, False, str(result.failure()), (), None, 0
    r = result.unwrap()
    if r.action == "problem":
        return None, None, False, r.problem, (), None, 0
    created = r.action == "created"
    return (
        r.batch_id,
        r.batch_number,
        salt_matched and created,
        None,
        r.skipped,
        r.action,
        r.ids_added,
    )


async def _batch_command(
    *,
    item: ChunkItem,
    reg_outcome: RegistrationOutcome,
    workspace_id: uuid.UUID,
    submitted_by: uuid.UUID,
    session_factory: async_sessionmaker,
    dispatcher,
) -> tuple[CreateBatchCommand, bool, CreateBatch]:
    """Resolve salt; build the batch command and the use case that runs it."""
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

    # Batch creation uses its own UoW (CreateBatch manages it internally).
    # The batch repo is shared with SyncBatchIdentifierMirrors so its
    # in-transaction workspace-uniqueness lookups run on the same session
    # (matches the DI wiring in di/_inventory.py). Passing sync fans the
    # molecule's identifiers out onto the new batch as `<synonym>-NNN` aliases;
    # workspace_settings_repo makes the batch honor the workspace's configured
    # sequence width. custom_field_validator is intentionally omitted — the
    # activity writes an internal cdd_batch_id custom field that is not a
    # workspace-defined custom field and would be rejected by the validator.
    batch_uow = AsyncUnitOfWork(session_factory)
    batch_repo = SQLAlchemyBatchRepository(batch_uow)
    create_batch = CreateBatch(
        uow=batch_uow,
        repo=batch_repo,
        molecule_repo=SQLAlchemyMoleculeRepository(batch_uow),
        dispatcher=dispatcher,
        workspace_settings_repo=SQLAlchemyWorkspaceSettingsRepository(batch_uow),
        sync=SyncBatchIdentifierMirrors(batch_repo),
    )

    # The CDD vault batch id also goes into custom_fields: plate wells resolve by it.
    # (It is a batch ID too — ``item.batch_ids`` — which ApplyRowBatch stores.)
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
        custom_fields=custom_fields,
    )

    return batch_cmd, salt_matched, create_batch
