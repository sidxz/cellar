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
            async with self.uow:
                run = await self.repository.find_by_id(run_id, workspace_id=workspace_id)
                if run is None:
                    log.error("rgroup_decomposition_run_not_found")
                    return
                if run.status != RGroupDecompositionRunStatus.PENDING:
                    log.info("rgroup_decomposition_run_not_pending", status=str(run.status))
                    return
                running = run.mark_running(datetime.now(UTC))
                await self.repository.save(running)
                await self.uow.commit()

            async with self.uow:
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
                ready = running.mark_ready(
                    rgroup_labels=result.rgroup_labels,
                    matched_count=matched,
                    unmatched_count=unmatched,
                    total_count=total,
                    now=datetime.now(UTC),
                )
                await self.repository.save(ready)
                await self.uow.commit()
            log.info("rgroup_decomposition_run_ready", matched=matched, unmatched=unmatched)

        except Exception as exc:
            log.exception("rgroup_decomposition_run_failed")
            try:
                async with self.uow:
                    current = await self.repository.find_by_id(run_id, workspace_id=workspace_id)
                    if (
                        current is not None
                        and current.status == RGroupDecompositionRunStatus.RUNNING
                    ):
                        failed = current.mark_failed(str(exc), datetime.now(UTC))
                        await self.repository.save(failed)
                        await self.uow.commit()
            except Exception:
                log.exception("rgroup_decomposition_fail_mark_failed")
            raise
