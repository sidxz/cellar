"""RunDecomposition — in-process runner: claim -> reset + stream + decompose ->
finalize. The Temporal activity wraps this; the Null orchestrator invokes it
inline (dev / tests).

Lifecycle scaffolding (claim, re-read-before-finalize) is the shared
``claim_job`` / ``finalize_if_still_running``; the compute stays explicit here.
The runner never marks FAILED — it re-raises so a retry can re-enter; FAILED is
recorded at the orchestration boundary (``MarkJobFailed``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog

from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream
from cellar.application.sar_analysis.repositories import RGroupDecompositionRunRepository
from cellar.application.sar_analysis.rgroup_decomposition import StreamingDecomposer
from cellar.application.shared.async_job_runner import claim_job, finalize_if_still_running
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.rgroup_types import RGroupDecompositionResult

logger = structlog.get_logger(__name__)

_JOB_TYPE = "rgroup_decomposition"


def ready_counts(result: RGroupDecompositionResult) -> tuple[int, int, int]:
    """The verified count bridge: (matched, unmatched, total)."""
    matched = len(result.assignments)
    unmatched = len(result.unmatched_ids)
    return matched, unmatched, matched + unmatched


@dataclass
class RunDecomposition:
    members: DecompositionMemberStream
    decomposer: StreamingDecomposer
    repository: RGroupDecompositionRunRepository
    uow: UnitOfWork

    async def run(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        core_smiles: str,
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None:
        log = logger.bind(run_id=str(run_id), workspace_id=str(workspace_id))
        try:
            if not await claim_job(
                self.repository,
                self.uow,
                job_id=run_id,
                workspace_id=workspace_id,
                now=datetime.now(UTC),
                job_type=_JOB_TYPE,
            ):
                return

            # Reset any rows from a prior attempt, then (re)compute — idempotent
            # so a Temporal retry never collides on the assignment PK.
            async with self.uow:
                await self.repository.delete_assignments(run_id)
                session = self.decomposer.session(core_smiles=core_smiles)
                async for batch in self.members.stream(
                    workspace_id=workspace_id,
                    collection_id=collection_id,
                    molecule_ids=molecule_ids,
                ):
                    for molecule_id, smiles, _version in batch:
                        session.add(molecule_id, smiles or "")
                result = session.finish()
                await self.repository.write_assignments(run_id, result.assignments)
                matched, unmatched, total = ready_counts(result)

                await finalize_if_still_running(
                    self.repository,
                    self.uow,
                    job_id=run_id,
                    workspace_id=workspace_id,
                    apply_ready=lambda run: run.mark_ready(
                        rgroup_labels=result.rgroup_labels,
                        matched_count=matched,
                        unmatched_count=unmatched,
                        total_count=total,
                        now=datetime.now(UTC),
                    ),
                    job_type=_JOB_TYPE,
                )
            log.info("rgroup_decomposition_run_ready", matched=matched, unmatched=unmatched)
        except Exception:
            # FAILED is marked at the orchestration boundary (Temporal workflow on
            # retry exhaustion, or the inline/Null handler), not here — so a retry
            # can re-enter and recover. Re-raise for the boundary.
            log.exception("rgroup_decomposition_run_failed")
            raise
