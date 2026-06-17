"""RunActivityProjection — in-process runner: claim -> reset + stream + enrich ->
finalize. The Temporal activity wraps this; the Null orchestrator invokes it
inline.

Lifecycle scaffolding (claim, re-read-before-finalize) is the shared
``claim_job`` / ``finalize_if_still_running``; the enrich compute stays explicit.
Each batch is enriched and its sparse scalars written immediately, so memory
stays O(batch). The runner never marks FAILED — it re-raises so a retry can
re-enter; FAILED is recorded at the boundary (``MarkJobFailed``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from cellar.application.sar_analysis.activity_channel import ActivityChannelSpec
from cellar.application.sar_analysis.activity_enrichment import (
    MoleculeActivityEnricher,
    enrich_to_scalars,
)
from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream
from cellar.application.sar_analysis.repositories import SarActivityProjectionRepository
from cellar.application.shared.async_job_runner import claim_job, finalize_if_still_running
from cellar.application.shared.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

_JOB_TYPE = "sar_activity_projection"


@dataclass
class RunActivityProjection:
    members: DecompositionMemberStream
    enricher: MoleculeActivityEnricher
    repository: SarActivityProjectionRepository
    uow: UnitOfWork

    async def run(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        channel_spec: dict[str, Any],
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None:
        log = logger.bind(projection_id=str(run_id), workspace_id=str(workspace_id))
        channel = ActivityChannelSpec.from_spec_dict(channel_spec)
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

            # Reset prior value rows, then (re)enrich — idempotent so a Temporal
            # retry never collides on the value PK.
            async with self.uow:
                await self.repository.delete_values(run_id)
                total = 0
                async for batch in self.members.stream(
                    workspace_id=workspace_id,
                    collection_id=collection_id,
                    molecule_ids=molecule_ids,
                ):
                    ids = [molecule_id for molecule_id, _smiles, _version in batch]
                    scalars = await enrich_to_scalars(
                        self.enricher, workspace_id=workspace_id, molecule_ids=ids, channel=channel
                    )
                    if scalars:
                        await self.repository.write_values(run_id, scalars)
                        total += len(scalars)

                await finalize_if_still_running(
                    self.repository,
                    self.uow,
                    job_id=run_id,
                    workspace_id=workspace_id,
                    apply_ready=lambda proj: proj.mark_ready(
                        value_count=total, now=datetime.now(UTC)
                    ),
                    job_type=_JOB_TYPE,
                )
            log.info("sar_activity_projection_ready", value_count=total)
        except Exception:
            # FAILED is marked at the orchestration boundary (Temporal workflow on
            # retry exhaustion, or the inline/Null handler), not here — so a retry
            # can re-enter and recover. Re-raise for the boundary.
            log.exception("sar_activity_projection_run_failed")
            raise
