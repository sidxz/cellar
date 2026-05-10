"""BulkRegistrationWorkflow — orchestrates file-based bulk molecule import.

Phases:
1. Create tracking aggregate
2. Parse file into chunks (activity)
3. Process each chunk through registration pipeline (reuses process_chunk)
4. Complete tracking aggregate

Uses continue_as_new every 2000 chunks for very large files (>500K molecules).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from chem_vault.infrastructure.temporal.activities.bulk_tracking import BulkTrackingActivities
    from chem_vault.infrastructure.temporal.activities.file_parsing import FileParsingActivities, ParseFileInput
    from chem_vault.infrastructure.temporal.activities.dtos import (
        ChunkInput,
        ChunkItem,
        CompleteBulkRegInput,
        CreateBulkRegInput,
        PersistChunkItemsInput,
    )
    from chem_vault.infrastructure.temporal.activities.registration import RegistrationActivities


@dataclass
class BulkRegistrationWorkflowInput:
    """Input for starting a bulk registration workflow."""

    workspace_id: str
    originating_org_id: str
    submitted_by: str
    source_file: str
    file_format: str
    storage_path: str  # absolute path to the uploaded file
    filename: str
    create_batch_on_duplicate: bool | None = None
    # For continue_as_new
    resume_bulk_reg_id: str | None = None
    resume_chunk_index: int = 0
    resume_total_count: int = 0
    resume_registered: int = 0
    resume_duplicate: int = 0
    resume_error: int = 0
    resume_disclosed: int = 0
    resume_merge_candidate: int = 0
    resume_conflict: int = 0
    resume_merge_candidates_list: list[dict] = field(default_factory=list)
    resume_chunks: list[list[dict]] | None = None


@dataclass
class BulkRegistrationProgress:
    """Progress state queryable from the workflow."""

    bulk_reg_id: str = ""
    status: str = "pending"
    total_count: int = 0
    registered_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    disclosed_count: int = 0
    merge_candidate_count: int = 0
    conflict_count: int = 0
    merge_candidates: list[dict] = field(default_factory=list)
    chunks_processed: int = 0
    chunks_total: int = 0

    @property
    def processed_count(self) -> int:
        return (
            self.registered_count
            + self.duplicate_count
            + self.error_count
            + self.disclosed_count
            + self.merge_candidate_count
            + self.conflict_count
        )


_CONTINUE_AS_NEW_EVERY = 2000  # chunks


@workflow.defn
class BulkRegistrationWorkflow:
    """Durable workflow for file-based bulk molecule registration."""

    def __init__(self) -> None:
        self._progress = BulkRegistrationProgress()
        self._cancel_requested = False

    @workflow.run
    async def run(self, input: BulkRegistrationWorkflowInput) -> BulkRegistrationProgress:

        # --- Phase 1: Create or resume tracking aggregate ---
        if input.resume_bulk_reg_id:
            bulk_reg_id = input.resume_bulk_reg_id
            self._progress.bulk_reg_id = bulk_reg_id
            self._progress.total_count = input.resume_total_count
            self._progress.registered_count = input.resume_registered
            self._progress.duplicate_count = input.resume_duplicate
            self._progress.error_count = input.resume_error
            self._progress.disclosed_count = input.resume_disclosed
            self._progress.merge_candidate_count = input.resume_merge_candidate
            self._progress.conflict_count = input.resume_conflict
            self._progress.merge_candidates = list(input.resume_merge_candidates_list)
            self._progress.status = "processing"
            chunks = input.resume_chunks or []
            self._progress.chunks_total = len(chunks) + input.resume_chunk_index
            start_chunk = 0  # chunks are already sliced for continue-as-new
        else:
            # --- Phase 2: Parse file ---
            parse_result = await workflow.execute_activity(
                FileParsingActivities.parse_file,
                ParseFileInput(
                    storage_path=input.storage_path,
                    file_format=input.file_format,
                    filename=input.filename,
                ),
                start_to_close_timeout=timedelta(minutes=10),
                heartbeat_timeout=timedelta(seconds=60),
            )

            # Create tracking aggregate with actual total
            bulk_reg_id = await workflow.execute_activity(
                BulkTrackingActivities.create_bulk_registration,
                CreateBulkRegInput(
                    workspace_id=input.workspace_id,
                    source_file=input.source_file,
                    file_format=input.file_format,
                    submitted_by=input.submitted_by,
                    total_count=parse_result.total_count,
                    workflow_id=workflow.info().workflow_id,
                ),
                start_to_close_timeout=timedelta(seconds=30),
            )

            self._progress.bulk_reg_id = bulk_reg_id
            self._progress.total_count = parse_result.total_count
            self._progress.chunks_total = parse_result.chunk_count
            self._progress.status = "processing"
            chunks = parse_result.chunks
            start_chunk = 0

        # --- Phase 3: Process chunks ---
        chunks_in_this_run = 0

        for i, chunk_data in enumerate(chunks[start_chunk:], start=start_chunk):
            if self._cancel_requested:
                break

            # Reconstruct ChunkItem list from dicts
            items = [ChunkItem(**d) for d in chunk_data]

            chunk_result = await workflow.execute_activity(
                RegistrationActivities.process_chunk,
                ChunkInput(
                    workspace_id=input.workspace_id,
                    originating_org_id=input.originating_org_id,
                    submitted_by=input.submitted_by,
                    items=items,
                    chunk_index=i,
                    create_batch_on_duplicate=input.create_batch_on_duplicate,
                ),
                start_to_close_timeout=timedelta(minutes=5),
                heartbeat_timeout=timedelta(seconds=120),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            # Persist per-row outcomes AND roll up counters in one transaction.
            # The activity handles BulkRegistrationItem inserts (idempotent on
            # row_index) plus aggregate counter increments via record_item().
            await workflow.execute_activity(
                BulkTrackingActivities.persist_chunk_items,
                PersistChunkItemsInput(
                    workspace_id=input.workspace_id,
                    bulk_reg_id=bulk_reg_id,
                    items=[
                        {
                            "row_index": r.row_index,
                            "success": r.success,
                            "action": r.action,
                            "molecule_id": r.molecule_id,
                            "batch_id": r.batch_id,
                            "batch_number": r.batch_number,
                            "error": r.error,
                        }
                        for r in chunk_result.results
                    ],
                ),
                start_to_close_timeout=timedelta(minutes=2),
            )

            self._progress.registered_count += chunk_result.registered
            self._progress.duplicate_count += chunk_result.duplicate
            self._progress.error_count += chunk_result.error
            self._progress.disclosed_count += chunk_result.disclosed
            self._progress.merge_candidate_count += chunk_result.merge_candidate
            self._progress.conflict_count += chunk_result.conflict

            # Collect merge candidates for review
            for r in chunk_result.results:
                if r.needs_merge_confirmation and r.disclosure_id:
                    self._progress.merge_candidates.append({
                        "row_index": r.row_index,
                        "molecule_id": r.molecule_id,
                        "matched_molecule_id": r.matched_molecule_id,
                        "disclosure_id": r.disclosure_id,
                    })

            self._progress.chunks_processed = (input.resume_chunk_index or 0) + i + 1

            chunks_in_this_run += 1

            # Continue-as-new for very large files
            if chunks_in_this_run >= _CONTINUE_AS_NEW_EVERY and i + 1 < len(chunks):
                workflow.continue_as_new(
                    BulkRegistrationWorkflowInput(
                        workspace_id=input.workspace_id,
                        originating_org_id=input.originating_org_id,
                        submitted_by=input.submitted_by,
                        source_file=input.source_file,
                        file_format=input.file_format,
                        storage_path=input.storage_path,
                        filename=input.filename,
                        create_batch_on_duplicate=input.create_batch_on_duplicate,
                        resume_bulk_reg_id=bulk_reg_id,
                        resume_chunk_index=self._progress.chunks_processed,
                        resume_total_count=self._progress.total_count,
                        resume_registered=self._progress.registered_count,
                        resume_duplicate=self._progress.duplicate_count,
                        resume_error=self._progress.error_count,
                        resume_disclosed=self._progress.disclosed_count,
                        resume_merge_candidate=self._progress.merge_candidate_count,
                        resume_conflict=self._progress.conflict_count,
                        resume_merge_candidates_list=self._progress.merge_candidates,
                        resume_chunks=chunks[i + 1 :],
                    )
                )

        # --- Phase 4: Complete ---
        if not self._cancel_requested:
            await workflow.execute_activity(
                BulkTrackingActivities.complete_bulk_registration,
                CompleteBulkRegInput(workspace_id=input.workspace_id, bulk_reg_id=bulk_reg_id),
                start_to_close_timeout=timedelta(seconds=30),
            )
            self._progress.status = "completed"

        return self._progress

    @workflow.query
    def get_progress(self) -> BulkRegistrationProgress:
        return self._progress

    @workflow.signal
    async def cancel(self) -> None:
        self._cancel_requested = True
