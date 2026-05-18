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
    from cellar.application.export.render_export import RenderExport
    from cellar.application.sar_analysis.run_scaffold_tree import RunScaffoldTree
    from cellar.application.sar_analysis.run_umap_cluster import RunUmapCluster
    from cellar.domain.shared.secret_provider import SecretProvider
    from cellar.infrastructure.cdd.client import CddVaultClient
    from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
    from cellar.infrastructure.temporal.activities.bulk_tracking import BulkTrackingActivities
    from cellar.infrastructure.temporal.activities.cdd_fetch import CddFetchActivities
    from cellar.infrastructure.temporal.activities.export import ExportActivities
    from cellar.infrastructure.temporal.activities.file_parsing import FileParsingActivities
    from cellar.infrastructure.temporal.activities.plate_registration import (
        PlateRegistrationActivities,
    )
    from cellar.infrastructure.temporal.activities.registration import RegistrationActivities
    from cellar.infrastructure.temporal.activities.scaffold_tree import ScaffoldTreeActivities
    from cellar.infrastructure.temporal.activities.umap_cluster import UmapClusterActivities
    from cellar.infrastructure.temporal.workflows.bulk_registration import (
        BulkRegistrationWorkflow,
    )
    from cellar.infrastructure.temporal.workflows.cdd_plate_import import CddPlateImportWorkflow
    from cellar.infrastructure.temporal.workflows.cdd_vault_import import CddVaultImportWorkflow
    from cellar.infrastructure.temporal.workflows.export import ExportWorkflow
    from cellar.infrastructure.temporal.workflows.scaffold_tree import ScaffoldTreeWorkflow
    from cellar.infrastructure.temporal.workflows.umap_cluster import UmapClusterWorkflow

    session_factory = container[async_sessionmaker]
    dispatcher = container[EventDispatcher]
    secret_provider = container[SecretProvider]
    cdd_client = container[CddVaultClient]
    structure_processor = container[StructureProcessorProtocol]
    side_effect_registry = container[MergeSideEffectRegistry]

    # --- Export activity ---
    # RenderExport (and its build_search_stream closure) is fully wired by the
    # DI container via register_export. Resolve it once here so the same
    # session-factory-scoped instance is reused across all activity invocations.
    render_export = container[RenderExport]
    export_activities = ExportActivities(render_export)

    # --- Scaffold-tree activity ---
    # RunScaffoldTree is wired by the DI container via register_sar_analysis.
    run_scaffold_tree = container[RunScaffoldTree]
    scaffold_tree_activities = ScaffoldTreeActivities(run_scaffold_tree)

    # --- UMAP cluster activity ---
    # RunUmapCluster is wired by the DI container via register_sar_analysis.
    run_umap_cluster = container[RunUmapCluster]
    umap_cluster_activities = UmapClusterActivities(run_umap_cluster)

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
        workflows=[
            CddVaultImportWorkflow,
            BulkRegistrationWorkflow,
            CddPlateImportWorkflow,
            ExportWorkflow,
            ScaffoldTreeWorkflow,
            UmapClusterWorkflow,
        ],
        activities=[
            # Scaffold tree
            scaffold_tree_activities.run_scaffold_tree,
            # UMAP cluster
            umap_cluster_activities.run_umap_cluster,
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
