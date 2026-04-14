"""Temporal worker bootstrap.

Run as::

    python -m chem_vault.infrastructure.temporal.worker
"""

from __future__ import annotations

import asyncio
import logging
import os

from temporalio.worker import Worker

from chem_vault.infrastructure.di.container import create_container
from chem_vault.infrastructure.logging import configure_logging
from chem_vault.infrastructure.temporal.client import create_temporal_client
from chem_vault.infrastructure.temporal.settings import TemporalSettings

logger = logging.getLogger(__name__)


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

    # DI container gives access to DB, repos, event dispatcher — same as FastAPI
    container = create_container()

    # Instantiate activity classes with the container
    from chem_vault.infrastructure.temporal.activities.bulk_tracking import BulkTrackingActivities
    from chem_vault.infrastructure.temporal.activities.cdd_fetch import CddFetchActivities
    from chem_vault.infrastructure.temporal.activities.file_parsing import FileParsingActivities
    from chem_vault.infrastructure.temporal.activities.registration import RegistrationActivities
    from chem_vault.infrastructure.temporal.workflows.bulk_registration import BulkRegistrationWorkflow
    from chem_vault.infrastructure.temporal.workflows.cdd_vault_import import CddVaultImportWorkflow

    tracking = BulkTrackingActivities(container)
    cdd_fetch = CddFetchActivities(container)
    file_parsing = FileParsingActivities()
    registration = RegistrationActivities(container)

    worker = Worker(
        client,
        task_queue=settings.task_queue,
        workflows=[CddVaultImportWorkflow, BulkRegistrationWorkflow],
        activities=[
            # BulkRegistration tracking
            tracking.create_bulk_registration,
            tracking.update_bulk_reg_progress,
            tracking.complete_bulk_registration,
            # CDD import tracking
            tracking.create_cdd_import,
            tracking.complete_discovery,
            tracking.update_cdd_import_progress,
            tracking.complete_cdd_import,
            tracking.fail_cdd_import,
            # CDD sync mapping
            tracking.record_sync_mappings,
            # CDD fetch (async export model)
            cdd_fetch.start_molecule_export,
            cdd_fetch.poll_molecule_export,
            cdd_fetch.load_export_chunk,
            cdd_fetch.get_sync_watermark,
            # File parsing
            file_parsing.parse_file,
            # Registration (shared)
            registration.process_chunk,
        ],
    )

    logger.info("Temporal worker started on queue %r", settings.task_queue)
    await worker.run()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
