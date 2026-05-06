"""Temporal worker bootstrap.

Run as::

    python -m chem_vault.infrastructure.temporal.worker
"""

from __future__ import annotations

import asyncio
import os

import structlog
from temporalio.worker import Worker

from chem_vault.infrastructure.di.container import create_container
from chem_vault.infrastructure.logging import configure_logging
from chem_vault.infrastructure.temporal.client import create_temporal_client
from chem_vault.infrastructure.temporal.settings import TemporalSettings

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

    from chem_vault.application.chemical_registration.merge_side_effect_registry import (
        MergeSideEffectRegistry,
    )
    from chem_vault.application.chemical_registration.protocols import (
        StructureProcessorProtocol,
    )
    from chem_vault.domain.shared.secret_provider import SecretProvider
    from chem_vault.infrastructure.cdd.client import CddVaultClient
    from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher
    from chem_vault.infrastructure.temporal.activities.bulk_tracking import BulkTrackingActivities
    from chem_vault.infrastructure.temporal.activities.cdd_fetch import CddFetchActivities
    from chem_vault.infrastructure.temporal.activities.file_parsing import FileParsingActivities
    from chem_vault.infrastructure.temporal.activities.plate_registration import (
        PlateRegistrationActivities,
    )
    from chem_vault.infrastructure.temporal.activities.registration import RegistrationActivities
    from chem_vault.infrastructure.temporal.workflows.bulk_registration import (
        BulkRegistrationWorkflow,
    )
    from chem_vault.infrastructure.temporal.workflows.cdd_plate_import import CddPlateImportWorkflow
    from chem_vault.infrastructure.temporal.workflows.cdd_vault_import import CddVaultImportWorkflow

    session_factory = container[async_sessionmaker]
    dispatcher = container[EventDispatcher]
    secret_provider = container[SecretProvider]
    cdd_client = container[CddVaultClient]
    structure_processor = container[StructureProcessorProtocol]
    side_effect_registry = container[MergeSideEffectRegistry]

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
        workflows=[CddVaultImportWorkflow, BulkRegistrationWorkflow, CddPlateImportWorkflow],
        activities=[
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
