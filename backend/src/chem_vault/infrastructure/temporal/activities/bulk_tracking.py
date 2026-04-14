"""Bulk tracking activities — manage import aggregate state in the DB.

These are activities (not inline workflow code) because they have DB side effects.
Covers both BulkRegistration (file import) and CddMoleculeImport aggregates.
"""

from __future__ import annotations

import uuid

from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker
from temporalio import activity

from chem_vault.domain.chemical_registration.bulk_registration import BulkRegistration
from chem_vault.domain.chemical_registration.cdd_molecule_import import CddMoleculeImport
from chem_vault.domain.chemical_registration.enums import (
    BulkRegistrationFileFormat,
    CddImportMode,
)
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.bulk_registration_repository import (
    SQLAlchemyBulkRegistrationRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.cdd_molecule_import_repository import (
    SQLAlchemyCddMoleculeImportRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.cdd_molecule_sync_repository import (
    CddMoleculeSyncRepository,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from chem_vault.infrastructure.temporal.activities.dtos import (
    CompleteBulkRegInput,
    CompleteCddImportInput,
    CompleteDiscoveryInput,
    CreateBulkRegInput,
    CreateCddImportInput,
    FailCddImportInput,
    RecordSyncMappingsInput,
    UpdateBulkRegProgressInput,
    UpdateCddImportProgressInput,
)


class BulkTrackingActivities:
    """Temporal activities for managing import tracking aggregates."""

    def __init__(self, container: Container) -> None:
        self._container = container

    def _make_cdd_deps(self):
        session_factory = self._container[async_sessionmaker]
        uow = AsyncUnitOfWork(session_factory)
        repo = SQLAlchemyCddMoleculeImportRepository(uow)
        dispatcher = self._container[EventDispatcher]
        return uow, repo, dispatcher

    def _make_bulk_reg_deps(self):
        session_factory = self._container[async_sessionmaker]
        uow = AsyncUnitOfWork(session_factory)
        repo = SQLAlchemyBulkRegistrationRepository(uow)
        dispatcher = self._container[EventDispatcher]
        return uow, repo, dispatcher

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
            )
            bulk_reg.start_processing()
            await repo.save(bulk_reg)
            events = await uow.commit()
            await dispatcher.dispatch_all(events)
        return str(bulk_reg.id)

    @activity.defn
    async def update_bulk_reg_progress(self, input: UpdateBulkRegProgressInput) -> None:
        """Update BulkRegistration counters after a chunk."""
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
    # CDD sync mapping recording
    # ------------------------------------------------------------------

    @activity.defn
    async def record_sync_mappings(self, input: RecordSyncMappingsInput) -> None:
        """Record CDD→internal molecule mappings after successful registration."""
        session_factory = self._container[async_sessionmaker]
        uow = AsyncUnitOfWork(session_factory)
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
