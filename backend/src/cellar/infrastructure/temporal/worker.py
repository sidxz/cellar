"""Temporal worker bootstrap.

Run as::

    python -m cellar.infrastructure.temporal.worker
"""

from __future__ import annotations

import asyncio
import os

import structlog
from temporalio.worker import Worker

from cellar.infrastructure.di.container import create_container
from cellar.infrastructure.logging import configure_logging
from cellar.infrastructure.temporal.client import create_temporal_client
from cellar.infrastructure.temporal.settings import TemporalSettings

logger = structlog.get_logger(__name__)


async def run_worker() -> None:
    """Connect to Temporal, create DI container, and run the worker forever."""
    configure_logging(
        json_output=os.getenv("LOG_FORMAT", "json") == "json",
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )

    settings = TemporalSettings()
    logger.info(
        "Connecting to Temporal at %s (namespace=%s, queue=%s)",
        settings.address,
        settings.namespace,
        settings.task_queue,
    )

    client = await create_temporal_client(settings)

    # DI container gives access to DB, repos, event dispatcher — same as FastAPI.
    # Resolve concrete dependencies once and pass them into the activity classes
    # explicitly — activities never reach back into the container at task time.
    container = create_container()

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from cellar.application.chemical_registration.merge_side_effect_registry import (
        MergeSideEffectRegistry,
    )
    from cellar.application.chemical_registration.protocols import (
        StructureProcessorProtocol,
    )
    from cellar.domain.shared.secret_provider import SecretProvider
    from cellar.infrastructure.cdd.client import CddVaultClient
    from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
    from cellar.infrastructure.temporal.activities.bulk_tracking import BulkTrackingActivities
    from cellar.infrastructure.temporal.activities.cdd_fetch import CddFetchActivities
    from cellar.infrastructure.temporal.activities.file_parsing import FileParsingActivities
    from cellar.infrastructure.temporal.activities.plate_registration import (
        PlateRegistrationActivities,
    )
    from cellar.infrastructure.temporal.activities.registration import RegistrationActivities
    from cellar.infrastructure.temporal.workflows.bulk_registration import (
        BulkRegistrationWorkflow,
    )
    from cellar.infrastructure.temporal.workflows.cdd_plate_import import CddPlateImportWorkflow
    from cellar.infrastructure.temporal.workflows.cdd_vault_import import CddVaultImportWorkflow
    from cellar.infrastructure.temporal.workflows.export import ExportWorkflow

    from cellar.application.chemical_registration.molecule_reader import MoleculeReader
    from cellar.application.export.render_export import RenderExport
    from cellar.application.export.row_streams.search_results import SearchResultsRowStream
    from cellar.application.research_organization.execute_search import ExecuteSearch
    from cellar.application.screening.get_protocol import ListProtocols, ListProtocolsQuery
    from cellar.application.screening.molecule_activity_service import MoleculeActivityService
    from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
        SQLAlchemyDoseResponseCurveRepository,
    )
    from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
        SQLAlchemyProtocolRepository,
    )
    from cellar.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_repository import (
        SQLAlchemyReadoutDataRepository,
    )
    from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
        SQLAlchemyRunRepository,
    )
    from cellar.infrastructure.persistence.sqlalchemy.export.export_job_repository import (
        SqlAlchemyExportJobRepository,
    )
    from cellar.infrastructure.persistence.sqlalchemy.research_organization.saved_search_repository import (
        SQLAlchemySavedSearchRepository,
    )
    from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
    from cellar.infrastructure.storage.fsspec_client import FsspecStorageClient
    from cellar.infrastructure.temporal.activities.export import ExportActivities

    session_factory = container[async_sessionmaker]
    dispatcher = container[EventDispatcher]
    secret_provider = container[SecretProvider]
    cdd_client = container[CddVaultClient]
    structure_processor = container[StructureProcessorProtocol]
    side_effect_registry = container[MergeSideEffectRegistry]

    # --- Export activity ---
    # RenderExport is a dataclass-callable. It manages its own UoW lifecycle
    # (multiple `async with self.uow` blocks across the pipeline). The repo
    # must share the same UoW instance so it writes through the same session.
    # build_search_stream constructs fresh per-job instances (matching the
    # request-scoped DI pattern used in the API).
    _molecule_reader = container[MoleculeReader]
    _storage = container[FsspecStorageClient]
    _export_uow = AsyncUnitOfWork(session_factory)
    _export_repo = SqlAlchemyExportJobRepository(_export_uow)

    def _build_search_stream(job):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(session_factory)
        execute_search = ExecuteSearch(
            uow,
            _molecule_reader,
            SQLAlchemySavedSearchRepository(uow),
            activity_service=MoleculeActivityService(
                uow=uow,
                readout_repo=SQLAlchemyReadoutDataRepository(uow),
                curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
                protocol_repo=SQLAlchemyProtocolRepository(uow),
                run_repo=SQLAlchemyRunRepository(uow),
            ),
        )

        async def _protocols_reader(workspace_id):  # type: ignore[no-untyped-def]
            from returns.result import Success

            uow2 = AsyncUnitOfWork(session_factory)
            lp = ListProtocols(uow2, SQLAlchemyProtocolRepository(uow2))
            result = await lp(ListProtocolsQuery(workspace_id=workspace_id), auth=None)
            return result.unwrap().items if isinstance(result, Success) else []

        return SearchResultsRowStream(
            workspace_id=job.workspace_id,
            payload=job.query_snapshot,
            execute_search=execute_search,
            protocols_reader=_protocols_reader,
            requested_by=job.requested_by,
        )

    render_export = RenderExport(
        uow=_export_uow,
        repo=_export_repo,
        storage=_storage,
        build_search_stream=_build_search_stream,
    )
    export_activities = ExportActivities(render_export)

    tracking = BulkTrackingActivities(session_factory, dispatcher)
    cdd_fetch = CddFetchActivities(session_factory, secret_provider, cdd_client)
    file_parsing = FileParsingActivities()
    registration = RegistrationActivities(
        session_factory, dispatcher, structure_processor, side_effect_registry
    )
    plate_registration = PlateRegistrationActivities(session_factory, dispatcher)

    worker = Worker(
        client,
        task_queue=settings.task_queue,
        workflows=[CddVaultImportWorkflow, BulkRegistrationWorkflow, CddPlateImportWorkflow, ExportWorkflow],
        activities=[
            # Export
            export_activities.run_export,
            # BulkRegistration tracking
            tracking.create_bulk_registration,
            tracking.update_bulk_reg_progress,
            tracking.persist_chunk_items,
            tracking.complete_bulk_registration,
            # CDD molecule import tracking
            tracking.create_cdd_import,
            tracking.complete_discovery,
            tracking.update_cdd_import_progress,
            tracking.complete_cdd_import,
            tracking.fail_cdd_import,
            # CDD sync mapping
            tracking.record_sync_mappings,
            # CDD plate import tracking
            tracking.create_cdd_plate_import,
            tracking.complete_plate_discovery,
            tracking.update_cdd_plate_import_progress,
            tracking.complete_cdd_plate_import,
            tracking.fail_cdd_plate_import,
            tracking.record_plate_sync_mappings,
            # CDD fetch (async export model)
            cdd_fetch.start_molecule_export,
            cdd_fetch.poll_molecule_export,
            cdd_fetch.load_export_chunk,
            cdd_fetch.get_sync_watermark,
            # CDD plate fetch
            cdd_fetch.start_plate_export,
            cdd_fetch.poll_plate_export,
            cdd_fetch.load_plate_chunk,
            # File parsing
            file_parsing.parse_file,
            # Registration (shared)
            registration.process_chunk,
            # Plate registration
            plate_registration.process_plate_chunk,
        ],
    )

    logger.info("Temporal worker started on queue %r", settings.task_queue)
    await worker.run()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
