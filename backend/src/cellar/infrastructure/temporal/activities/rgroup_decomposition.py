"""RGroupDecompositionActivities — Temporal activity delegating to RunDecomposition.

RunDecomposition is injected at worker boot so the activity is a thin adapter.
The source (collection_id XOR molecule_ids) crosses the boundary as strings.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from temporalio import activity

from cellar.application.sar_analysis.run_decomposition import RunDecomposition
from cellar.application.shared.mark_job_failed import MarkJobFailed, MarkJobFailedInput


@dataclass
class RunDecompositionInput:
    run_id: str
    workspace_id: str
    core_smiles: str
    collection_id: str | None = None
    molecule_ids: list[str] = field(default_factory=list)


@dataclass
class MarkRunFailedInput:
    run_id: str
    workspace_id: str
    error: str


class RGroupDecompositionActivities:
    def __init__(
        self,
        run_decomposition: RunDecomposition,
        mark_failed: MarkJobFailed,
    ) -> None:
        self._run = run_decomposition
        self._mark_failed = mark_failed

    @activity.defn
    async def run_rgroup_decomposition(self, input: RunDecompositionInput) -> None:
        collection_id = uuid.UUID(input.collection_id) if input.collection_id else None
        molecule_ids = [uuid.UUID(m) for m in input.molecule_ids] if input.molecule_ids else None
        await self._run.run(
            run_id=uuid.UUID(input.run_id),
            workspace_id=uuid.UUID(input.workspace_id),
            core_smiles=input.core_smiles,
            collection_id=collection_id,
            molecule_ids=molecule_ids,
        )

    @activity.defn
    async def mark_rgroup_decomposition_failed(self, input: MarkRunFailedInput) -> None:
        # Invoked by the workflow once run retries are exhausted, so the row is
        # never left orphaned in RUNNING. Guarded + idempotent in the use case.
        await self._mark_failed.execute(
            MarkJobFailedInput(
                job_id=uuid.UUID(input.run_id),
                workspace_id=uuid.UUID(input.workspace_id),
                error=input.error,
                now=datetime.now(UTC),
            )
        )
