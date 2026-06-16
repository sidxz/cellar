"""MarkDecompositionRunFailed — record a FAILED terminal state at the
orchestration boundary.

The runner deliberately does NOT mark FAILED on error (so a Temporal retry can
re-enter and recover). FAILED is set here instead — invoked by the Temporal
workflow once retries are exhausted, by the Null orchestrator's inline task, and
by the inline ``StartDecompositionRun`` path. Guarded + idempotent: a run that
is already terminal (e.g. a cancel that won the race, or a success) is left
untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from cellar.application.sar_analysis.repositories import RGroupDecompositionRunRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.rgroup_decomposition_run import InvalidRGroupRunTransition
from cellar.domain.shared.errors import ConcurrencyConflictError

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class MarkDecompositionRunFailedInput:
    run_id: UUID
    workspace_id: UUID
    error: str
    now: datetime


class MarkDecompositionRunFailed:
    def __init__(
        self, *, repository: RGroupDecompositionRunRepository, uow: UnitOfWork
    ) -> None:
        self._repo = repository
        self._uow = uow

    async def execute(self, payload: MarkDecompositionRunFailedInput) -> None:
        async with self._uow:
            run = await self._repo.find_by_id(payload.run_id, workspace_id=payload.workspace_id)
            if run is None:
                return
            try:
                failed = run.mark_failed(payload.error, payload.now)
            except InvalidRGroupRunTransition:
                return  # already terminal — idempotent no-op
            try:
                await self._repo.save(failed)
                await self._uow.commit()
            except ConcurrencyConflictError:
                # A concurrent transition (e.g. a cancel) advanced the row; leave
                # whatever terminal state won the race.
                logger.info(
                    "rgroup_decomposition_run_mark_failed_conflict",
                    run_id=str(payload.run_id),
                )
