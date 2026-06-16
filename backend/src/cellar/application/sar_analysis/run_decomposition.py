"""RunDecomposition — in-process runner: load -> stream + decompose -> persist.

The Temporal activity wraps this; the Null orchestrator invokes it inline (dev /
tests). Mirrors RunScaffoldTree's state-machine handling so the activity is a
thin adapter. Members are re-streamed by source at run time, workspace-scoped,
with no auth context (authorization happened at the start route).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog

from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream
from cellar.application.sar_analysis.repositories import RGroupDecompositionRunRepository
from cellar.application.sar_analysis.rgroup_decomposition import StreamingDecomposer
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRunStatus
from cellar.domain.sar_analysis.rgroup_types import RGroupDecompositionResult

logger = structlog.get_logger(__name__)


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
            # 1. Claim. Idempotent re-entry: PENDING -> RUNNING, or re-claim a
            #    run already RUNNING from a crashed attempt (a Temporal retry).
            #    Terminal states (incl. a cancel) are respected — no-op.
            async with self.uow:
                run = await self.repository.find_by_id(run_id, workspace_id=workspace_id)
                if run is None:
                    log.error("rgroup_decomposition_run_not_found")
                    return
                if run.status == RGroupDecompositionRunStatus.PENDING:
                    await self.repository.save(run.mark_running(datetime.now(UTC)))
                    await self.uow.commit()
                elif run.status != RGroupDecompositionRunStatus.RUNNING:
                    log.info("rgroup_decomposition_run_not_runnable", status=str(run.status))
                    return

            # 2. (Re)compute. Reset any rows from a prior attempt first, so a
            #    retry is idempotent and never collides on the assignment PK.
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

                # 3. Finalize. Re-read so a cancel that landed mid-run is
                #    respected rather than clobbered back to READY (the save is
                #    also version-checked as a backstop against the TOCTOU gap).
                current = await self.repository.find_by_id(run_id, workspace_id=workspace_id)
                if current is None or current.status != RGroupDecompositionRunStatus.RUNNING:
                    log.info(
                        "rgroup_decomposition_run_no_longer_running",
                        status=str(current.status) if current is not None else "missing",
                    )
                    return
                await self.repository.save(
                    current.mark_ready(
                        rgroup_labels=result.rgroup_labels,
                        matched_count=matched,
                        unmatched_count=unmatched,
                        total_count=total,
                        now=datetime.now(UTC),
                    )
                )
                await self.uow.commit()
            log.info("rgroup_decomposition_run_ready", matched=matched, unmatched=unmatched)

        except Exception:
            # FAILED is marked at the orchestration boundary (Temporal workflow
            # on retry exhaustion, or the inline/Null handler), not here — so a
            # retry can re-enter and recover. Re-raise for the boundary.
            log.exception("rgroup_decomposition_run_failed")
            raise
