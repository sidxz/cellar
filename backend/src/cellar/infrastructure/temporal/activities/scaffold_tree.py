"""ScaffoldTreeActivities — Temporal activity that delegates to RunScaffoldTree.

A single ``run_scaffold_tree`` activity drives the full pipeline:
  fetch molecules → build network → persist READY job → expose result.

``RunScaffoldTree`` is injected at worker boot time so the activity class
is just a thin adapter — all business logic lives in the application layer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from temporalio import activity

from cellar.application.sar_analysis.run_scaffold_tree import RunScaffoldTree


@dataclass
class RunScaffoldTreeInput:
    job_id: str
    workspace_id: str
    molecule_ids: list[str]


class ScaffoldTreeActivities:
    def __init__(self, run_scaffold_tree: RunScaffoldTree) -> None:
        self._run = run_scaffold_tree

    @activity.defn
    async def run_scaffold_tree(self, input: RunScaffoldTreeInput) -> None:
        await self._run.run(
            job_id=uuid.UUID(input.job_id),
            workspace_id=uuid.UUID(input.workspace_id),
            molecule_ids=[uuid.UUID(mid) for mid in input.molecule_ids],
        )
