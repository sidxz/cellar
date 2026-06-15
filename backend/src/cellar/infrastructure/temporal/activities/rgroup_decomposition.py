"""RGroupDecompositionActivities — Temporal activity delegating to RunDecomposition.

RunDecomposition is injected at worker boot so the activity is a thin adapter.
The source (collection_id XOR molecule_ids) crosses the boundary as strings.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from temporalio import activity

from cellar.application.sar_analysis.run_decomposition import RunDecomposition


@dataclass
class RunDecompositionInput:
    run_id: str
    workspace_id: str
    core_smiles: str
    collection_id: str | None = None
    molecule_ids: list[str] = field(default_factory=list)


class RGroupDecompositionActivities:
    def __init__(self, run_decomposition: RunDecomposition) -> None:
        self._run = run_decomposition

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
