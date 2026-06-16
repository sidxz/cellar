"""StartActivityProjection — single entry point for the activity-projection endpoint.

Dispatches one of three paths (mirrors StartDecompositionRun):
1. Cache hit (any size)            -> return the prior READY projection header.
2. Cache miss, <= inline_threshold -> enrich inline, persist a READY projection.
3. Cache miss, > inline_threshold  -> persist PENDING + schedule the workflow.

A single pass over the member stream folds ``membership_hash`` over ``(id, version)``,
counts members, and buffers ids only up to the inline threshold. The job is
scheduled with the **source** (``collection_id`` or a bounded id list) + the channel
spec, never the expanded membership.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from cellar.application.sar_analysis.activity_channel import ActivityChannelSpec, channel_hash
from cellar.application.sar_analysis.activity_enrichment import (
    MoleculeActivityEnricher,
    enrich_to_scalars,
)
from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream
from cellar.application.sar_analysis.hashing import compute_membership_hash
from cellar.application.sar_analysis.mark_activity_projection_failed import (
    MarkActivityProjectionFailed,
    MarkActivityProjectionFailedInput,
)
from cellar.application.sar_analysis.repositories import SarActivityProjectionRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.sar_activity_projection import (
    SarActivityProjection,
    SarActivityProjectionStatus,
)


@dataclass(frozen=True)
class StartActivityProjectionInput:
    workspace_id: UUID
    requested_by: UUID
    collection_id: UUID | None
    molecule_ids: list[UUID] | None
    channel: ActivityChannelSpec
    now: datetime


class SarActivityProjectionOrchestrator(Protocol):
    async def schedule(
        self,
        *,
        projection_id: UUID,
        workspace_id: UUID,
        channel_spec: dict[str, Any],
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None: ...

    async def cancel(self, *, projection_id: UUID) -> None: ...


class StartActivityProjection:
    def __init__(
        self,
        *,
        members: DecompositionMemberStream,
        enricher: MoleculeActivityEnricher,
        repository: SarActivityProjectionRepository,
        orchestrator: SarActivityProjectionOrchestrator,
        uow: UnitOfWork,
        inline_threshold: int = 200,
    ) -> None:
        self._members = members
        self._enricher = enricher
        self._repo = repository
        self._orchestrator = orchestrator
        self._uow = uow
        # The inline path marks FAILED on error via the same guarded use case the
        # async boundary uses; it reuses this use case's repo + uow.
        self._mark_failed = MarkActivityProjectionFailed(repository=repository, uow=uow)
        self._inline_threshold = inline_threshold

    async def execute(self, payload: StartActivityProjectionInput) -> SarActivityProjection:
        ch_hash = channel_hash(payload.channel)
        spec_dict = payload.channel.to_spec_dict()

        async with self._uow:
            pairs, buffer_ids, count = await self._collect(payload)
            membership_hash = compute_membership_hash(pairs)

            cached = await self._repo.find_cached(
                workspace_id=payload.workspace_id,
                membership_hash=membership_hash,
                channel_hash=ch_hash,
            )
            if cached is not None:
                return cached

            proj = SarActivityProjection.create(
                workspace_id=payload.workspace_id,
                requested_by=payload.requested_by,
                membership_hash=membership_hash,
                channel_hash=ch_hash,
                channel_spec=spec_dict,
                now=payload.now,
            )
            is_inline = count <= self._inline_threshold
            # Persist the initial row: RUNNING for the inline path (value FKs need
            # the row to exist), PENDING for the async path.
            await self._repo.save(proj.mark_running(payload.now) if is_inline else proj)
            await self._uow.commit()

        if not is_inline:
            await self._orchestrator.schedule(
                projection_id=proj.id,
                workspace_id=payload.workspace_id,
                channel_spec=spec_dict,
                collection_id=payload.collection_id,
                molecule_ids=payload.molecule_ids,
            )
            return proj

        # Inline: enrich the small set now. On failure, mark FAILED so we never
        # leave an orphaned RUNNING row (mirrors the async runner's contract).
        try:
            async with self._uow:
                scalars = await enrich_to_scalars(
                    self._enricher,
                    workspace_id=payload.workspace_id,
                    molecule_ids=buffer_ids,
                    channel=payload.channel,
                )
                await self._repo.write_values(proj.id, scalars)
                # Re-read so a concurrent cancel is respected (and to mark_ready at
                # the row's current version under optimistic concurrency).
                current = await self._repo.find_by_id(
                    proj.id, workspace_id=payload.workspace_id
                )
                if current is None or current.status != SarActivityProjectionStatus.RUNNING:
                    return current if current is not None else proj
                ready = current.mark_ready(value_count=len(scalars), now=payload.now)
                await self._repo.save(ready)
                await self._uow.commit()
                return ready
        except Exception:
            await self._mark_failed.execute(
                MarkActivityProjectionFailedInput(
                    projection_id=proj.id,
                    workspace_id=payload.workspace_id,
                    error="inline activity projection failed",
                    now=payload.now,
                )
            )
            raise

    async def _collect(
        self, payload: StartActivityProjectionInput
    ) -> tuple[list[tuple[UUID, int]], list[UUID], int]:
        """One pass: fold (id, version) for the hash, count, buffer ids only while
        at/under the inline threshold (so a huge collection is hashed/counted
        without materializing its ids)."""
        pairs: list[tuple[UUID, int]] = []
        buffer: list[UUID] = []
        overflowed = False
        async for batch in self._members.stream(
            workspace_id=payload.workspace_id,
            collection_id=payload.collection_id,
            molecule_ids=payload.molecule_ids,
        ):
            for molecule_id, _smiles, version in batch:
                pairs.append((molecule_id, version))
                if not overflowed:
                    buffer.append(molecule_id)
                    if len(buffer) > self._inline_threshold:
                        overflowed = True
                        buffer = []  # release — this projection will be async
        return pairs, buffer, len(pairs)
