"""RunScaffoldTree — in-process runner: claim -> build network -> finalize.

The Temporal activity wraps this; the Null orchestrator invokes it inline. The
lifecycle scaffolding (claim, re-read-before-finalize) is the shared
``claim_job`` / ``finalize_if_still_running``; the build stays explicit. The
result is header-only (no child rows), so there is no reset step. The runner
never marks FAILED — it re-raises so a retry can re-enter; FAILED is recorded at
the orchestration boundary (``MarkJobFailed``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog

from cellar.application.sar_analysis.build_scaffold_network import (
    BuildScaffoldNetwork,
    BuildScaffoldNetworkInput,
)
from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository
from cellar.application.shared.async_job_runner import claim_job, finalize_if_still_running
from cellar.application.shared.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

_JOB_TYPE = "scaffold_tree"


@dataclass
class RunScaffoldTree:
    """Callable runner that drives the full scaffold-tree pipeline for one job."""

    builder: BuildScaffoldNetwork
    repository: ScaffoldTreeJobRepository
    uow: UnitOfWork

    async def run(self, *, job_id: UUID, workspace_id: UUID, molecule_ids: list[UUID]) -> None:
        log = logger.bind(job_id=str(job_id), workspace_id=str(workspace_id))
        try:
            if not await claim_job(
                self.repository,
                self.uow,
                job_id=job_id,
                workspace_id=workspace_id,
                now=datetime.now(UTC),
                job_type=_JOB_TYPE,
            ):
                return

            tree = await self.builder.execute(
                BuildScaffoldNetworkInput(
                    molecule_ids=molecule_ids,
                    workspace_id=workspace_id,
                )
            )

            async with self.uow:
                await finalize_if_still_running(
                    self.repository,
                    self.uow,
                    job_id=job_id,
                    workspace_id=workspace_id,
                    apply_ready=lambda job: job.mark_ready(result=tree, now=datetime.now(UTC)),
                    job_type=_JOB_TYPE,
                )
            log.info("scaffold_tree_job_ready", node_count=tree.stats.node_count)

        except Exception:
            # FAILED is marked at the orchestration boundary (Temporal workflow on
            # retry exhaustion, or the Null orchestrator), not here — so a retry
            # can re-enter and recover. Re-raise for the boundary.
            log.exception("scaffold_tree_job_failed")
            raise
