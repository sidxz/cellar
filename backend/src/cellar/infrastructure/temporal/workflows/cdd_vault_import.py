"""CddVaultImportWorkflow — orchestrates full CDD vault molecule import.

CDD uses an async export model:
1. Start export → get export_id
2. Poll /exports/{id} every 30s until finished (saved to disk)
3. Load chunks from disk → map → process through registration pipeline
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from cellar.infrastructure.temporal.activities.bulk_tracking import BulkTrackingActivities
    from cellar.infrastructure.temporal.activities.cdd_fetch import CddFetchActivities
    from cellar.infrastructure.temporal.activities.dtos import (
        CddPollExportInput,
        CddStartExportInput,
        CddSyncWatermarkInput,
        CompleteDiscoveryInput,
        ChunkInput,
        ChunkItem,
        CompleteCddImportInput,
        CreateCddImportInput,
        FailCddImportInput,
        LoadExportChunkInput,
        RecordSyncMappingsInput,
        UpdateCddImportProgressInput,
    )
    from cellar.infrastructure.temporal.activities.registration import RegistrationActivities
    from cellar.infrastructure.temporal.task_queues import CHUNK_SIZE
    from cellar.domain.chemical_registration.enums import CddImportMode


@dataclass
class CddVaultImportWorkflowInput:
    workspace_id: str
    cdd_vault_id: str
    import_mode: str
    submitted_by: str
    originating_org_id: str
    secret_ref: str
    filter_criteria: dict | None = None
    max_molecules: int | None = None
    entity_mappings: list[dict] | None = None  # serialized EntityMapping dicts
    create_batch_on_duplicate: bool | None = None
    # Resume fields — populated by continue-as-new to carry state across executions
    import_id: str | None = None
    storage_path: str | None = None
    resume_offset: int = 0
    resume_chunk_index: int = 0
    total_count: int = 0
    cumulative_registered: int = 0
    cumulative_duplicate: int = 0
    cumulative_error: int = 0
    cumulative_skipped: int = 0


@dataclass
class CddVaultImportProgress:
    import_id: str = ""
    status: str = "pending"
    total_count: int = 0
    registered_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    current_offset: int = 0
    pages_processed: int = 0


_RETRY = RetryPolicy(
    maximum_attempts=10, backoff_coefficient=2, initial_interval=timedelta(seconds=5)
)

# Continue-as-new every N chunks to keep workflow history small.
# 50 chunks × ~4 activities × 3 events = ~600 events per execution (limit: 50,000).
_CHUNKS_PER_EXECUTION = 50


@workflow.defn
class CddVaultImportWorkflow:
    def __init__(self) -> None:
        self._progress = CddVaultImportProgress()
        self._cancel_requested = False

    @workflow.run
    async def run(self, input: CddVaultImportWorkflowInput) -> CddVaultImportProgress:
        is_resume = input.import_id is not None

        if is_resume:
            # Resumed after continue-as-new — skip export/discovery phases
            import_id = input.import_id
            storage_path = input.storage_path
            self._progress = CddVaultImportProgress(
                import_id=import_id,
                status="processing",
                total_count=input.total_count,
                registered_count=input.cumulative_registered,
                duplicate_count=input.cumulative_duplicate,
                error_count=input.cumulative_error,
                skipped_count=input.cumulative_skipped,
                current_offset=input.resume_offset,
                pages_processed=input.resume_chunk_index,
            )
        else:
            # --- Phase 1: Create tracking aggregate ---
            import_id = await workflow.execute_activity(
                BulkTrackingActivities.create_cdd_import,
                CreateCddImportInput(
                    workspace_id=input.workspace_id,
                    cdd_vault_id=input.cdd_vault_id,
                    import_mode=input.import_mode,
                    originating_org_id=input.originating_org_id,
                    submitted_by=input.submitted_by,
                    workflow_id=workflow.info().workflow_id,
                    filter_criteria=input.filter_criteria,
                ),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=_RETRY,
            )
            self._progress.import_id = import_id
            self._progress.status = "discovering"

            # --- Phase 1b: Sync watermark lookup ---
            modified_after: str | None = None

            if input.import_mode == CddImportMode.SYNC:
                watermark = await workflow.execute_activity(
                    CddFetchActivities.get_sync_watermark,
                    CddSyncWatermarkInput(
                        workspace_id=input.workspace_id,
                        vault_id=input.cdd_vault_id,
                    ),
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=_RETRY,
                )
                modified_after = watermark.modified_after

            # --- Phase 2+3: Export and poll ---
            storage_path = await self._export_and_poll(input, import_id, modified_after)
            if storage_path is None:
                return self._progress  # cancelled or failed

            self._progress.status = "processing"

        # --- Phase 4: Load chunks from disk and process ---
        chunk_index = input.resume_chunk_index if is_resume else 0
        offset = input.resume_offset if is_resume else 0
        chunks_this_execution = 0

        while True:
            if self._cancel_requested:
                break

            chunk_result = await workflow.execute_activity(
                CddFetchActivities.load_export_chunk,
                LoadExportChunkInput(
                    storage_path=storage_path,
                    offset=offset,
                    limit=CHUNK_SIZE,
                    max_molecules=input.max_molecules,
                    entity_mappings=input.entity_mappings,
                ),
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=_RETRY,
            )

            if chunk_result.items:
                items = [ChunkItem(**d) for d in chunk_result.items]

                reg_result = await workflow.execute_activity(
                    RegistrationActivities.process_chunk,
                    ChunkInput(
                        workspace_id=input.workspace_id,
                        originating_org_id=input.originating_org_id,
                        submitted_by=input.submitted_by,
                        items=items,
                        chunk_index=chunk_index,
                        create_batch_on_duplicate=input.create_batch_on_duplicate,
                    ),
                    start_to_close_timeout=timedelta(minutes=5),
                    heartbeat_timeout=timedelta(seconds=120),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )

                await workflow.execute_activity(
                    BulkTrackingActivities.update_cdd_import_progress,
                    UpdateCddImportProgressInput(
                        workspace_id=input.workspace_id,
                        import_id=import_id,
                        registered=reg_result.mol_registered,
                        duplicate=reg_result.mol_duplicate,
                        error=reg_result.mol_error,
                        skipped=chunk_result.skipped,
                        last_processed_offset=offset + CHUNK_SIZE,
                    ),
                    start_to_close_timeout=timedelta(seconds=30),
                )

                # Record sync mappings (for both full and sync modes)
                sync_pairs = [
                    {
                        "cdd_molecule_id": r.cdd_molecule_id,
                        "molecule_id": r.molecule_id,
                        "cdd_modified_at": r.cdd_modified_at,
                    }
                    for r in reg_result.results
                    if r.success and r.molecule_id and r.cdd_molecule_id
                ]
                if sync_pairs:
                    await workflow.execute_activity(
                        BulkTrackingActivities.record_sync_mappings,
                        RecordSyncMappingsInput(
                            workspace_id=input.workspace_id,
                            cdd_vault_id=input.cdd_vault_id,
                            mappings=sync_pairs,
                        ),
                        start_to_close_timeout=timedelta(seconds=60),
                        retry_policy=_RETRY,
                    )

                self._progress.registered_count += reg_result.mol_registered
                self._progress.duplicate_count += reg_result.mol_duplicate
                self._progress.error_count += reg_result.mol_error
            elif chunk_result.skipped > 0:
                await workflow.execute_activity(
                    BulkTrackingActivities.update_cdd_import_progress,
                    UpdateCddImportProgressInput(
                        workspace_id=input.workspace_id,
                        import_id=import_id,
                        skipped=chunk_result.skipped,
                        last_processed_offset=offset + CHUNK_SIZE,
                    ),
                    start_to_close_timeout=timedelta(seconds=30),
                )

            self._progress.skipped_count += chunk_result.skipped
            self._progress.current_offset = offset + CHUNK_SIZE
            self._progress.pages_processed = chunk_index + 1
            offset += CHUNK_SIZE
            chunk_index += 1
            chunks_this_execution += 1

            if not chunk_result.has_more:
                break

            # Continue-as-new to prevent history size limit crash
            if chunks_this_execution >= _CHUNKS_PER_EXECUTION:
                workflow.continue_as_new(
                    CddVaultImportWorkflowInput(
                        workspace_id=input.workspace_id,
                        cdd_vault_id=input.cdd_vault_id,
                        import_mode=input.import_mode,
                        submitted_by=input.submitted_by,
                        originating_org_id=input.originating_org_id,
                        secret_ref=input.secret_ref,
                        filter_criteria=input.filter_criteria,
                        max_molecules=input.max_molecules,
                        entity_mappings=input.entity_mappings,
                        create_batch_on_duplicate=input.create_batch_on_duplicate,
                        import_id=import_id,
                        storage_path=storage_path,
                        resume_offset=offset,
                        resume_chunk_index=chunk_index,
                        total_count=self._progress.total_count,
                        cumulative_registered=self._progress.registered_count,
                        cumulative_duplicate=self._progress.duplicate_count,
                        cumulative_error=self._progress.error_count,
                        cumulative_skipped=self._progress.skipped_count,
                    ),
                )

        # --- Phase 5: Complete or cancel ---
        if self._cancel_requested:
            await self._fail(import_id, "Cancelled by user", input.workspace_id)
        else:
            await workflow.execute_activity(
                BulkTrackingActivities.complete_cdd_import,
                CompleteCddImportInput(workspace_id=input.workspace_id, import_id=import_id),
                start_to_close_timeout=timedelta(seconds=30),
            )
            self._progress.status = "completed"

        return self._progress

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _export_and_poll(
        self,
        input: CddVaultImportWorkflowInput,
        import_id: str,
        modified_after: str | None,
    ) -> str | None:
        """Start a single CDD export, poll until finished, return storage path.

        Uses POST /molecules/query — no URL length limits, no batching needed.
        Returns None if cancelled or failed.
        """
        if self._cancel_requested:
            await self._fail(import_id, "Cancelled by user", input.workspace_id)
            return None

        # Start export
        try:
            export_result = await workflow.execute_activity(
                CddFetchActivities.start_molecule_export,
                CddStartExportInput(
                    workspace_id=input.workspace_id,
                    secret_ref=input.secret_ref,
                    vault_id=input.cdd_vault_id,
                    max_molecules=input.max_molecules,
                    modified_after=modified_after,
                ),
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=_RETRY,
            )
        except Exception as exc:
            await self._fail(import_id, str(exc), input.workspace_id)
            return None

        # Transition to exporting
        await workflow.execute_activity(
            BulkTrackingActivities.complete_discovery,
            CompleteDiscoveryInput(
                workspace_id=input.workspace_id,
                import_id=import_id,
                total_count=export_result.total_count,
            ),
            start_to_close_timeout=timedelta(seconds=30),
        )
        self._progress.total_count = export_result.total_count
        self._progress.status = "exporting"

        # Poll until finished
        while True:
            if self._cancel_requested:
                await self._fail(import_id, "Cancelled by user", input.workspace_id)
                return None

            await workflow.sleep(timedelta(seconds=30))

            try:
                poll_result = await workflow.execute_activity(
                    CddFetchActivities.poll_molecule_export,
                    CddPollExportInput(
                        workspace_id=input.workspace_id,
                        secret_ref=input.secret_ref,
                        vault_id=input.cdd_vault_id,
                        export_id=export_result.export_id,
                    ),
                    start_to_close_timeout=timedelta(minutes=60),
                    heartbeat_timeout=timedelta(seconds=60),
                    retry_policy=_RETRY,
                )
            except Exception as exc:
                await self._fail(import_id, f"Export poll failed: {exc}", input.workspace_id)
                return None

            if poll_result.finished:
                return poll_result.storage_path

    async def _fail(self, import_id: str, reason: str, workspace_id: str = "") -> None:
        await workflow.execute_activity(
            BulkTrackingActivities.fail_cdd_import,
            FailCddImportInput(workspace_id=workspace_id, import_id=import_id, reason=reason),
            start_to_close_timeout=timedelta(seconds=30),
        )
        self._progress.status = "failed"

    @workflow.query
    def get_progress(self) -> CddVaultImportProgress:
        return self._progress

    @workflow.signal
    async def cancel(self) -> None:
        self._cancel_requested = True
