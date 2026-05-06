"""Bulk tracking activities — manage import aggregate state in the DB.

These are activities (not inline workflow code) because they have DB side effects.
Covers both BulkRegistration (file import) and CddMoleculeImport aggregates.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker
from temporalio import activity

from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher

from chem_vault.domain.chemical_registration.bulk_registration import BulkRegistration
from chem_vault.domain.chemical_registration.cdd_molecule_import import CddMoleculeImport
from chem_vault.domain.chemical_registration.enums import (
    BulkRegistrationFileFormat,
    BulkRegistrationItemAction,
    CddImportMode,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from chem_vault.domain.inventory.cdd_plate_import import CddPlateImport
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.bulk_registration_repository import (
    SQLAlchemyBulkRegistrationRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.cdd_molecule_import_repository import (
    SQLAlchemyCddMoleculeImportRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.cdd_molecule_sync_repository import (
    CddMoleculeSyncRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.cdd_plate_import_repository import (
    SQLAlchemyCddPlateImportRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.cdd_plate_sync_repository import (
    CddPlateSyncRepository,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from chem_vault.infrastructure.temporal.activities.dtos import (
    CompleteBulkRegInput,
    CompleteCddImportInput,
    CompleteCddPlateImportInput,
    CompleteDiscoveryInput,
    CreateBulkRegInput,
    CreateCddImportInput,
    CreateCddPlateImportInput,
    FailCddImportInput,
    FailCddPlateImportInput,
    PersistChunkItemsInput,
    RecordPlateSyncMappingsInput,
    RecordSyncMappingsInput,
    UpdateBulkRegProgressInput,
    UpdateCddImportProgressInput,
    UpdateCddPlateImportProgressInput,
)


class BulkTrackingActivities:
    """Temporal activities for managing import tracking aggregates."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        dispatcher: EventDispatcher,
    ) -> None:
        self._session_factory = session_factory
        self._dispatcher = dispatcher

    def _make_cdd_deps(self):
        uow = AsyncUnitOfWork(self._session_factory)
        repo = SQLAlchemyCddMoleculeImportRepository(uow)
        return uow, repo, self._dispatcher

    def _make_bulk_reg_deps(self):
        uow = AsyncUnitOfWork(self._session_factory)
        repo = SQLAlchemyBulkRegistrationRepository(uow)
        return uow, repo, self._dispatcher

    # ------------------------------------------------------------------
    # BulkRegistration (file import) tracking
    # ------------------------------------------------------------------

    @activity.defn
    async def create_bulk_registration(self, input: CreateBulkRegInput) -> str:
        """Create a BulkRegistration aggregate and return its ID."""
        uow, repo, dispatcher = self._make_bulk_reg_deps()
        async with uow:
            bulk_reg = BulkRegistration.create(
                workspace_id=uuid.UUID(input.workspace_id),
                source_file=input.source_file,
                file_format=BulkRegistrationFileFormat(input.file_format),
                submitted_by=uuid.UUID(input.submitted_by),
                total_count=input.total_count,
                workflow_id=input.workflow_id,
            )
            bulk_reg.start_processing()
            await repo.save(bulk_reg)
            events = await uow.commit()
            await dispatcher.dispatch_all(events)
        return str(bulk_reg.id)

    @activity.defn
    async def update_bulk_reg_progress(self, input: UpdateBulkRegProgressInput) -> None:
        """Update BulkRegistration counters after a chunk.

        Legacy entry point kept for backward compatibility — for new flows the
        workflow should call ``persist_chunk_items`` instead, which records both
        per-row provenance AND counters in one transaction.
        """
        uow, repo, _ = self._make_bulk_reg_deps()
        ws_id = uuid.UUID(input.workspace_id)
        async with uow:
            bulk_reg = await repo.find_by_id_in_workspace(ws_id, uuid.UUID(input.bulk_reg_id))
            if bulk_reg is None:
                raise ValueError(f"BulkRegistration {input.bulk_reg_id} not found")
            for _ in range(input.registered):
                bulk_reg.record_registered()
            for _ in range(input.duplicate):
                bulk_reg.record_duplicate()
            for _ in range(input.error):
                bulk_reg.record_error()
            await repo.save(bulk_reg)
            await uow.commit()

    @activity.defn
    async def persist_chunk_items(self, input: PersistChunkItemsInput) -> None:
        """Persist a chunk's per-row outcomes and roll up the aggregate counters.

        Replaces ``update_bulk_reg_progress`` for the bulk-registration import
        flow. Each ChunkItemResult dict produces one BulkRegistrationItem and
        increments the corresponding aggregate counter.

        Idempotent: the underlying ``insert_items`` uses
        ``ON CONFLICT (bulk_registration_id, row_index) DO NOTHING`` so a
        retried activity won't double-write. Counters are NOT idempotent on
        retry — Temporal's at-most-once activity semantics rely on
        successful completion of the activity setting last_completed_result;
        a redelivery before the activity commit is the only retry path, and
        commit happens atomically with the row inserts.
        """
        uow, repo, _ = self._make_bulk_reg_deps()
        ws_id = uuid.UUID(input.workspace_id)
        async with uow:
            bulk_reg = await repo.find_by_id_in_workspace(
                ws_id, uuid.UUID(input.bulk_reg_id)
            )
            if bulk_reg is None:
                raise ValueError(f"BulkRegistration {input.bulk_reg_id} not found")

            # Resolve molecule names for display once per molecule.
            mol_repo = SQLAlchemyMoleculeRepository(uow)
            mol_ids = {
                uuid.UUID(it["molecule_id"])
                for it in input.items
                if it.get("molecule_id")
            }
            molecules = (
                await mol_repo.find_by_ids(ws_id, list(mol_ids)) if mol_ids else []
            )
            mol_lookup: dict[uuid.UUID, tuple[str, str]] = {
                m.id: (m.name, m.registration_number.value) for m in molecules
            }

            for raw in input.items:
                row_index = int(raw["row_index"])
                success = bool(raw.get("success", False))
                action_str = raw.get("action") or ""
                err = raw.get("error")

                if not success:
                    action = BulkRegistrationItemAction.ERROR
                else:
                    try:
                        action = BulkRegistrationItemAction(action_str)
                    except ValueError:
                        action = BulkRegistrationItemAction.REGISTERED

                molecule_id_str = raw.get("molecule_id")
                molecule_id = (
                    uuid.UUID(molecule_id_str) if molecule_id_str else None
                )
                mol_name: str | None = None
                reg_number: str | None = None
                if molecule_id and molecule_id in mol_lookup:
                    mol_name, reg_number = mol_lookup[molecule_id]

                batch_id_str = raw.get("batch_id")
                batch_id = uuid.UUID(batch_id_str) if batch_id_str else None

                bulk_reg.record_item(
                    row_index=row_index,
                    action=action,
                    molecule_id=molecule_id,
                    molecule_name=mol_name,
                    registration_number=reg_number,
                    batch_id=batch_id,
                    batch_number=raw.get("batch_number"),
                    error=err,
                )

            await repo.save(bulk_reg)
            await uow.commit()

    @activity.defn
    async def complete_bulk_registration(self, input: CompleteBulkRegInput) -> None:
        """Complete the BulkRegistration."""
        uow, repo, dispatcher = self._make_bulk_reg_deps()
        ws_id = uuid.UUID(input.workspace_id)
        async with uow:
            bulk_reg = await repo.find_by_id_in_workspace(ws_id, uuid.UUID(input.bulk_reg_id))
            if bulk_reg is None:
                raise ValueError(f"BulkRegistration {input.bulk_reg_id} not found")
            bulk_reg.complete()
            await repo.save(bulk_reg)
            events = await uow.commit()
            await dispatcher.dispatch_all(events)

    # ------------------------------------------------------------------
    # CDD molecule import tracking
    # ------------------------------------------------------------------

    @activity.defn
    async def create_cdd_import(self, input: CreateCddImportInput) -> str:
        """Create a CddMoleculeImport aggregate and return its ID."""
        uow, repo, dispatcher = self._make_cdd_deps()
        async with uow:
            imp = CddMoleculeImport.create(
                workspace_id=uuid.UUID(input.workspace_id),
                cdd_vault_id=input.cdd_vault_id,
                import_mode=CddImportMode(input.import_mode),
                originating_org_id=uuid.UUID(input.originating_org_id),
                submitted_by=uuid.UUID(input.submitted_by),
                workflow_id=input.workflow_id,
                filter_criteria=input.filter_criteria,
            )
            imp.start_discovery()
            await repo.save(imp)
            events = await uow.commit()
            await dispatcher.dispatch_all(events)
        return str(imp.id)

    @activity.defn
    async def complete_discovery(self, input: CompleteDiscoveryInput) -> None:
        """Transition DISCOVERING -> PROCESSING with total_count."""
        uow, repo, dispatcher = self._make_cdd_deps()
        ws_id = uuid.UUID(input.workspace_id)
        async with uow:
            imp = await repo.find_by_id_in_workspace(ws_id, uuid.UUID(input.import_id))
            if imp is None:
                raise ValueError(f"CddMoleculeImport {input.import_id} not found")
            imp.complete_discovery(input.total_count)
            await repo.save(imp)
            events = await uow.commit()
            await dispatcher.dispatch_all(events)

    @activity.defn
    async def update_cdd_import_progress(self, input: UpdateCddImportProgressInput) -> None:
        """Update counters after a chunk completes."""
        uow, repo, _ = self._make_cdd_deps()
        ws_id = uuid.UUID(input.workspace_id)
        async with uow:
            imp = await repo.find_by_id_in_workspace(ws_id, uuid.UUID(input.import_id))
            if imp is None:
                raise ValueError(f"CddMoleculeImport {input.import_id} not found")
            if input.registered:
                imp.record_registered(input.registered)
            if input.duplicate:
                imp.record_duplicate(input.duplicate)
            if input.error:
                imp.record_error(input.error)
            if input.skipped:
                imp.record_skipped(input.skipped)
            imp.update_offset(input.last_processed_offset)
            await repo.save(imp)
            await uow.commit()

    @activity.defn
    async def complete_cdd_import(self, input: CompleteCddImportInput) -> None:
        """Complete the import (PROCESSING -> COMPLETED/COMPLETED_WITH_ERRORS)."""
        uow, repo, dispatcher = self._make_cdd_deps()
        ws_id = uuid.UUID(input.workspace_id)
        async with uow:
            imp = await repo.find_by_id_in_workspace(ws_id, uuid.UUID(input.import_id))
            if imp is None:
                raise ValueError(f"CddMoleculeImport {input.import_id} not found")
            imp.complete()
            await repo.save(imp)
            events = await uow.commit()
            await dispatcher.dispatch_all(events)

    @activity.defn
    async def fail_cdd_import(self, input: FailCddImportInput) -> None:
        """Fail the import (DISCOVERING/PROCESSING -> FAILED)."""
        uow, repo, dispatcher = self._make_cdd_deps()
        ws_id = uuid.UUID(input.workspace_id)
        async with uow:
            imp = await repo.find_by_id_in_workspace(ws_id, uuid.UUID(input.import_id))
            if imp is None:
                raise ValueError(f"CddMoleculeImport {input.import_id} not found")
            imp.fail(input.reason)
            await repo.save(imp)
            events = await uow.commit()
            await dispatcher.dispatch_all(events)

    # ------------------------------------------------------------------
    # CDD plate import tracking
    # ------------------------------------------------------------------

    def _make_plate_import_deps(self):
        uow = AsyncUnitOfWork(self._session_factory)
        repo = SQLAlchemyCddPlateImportRepository(uow)
        return uow, repo, self._dispatcher

    @activity.defn
    async def create_cdd_plate_import(self, input: CreateCddPlateImportInput) -> str:
        """Create a CddPlateImport aggregate and return its ID."""
        uow, repo, dispatcher = self._make_plate_import_deps()
        async with uow:
            imp = CddPlateImport.create(
                workspace_id=uuid.UUID(input.workspace_id),
                cdd_vault_id=input.cdd_vault_id,
                submitted_by=uuid.UUID(input.submitted_by),
                workflow_id=input.workflow_id,
            )
            imp.start_discovery()
            await repo.save(imp)
            events = await uow.commit()
            await dispatcher.dispatch_all(events)
        return str(imp.id)

    @activity.defn
    async def complete_plate_discovery(self, input: CompleteDiscoveryInput) -> None:
        """Transition plate import DISCOVERING -> PROCESSING with total_count."""
        uow, repo, dispatcher = self._make_plate_import_deps()
        ws_id = uuid.UUID(input.workspace_id)
        async with uow:
            imp = await repo.find_by_id_in_workspace(ws_id, uuid.UUID(input.import_id))
            if imp is None:
                raise ValueError(f"CddPlateImport {input.import_id} not found")
            imp.complete_discovery(input.total_count)
            await repo.save(imp)
            events = await uow.commit()
            await dispatcher.dispatch_all(events)

    @activity.defn
    async def update_cdd_plate_import_progress(self, input: UpdateCddPlateImportProgressInput) -> None:
        """Update plate import counters after a chunk completes."""
        uow, repo, _ = self._make_plate_import_deps()
        ws_id = uuid.UUID(input.workspace_id)
        async with uow:
            imp = await repo.find_by_id_in_workspace(ws_id, uuid.UUID(input.import_id))
            if imp is None:
                raise ValueError(f"CddPlateImport {input.import_id} not found")
            if input.plates_registered:
                imp.record_registered(input.plates_registered)
            if input.plates_duplicate:
                imp.record_duplicate(input.plates_duplicate)
            if input.plates_error:
                imp.record_error(input.plates_error)
            if input.wells_mapped or input.wells_unresolved:
                imp.record_wells(input.wells_mapped, input.wells_unresolved)
            imp.update_offset(input.last_processed_offset)
            await repo.save(imp)
            await uow.commit()

    @activity.defn
    async def complete_cdd_plate_import(self, input: CompleteCddPlateImportInput) -> None:
        """Complete plate import (PROCESSING -> COMPLETED/COMPLETED_WITH_ERRORS)."""
        uow, repo, dispatcher = self._make_plate_import_deps()
        ws_id = uuid.UUID(input.workspace_id)
        async with uow:
            imp = await repo.find_by_id_in_workspace(ws_id, uuid.UUID(input.import_id))
            if imp is None:
                raise ValueError(f"CddPlateImport {input.import_id} not found")
            imp.complete()
            await repo.save(imp)
            events = await uow.commit()
            await dispatcher.dispatch_all(events)

    @activity.defn
    async def fail_cdd_plate_import(self, input: FailCddPlateImportInput) -> None:
        """Fail plate import (DISCOVERING/PROCESSING -> FAILED)."""
        uow, repo, dispatcher = self._make_plate_import_deps()
        ws_id = uuid.UUID(input.workspace_id)
        async with uow:
            imp = await repo.find_by_id_in_workspace(ws_id, uuid.UUID(input.import_id))
            if imp is None:
                raise ValueError(f"CddPlateImport {input.import_id} not found")
            imp.fail(input.reason)
            await repo.save(imp)
            events = await uow.commit()
            await dispatcher.dispatch_all(events)

    @activity.defn
    async def record_plate_sync_mappings(self, input: RecordPlateSyncMappingsInput) -> None:
        """Record CDD->internal plate mappings after successful registration."""
        uow = AsyncUnitOfWork(self._session_factory)
        sync_repo = CddPlateSyncRepository(uow)
        async with uow:
            mappings = [
                (m["cdd_plate_id"], uuid.UUID(m["plate_id"]))
                for m in input.mappings
                if m.get("cdd_plate_id") and m.get("plate_id")
            ]
            if mappings:
                await sync_repo.bulk_upsert(
                    uuid.UUID(input.workspace_id), input.cdd_vault_id, mappings
                )
            await uow.commit()

    # ------------------------------------------------------------------
    # CDD sync mapping recording
    # ------------------------------------------------------------------

    @activity.defn
    async def record_sync_mappings(self, input: RecordSyncMappingsInput) -> None:
        """Record CDD→internal molecule mappings after successful registration."""
        uow = AsyncUnitOfWork(self._session_factory)
        sync_repo = CddMoleculeSyncRepository(uow)
        async with uow:
            mappings = [
                (m["cdd_molecule_id"], uuid.UUID(m["molecule_id"]), m.get("cdd_modified_at"))
                for m in input.mappings
                if m.get("cdd_molecule_id") and m.get("molecule_id")
            ]
            if mappings:
                await sync_repo.bulk_upsert(
                    uuid.UUID(input.workspace_id), input.cdd_vault_id, mappings
                )
            await uow.commit()
