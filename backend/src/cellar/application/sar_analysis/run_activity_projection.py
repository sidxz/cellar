"""RunActivityProjection — in-process runner: load -> stream + enrich -> persist.

The Temporal activity wraps this; the Null orchestrator invokes it inline. Mirrors
RunDecomposition's state-machine handling. Members are re-streamed by source at run
time (workspace-scoped, no auth context). Each batch is enriched and its sparse
scalars are written immediately, so memory stays O(batch). The enricher shares the
runner's UoW so enrich + persist run on one session (wired in DI).
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
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjectionStatus

logger = structlog.get_logger(__name__)


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
            # 1. Claim. Idempotent re-entry: PENDING -> RUNNING, or re-claim a
            #    projection already RUNNING from a crashed attempt (a Temporal
            #    retry). Terminal states (incl. a cancel) are respected — no-op.
            async with self.uow:
                proj = await self.repository.find_by_id(run_id, workspace_id=workspace_id)
                if proj is None:
                    log.error("sar_activity_projection_not_found")
                    return
                if proj.status == SarActivityProjectionStatus.PENDING:
                    await self.repository.save(proj.mark_running(datetime.now(UTC)))
                    await self.uow.commit()
                elif proj.status != SarActivityProjectionStatus.RUNNING:
                    log.info("sar_activity_projection_not_runnable", status=str(proj.status))
                    return

            # 2. (Re)compute. Reset any rows from a prior attempt first, so a
            #    retry is idempotent and never collides on the value PK.
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

                # 3. Finalize. Re-read so a cancel that landed mid-run is
                #    respected rather than clobbered back to READY (the save is
                #    also version-checked as a backstop against the TOCTOU gap).
                current = await self.repository.find_by_id(run_id, workspace_id=workspace_id)
                if current is None or current.status != SarActivityProjectionStatus.RUNNING:
                    log.info(
                        "sar_activity_projection_no_longer_running",
                        status=str(current.status) if current is not None else "missing",
                    )
                    return
                await self.repository.save(
                    current.mark_ready(value_count=total, now=datetime.now(UTC))
                )
                await self.uow.commit()
            log.info("sar_activity_projection_ready", value_count=total)

        except Exception:
            # FAILED is marked at the orchestration boundary (Temporal workflow
            # on retry exhaustion, or the inline/Null handler), not here — so a
            # retry can re-enter and recover. Re-raise for the boundary.
            log.exception("sar_activity_projection_run_failed")
            raise
