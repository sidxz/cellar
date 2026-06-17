"""StartDecompositionRun — single entry point for the decomposition endpoint.

Dispatches one of three paths (mirrors StartScaffoldTreeJob):
1. Cache hit (any size)        -> return the prior READY run header.
2. Cache miss, <= inline_threshold -> decompose inline, persist a READY run.
3. Cache miss, > inline_threshold  -> persist PENDING + schedule the workflow.

A single pass over the member stream folds ``membership_hash`` over
``(id, version)``, counts members, and buffers ``(id, smiles)`` only up to the
inline threshold — so a huge collection is hashed/counted without materializing
its structures. The job is scheduled with the **source** (``collection_id`` or a
bounded id list), never the expanded membership.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream
from cellar.application.sar_analysis.hashing import compute_membership_hash, sha256_hex
from cellar.application.sar_analysis.repositories import RGroupDecompositionRunRepository
from cellar.application.sar_analysis.rgroup_decomposition import StreamingDecomposer
from cellar.application.sar_analysis.run_decomposition import ready_counts
from cellar.application.shared.mark_job_failed import MarkJobFailed, MarkJobFailedInput
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.shared.async_job import AsyncJobStatus


@dataclass(frozen=True)
class StartDecompositionRunInput:
    workspace_id: UUID
    requested_by: UUID
    collection_id: UUID | None
    molecule_ids: list[UUID] | None
    core_smiles: str
    now: datetime


class RGroupDecompositionOrchestrator(Protocol):
    async def schedule(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        core_smiles: str,
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None: ...

    async def cancel(self, *, run_id: UUID) -> None: ...


class StartDecompositionRun:
    def __init__(
        self,
        *,
        members: DecompositionMemberStream,
        decomposer: StreamingDecomposer,
        repository: RGroupDecompositionRunRepository,
        orchestrator: RGroupDecompositionOrchestrator,
        uow: UnitOfWork,
        inline_threshold: int = 200,
    ) -> None:
        self._members = members
        self._decomposer = decomposer
        self._repo = repository
        self._orchestrator = orchestrator
        self._uow = uow
        # The inline path marks FAILED on error via the same guarded use case the
        # async boundary uses; it reuses this use case's repo + uow.
        self._mark_failed = MarkJobFailed(
            repository=repository, uow=uow, job_type="rgroup_decomposition"
        )
        self._inline_threshold = inline_threshold

    async def execute(self, payload: StartDecompositionRunInput) -> RGroupDecompositionRun:
        core_hash = sha256_hex(self._decomposer.canonical_core_smiles(payload.core_smiles))

        async with self._uow:
            pairs, buffer, count = await self._collect(payload)
            membership_hash = compute_membership_hash(pairs)

            cached = await self._repo.find_cached(
                workspace_id=payload.workspace_id,
                membership_hash=membership_hash,
                core_hash=core_hash,
            )
            if cached is not None:
                return cached

            run = RGroupDecompositionRun.create(
                workspace_id=payload.workspace_id,
                requested_by=payload.requested_by,
                membership_hash=membership_hash,
                core_smiles=payload.core_smiles,
                core_hash=core_hash,
                now=payload.now,
            )
            is_inline = count <= self._inline_threshold
            # Persist the initial row: RUNNING for the inline path (assignment FKs
            # need the row to exist), PENDING for the async path.
            if is_inline:
                run.mark_running(payload.now)
            await self._repo.save(run)
            await self._uow.commit()

        if not is_inline:
            await self._orchestrator.schedule(
                run_id=run.id,
                workspace_id=payload.workspace_id,
                core_smiles=payload.core_smiles,
                collection_id=payload.collection_id,
                molecule_ids=payload.molecule_ids,
            )
            return run

        # Inline: decompose the small set now. On failure, mark FAILED so we never
        # leave an orphaned RUNNING row (mirrors the async runner's contract).
        try:
            async with self._uow:
                session = self._decomposer.session(core_smiles=payload.core_smiles)
                for molecule_id, smiles in buffer:
                    session.add(molecule_id, smiles or "")
                result = session.finish()
                await self._repo.write_assignments(run.id, result.assignments)
                matched, unmatched, total = ready_counts(result)
                # Re-read so a concurrent cancel is respected (and to mark_ready at
                # the row's current version under optimistic concurrency).
                current = await self._repo.find_by_id_in_workspace(payload.workspace_id, run.id)
                if current is None or current.status != AsyncJobStatus.RUNNING:
                    return current if current is not None else run
                current.mark_ready(
                    rgroup_labels=result.rgroup_labels,
                    matched_count=matched,
                    unmatched_count=unmatched,
                    total_count=total,
                    now=payload.now,
                )
                await self._repo.save(current)
                await self._uow.commit()
                return current
        except Exception:
            await self._mark_failed.execute(
                MarkJobFailedInput(
                    job_id=run.id,
                    workspace_id=payload.workspace_id,
                    error="inline decomposition failed",
                    now=payload.now,
                )
            )
            raise

    async def _collect(
        self, payload: StartDecompositionRunInput
    ) -> tuple[list[tuple[UUID, int]], list[tuple[UUID, str | None]], int]:
        """One pass: fold (id, version) for the hash, count, buffer (id, smiles)
        only while at/under the inline threshold."""
        pairs: list[tuple[UUID, int]] = []
        buffer: list[tuple[UUID, str | None]] = []
        overflowed = False
        async for batch in self._members.stream(
            workspace_id=payload.workspace_id,
            collection_id=payload.collection_id,
            molecule_ids=payload.molecule_ids,
        ):
            for molecule_id, smiles, version in batch:
                pairs.append((molecule_id, version))
                if not overflowed:
                    buffer.append((molecule_id, smiles))
                    if len(buffer) > self._inline_threshold:
                        overflowed = True
                        buffer = []  # release — this run will be async
        return pairs, buffer, len(pairs)
