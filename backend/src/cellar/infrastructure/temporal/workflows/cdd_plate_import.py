"""CddPlateImportWorkflow — orchestrates full CDD vault plate import.

Mirrors CddVaultImportWorkflow structure:
1. Start plate export → get export_id
2. Poll until finished (saved to disk)
3. Load chunks → map → register plates + resolve wells
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
        CddStartPlateExportInput,
        CompleteCddPlateImportInput,
        CompleteDiscoveryInput,
        CreateCddPlateImportInput,
        FailCddPlateImportInput,
        LoadPlateChunkInput,
        PlateChunkInput,
        PlateChunkItem,
        RecordPlateSyncMappingsInput,
        UpdateCddPlateImportProgressInput,
    )
    from cellar.infrastructure.temporal.activities.plate_registration import (
        PlateRegistrationActivities,
    )
    from cellar.infrastructure.temporal.task_queues import PLATE_CHUNK_SIZE


@dataclass
class CddPlateImportWorkflowInput:
    workspace_id: str
    cdd_vault_id: str
    submitted_by: str
    secret_ref: str
    entity_mappings: list[dict] | None = None  # serialized EntityMapping dicts
    # Resume fields — populated by continue-as-new
    import_id: str | None = None
    storage_path: str | None = None
    resume_offset: int = 0
    resume_chunk_index: int = 0
    total_count: int = 0
    cumulative_registered: int = 0
    cumulative_duplicate: int = 0
    cumulative_error: int = 0
    cumulative_wells_mapped: int = 0
    cumulative_wells_unresolved: int = 0


@dataclass
class CddPlateImportProgress:
    import_id: str = ""
    status: str = "pending"
    total_count: int = 0
    plates_registered: int = 0
    plates_duplicate: int = 0
    plates_error: int = 0
    wells_mapped: int = 0
    wells_unresolved: int = 0
    current_offset: int = 0
    pages_processed: int = 0


_RETRY = RetryPolicy(
    maximum_attempts=10, backoff_coefficient=2, initial_interval=timedelta(seconds=5)
)
_CHUNKS_PER_EXECUTION = 50


@workflow.defn
class CddPlateImportWorkflow:
    def __init__(self) -> None:
        self._progress = CddPlateImportProgress()
        self._cancel_requested = False

    @workflow.run
    async def run(self, input: CddPlateImportWorkflowInput) -> CddPlateImportProgress:
        is_resume = input.import_id is not None

        if is_resume:
            import_id = input.import_id
            storage_path = input.storage_path
            self._progress = CddPlateImportProgress(
                import_id=import_id,
                status="processing",
                total_count=input.total_count,
                plates_registered=input.cumulative_registered,
                plates_duplicate=input.cumulative_duplicate,
                plates_error=input.cumulative_error,
                wells_mapped=input.cumulative_wells_mapped,
                wells_unresolved=input.cumulative_wells_unresolved,
                current_offset=input.resume_offset,
                pages_processed=input.resume_chunk_index,
            )
        else:
            # --- Phase 1: Create tracking aggregate ---
            import_id = await workflow.execute_activity(
                BulkTrackingActivities.create_cdd_plate_import,
                CreateCddPlateImportInput(
                    workspace_id=input.workspace_id,
                    cdd_vault_id=input.cdd_vault_id,
                    submitted_by=input.submitted_by,
                    workflow_id=workflow.info().workflow_id,
                ),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=_RETRY,
            )
            self._progress.import_id = import_id
            self._progress.status = "discovering"

            # --- Phase 2+3: Export and poll ---
            storage_path = await self._export_and_poll(input, import_id)
            if storage_path is None:
                return self._progress

            self._progress.status = "processing"

        # --- Phase 4: Load chunks and process ---
        chunk_index = input.resume_chunk_index if is_resume else 0
        offset = input.resume_offset if is_resume else 0
        chunks_this_execution = 0

        while True:
            if self._cancel_requested:
                break

            chunk_result = await workflow.execute_activity(
                CddFetchActivities.load_plate_chunk,
                LoadPlateChunkInput(
                    storage_path=storage_path,
                    offset=offset,
                    limit=PLATE_CHUNK_SIZE,
                    entity_mappings=input.entity_mappings,
                ),
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=_RETRY,
            )

            if chunk_result.items:
                items = [PlateChunkItem(**d) for d in chunk_result.items]

                reg_result = await workflow.execute_activity(
                    PlateRegistrationActivities.process_plate_chunk,
                    PlateChunkInput(
                        workspace_id=input.workspace_id,
                        cdd_vault_id=input.cdd_vault_id,
                        submitted_by=input.submitted_by,
                        items=items,
                        chunk_index=chunk_index,
                    ),
                    start_to_close_timeout=timedelta(minutes=10),
                    heartbeat_timeout=timedelta(seconds=120),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )

                await workflow.execute_activity(
                    BulkTrackingActivities.update_cdd_plate_import_progress,
                    UpdateCddPlateImportProgressInput(
                        workspace_id=input.workspace_id,
                        import_id=import_id,
                        plates_registered=reg_result.plates_registered,
                        plates_duplicate=reg_result.plates_duplicate,
                        plates_error=reg_result.plates_error,
                        wells_mapped=reg_result.wells_mapped,
                        wells_unresolved=reg_result.wells_unresolved,
                        last_processed_offset=offset + PLATE_CHUNK_SIZE,
                    ),
                    start_to_close_timeout=timedelta(seconds=30),
                )

                # Record sync mappings
                if reg_result.sync_pairs:
                    await workflow.execute_activity(
                        BulkTrackingActivities.record_plate_sync_mappings,
                        RecordPlateSyncMappingsInput(
                            workspace_id=input.workspace_id,
                            cdd_vault_id=input.cdd_vault_id,
                            mappings=reg_result.sync_pairs,
                        ),
                        start_to_close_timeout=timedelta(seconds=60),
                        retry_policy=_RETRY,
                    )

                self._progress.plates_registered += reg_result.plates_registered
                self._progress.plates_duplicate += reg_result.plates_duplicate
                self._progress.plates_error += reg_result.plates_error
                self._progress.wells_mapped += reg_result.wells_mapped
                self._progress.wells_unresolved += reg_result.wells_unresolved

            self._progress.current_offset = offset + PLATE_CHUNK_SIZE
            self._progress.pages_processed = chunk_index + 1
            offset += PLATE_CHUNK_SIZE
            chunk_index += 1
            chunks_this_execution += 1

            if not chunk_result.has_more:
                break

            if chunks_this_execution >= _CHUNKS_PER_EXECUTION:
                workflow.continue_as_new(
                    CddPlateImportWorkflowInput(
                        workspace_id=input.workspace_id,
                        cdd_vault_id=input.cdd_vault_id,
                        submitted_by=input.submitted_by,
                        secret_ref=input.secret_ref,
                        entity_mappings=input.entity_mappings,
                        import_id=import_id,
                        storage_path=storage_path,
                        resume_offset=offset,
                        resume_chunk_index=chunk_index,
                        total_count=self._progress.total_count,
                        cumulative_registered=self._progress.plates_registered,
                        cumulative_duplicate=self._progress.plates_duplicate,
                        cumulative_error=self._progress.plates_error,
                        cumulative_wells_mapped=self._progress.wells_mapped,
                        cumulative_wells_unresolved=self._progress.wells_unresolved,
                    ),
                )

        # --- Phase 5: Complete or cancel ---
        if self._cancel_requested:
            await self._fail(import_id, "Cancelled by user", input.workspace_id)
        else:
            await workflow.execute_activity(
                BulkTrackingActivities.complete_cdd_plate_import,
                CompleteCddPlateImportInput(workspace_id=input.workspace_id, import_id=import_id),
                start_to_close_timeout=timedelta(seconds=30),
            )
            self._progress.status = "completed"

        return self._progress

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _export_and_poll(
        self,
        input: CddPlateImportWorkflowInput,
        import_id: str,
    ) -> str | None:
        """Start CDD plate export, poll until finished, return storage path."""
        if self._cancel_requested:
            await self._fail(import_id, "Cancelled by user", input.workspace_id)
            return None

        try:
            export_result = await workflow.execute_activity(
                CddFetchActivities.start_plate_export,
                CddStartPlateExportInput(
                    workspace_id=input.workspace_id,
                    secret_ref=input.secret_ref,
                    vault_id=input.cdd_vault_id,
                ),
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=_RETRY,
            )
        except Exception as exc:
            await self._fail(import_id, str(exc), input.workspace_id)
            return None

        await workflow.execute_activity(
            BulkTrackingActivities.complete_plate_discovery,
            CompleteDiscoveryInput(
                workspace_id=input.workspace_id,
                import_id=import_id,
                total_count=export_result.total_count,
            ),
            start_to_close_timeout=timedelta(seconds=30),
        )
        self._progress.total_count = export_result.total_count
        self._progress.status = "exporting"

        while True:
            if self._cancel_requested:
                await self._fail(import_id, "Cancelled by user", input.workspace_id)
                return None

            await workflow.sleep(timedelta(seconds=30))

            try:
                poll_result = await workflow.execute_activity(
                    CddFetchActivities.poll_plate_export,
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
            BulkTrackingActivities.fail_cdd_plate_import,
            FailCddPlateImportInput(workspace_id=workspace_id, import_id=import_id, reason=reason),
            start_to_close_timeout=timedelta(seconds=30),
        )
        self._progress.status = "failed"

    @workflow.query
    def get_progress(self) -> CddPlateImportProgress:
        return self._progress

    @workflow.signal
    async def cancel(self) -> None:
        self._cancel_requested = True
