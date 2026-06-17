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
    from cellar.application.sar_analysis.run_activity_projection import RunActivityProjection
    from cellar.application.sar_analysis.run_decomposition import RunDecomposition
    from cellar.application.sar_analysis.run_scaffold_tree import RunScaffoldTree
    from cellar.application.sar_analysis.run_umap_cluster import RunUmapCluster
    from cellar.application.shared.mark_job_failed import MarkJobFailed
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
    from cellar.infrastructure.temporal.activities.rgroup_decomposition import (
        RGroupDecompositionActivities,
    )
    from cellar.infrastructure.temporal.activities.sar_activity_projection import (
        SarActivityProjectionActivities,
    )
    from cellar.infrastructure.temporal.activities.scaffold_tree import ScaffoldTreeActivities
    from cellar.infrastructure.temporal.activities.umap_cluster import UmapClusterActivities
    from cellar.infrastructure.temporal.workflows.bulk_registration import (
        BulkRegistrationWorkflow,
    )
    from cellar.infrastructure.temporal.workflows.cdd_plate_import import CddPlateImportWorkflow
    from cellar.infrastructure.temporal.workflows.cdd_vault_import import CddVaultImportWorkflow
    from cellar.infrastructure.temporal.workflows.export import ExportWorkflow
    from cellar.infrastructure.temporal.workflows.rgroup_decomposition import (
        RGroupDecompositionWorkflow,
    )
    from cellar.infrastructure.temporal.workflows.sar_activity_projection import (
        SarActivityProjectionWorkflow,
    )
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

    # --- Scaffold-tree activity (mark-failed wired below, after the repo imports). ---
    # RunScaffoldTree is wired by the DI container via register_sar_analysis.
    run_scaffold_tree = container[RunScaffoldTree]

    # --- R-group decomposition activity ---
    # RunDecomposition is wired by the DI container via register_sar_analysis.
    # The mark-failed use case (own UoW) lets the workflow record FAILED on retry
    # exhaustion — the runner leaves FAILED-marking to this boundary.
    from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_run_repository import (  # noqa: E501
        SQLAlchemyRGroupDecompositionRunRepository,
    )
    from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
        SQLAlchemySarActivityProjectionRepository,
    )
    from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.scaffold_tree_job_repository import (  # noqa: E501
        SQLAlchemyScaffoldTreeJobRepository,
    )
    from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

    _scaffold_fail_uow = AsyncUnitOfWork(session_factory)
    scaffold_tree_activities = ScaffoldTreeActivities(
        run_scaffold_tree,
        MarkJobFailed(
            repository=SQLAlchemyScaffoldTreeJobRepository(_scaffold_fail_uow),
            uow=_scaffold_fail_uow,
            job_type="scaffold_tree",
        ),
    )

    run_rgroup_decomposition = container[RunDecomposition]
    _dec_fail_uow = AsyncUnitOfWork(session_factory)
    rgroup_decomposition_activities = RGroupDecompositionActivities(
        run_rgroup_decomposition,
        MarkJobFailed(
            repository=SQLAlchemyRGroupDecompositionRunRepository(_dec_fail_uow),
            uow=_dec_fail_uow,
            job_type="rgroup_decomposition",
        ),
    )

    # --- SAR activity projection activity ---
    run_sar_activity_projection = container[RunActivityProjection]
    _proj_fail_uow = AsyncUnitOfWork(session_factory)
    sar_activity_projection_activities = SarActivityProjectionActivities(
        run_sar_activity_projection,
        MarkJobFailed(
            repository=SQLAlchemySarActivityProjectionRepository(_proj_fail_uow),
            uow=_proj_fail_uow,
            job_type="sar_activity_projection",
        ),
    )

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
            RGroupDecompositionWorkflow,
            UmapClusterWorkflow,
            SarActivityProjectionWorkflow,
        ],
        activities=[
            # Scaffold tree
            scaffold_tree_activities.run_scaffold_tree,
            scaffold_tree_activities.mark_scaffold_tree_job_failed,
            # R-group decomposition
            rgroup_decomposition_activities.run_rgroup_decomposition,
            rgroup_decomposition_activities.mark_rgroup_decomposition_failed,
            # SAR activity projection
            sar_activity_projection_activities.run_sar_activity_projection,
            sar_activity_projection_activities.mark_sar_activity_projection_failed,
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
