"""RunScaffoldTree — in-process runner: fetch → build network → persist → mark READY.

The Temporal activity wraps this runner. The NullScaffoldTreeOrchestrator also
invokes it inline for environments without a Temporal cluster (TEMPORAL_DISABLED=1
or unit tests).

Mirroring RenderExport, all state-machine transitions are handled here so that
the activity is a thin adapter and the orchestrator Null path has identical
business semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import structlog

from cellar.application.sar_analysis.build_scaffold_network import (
    BuildScaffoldNetwork,
    BuildScaffoldNetworkInput,
)
from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository
from cellar.application.shared.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass
class RunScaffoldTree:
    """Callable runner that drives the full scaffold-tree pipeline for one job.

    Dependencies are injected as dataclass fields so both the Temporal
    activity and the NullScaffoldTreeOrchestrator can wire them independently.

    Usage::

        runner = RunScaffoldTree(builder=..., repository=..., uow=...)
        await runner.run(job_id=job.id, workspace_id=job.workspace_id, molecule_ids=[...])
    """

    builder: BuildScaffoldNetwork
    repository: ScaffoldTreeJobRepository
    uow: UnitOfWork

    async def run(
        self, *, job_id: UUID, workspace_id: UUID, molecule_ids: list[UUID]
    ) -> None:
        """Execute the scaffold-tree pipeline for *job_id*.

        1. Load the job from the repository.
        2. Advance the state machine: PENDING → RUNNING.
        3. Run BuildScaffoldNetwork.
        4. Advance the state machine: RUNNING → READY (result attached).
        5. On any exception: advance to FAILED and re-raise so Temporal retries.
        """
        log = logger.bind(job_id=str(job_id), workspace_id=str(workspace_id))
        try:
            async with self.uow:
                job = await self.repository.find_by_id(job_id, workspace_id=workspace_id)
                if job is None:
                    log.error("scaffold_tree_job_not_found")
                    return
                running = job.mark_running(datetime.now(timezone.utc))
                await self.repository.save(running)
                await self.uow.commit()

            tree = await self.builder.execute(
                BuildScaffoldNetworkInput(
                    molecule_ids=molecule_ids,
                    workspace_id=workspace_id,
                )
            )

            async with self.uow:
                ready = running.mark_ready(tree, datetime.now(timezone.utc))
                await self.repository.save(ready)
                await self.uow.commit()
            log.info("scaffold_tree_job_ready", node_count=tree.stats.node_count)

        except Exception as exc:
            log.exception("scaffold_tree_job_failed")
            try:
                async with self.uow:
                    current = await self.repository.find_by_id(
                        job_id, workspace_id=workspace_id
                    )
                    if current is not None:
                        failed = current.mark_failed(str(exc), datetime.now(timezone.utc))
                        await self.repository.save(failed)
                        await self.uow.commit()
            except Exception:
                log.exception("scaffold_tree_fail_mark_failed")
            raise
