"""MarkActivityProjectionFailed — record a FAILED terminal state at the
orchestration boundary.

The runner deliberately does NOT mark FAILED on error (so a Temporal retry can
re-enter and recover). FAILED is set here instead — invoked by the Temporal
workflow once retries are exhausted, by the Null orchestrator's inline task, and
by the inline ``StartActivityProjection`` path. Guarded + idempotent: a
projection that is already terminal (e.g. a cancel that won the race, or a
success) is left untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from cellar.application.sar_analysis.repositories import SarActivityProjectionRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.sar_activity_projection import InvalidSarProjectionTransition
from cellar.domain.shared.errors import ConcurrencyConflictError

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class MarkActivityProjectionFailedInput:
    projection_id: UUID
    workspace_id: UUID
    error: str
    now: datetime


class MarkActivityProjectionFailed:
    def __init__(
        self, *, repository: SarActivityProjectionRepository, uow: UnitOfWork
    ) -> None:
        self._repo = repository
        self._uow = uow

    async def execute(self, payload: MarkActivityProjectionFailedInput) -> None:
        async with self._uow:
            proj = await self._repo.find_by_id(
                payload.projection_id, workspace_id=payload.workspace_id
            )
            if proj is None:
                return
            try:
                failed = proj.mark_failed(payload.error, payload.now)
            except InvalidSarProjectionTransition:
                return  # already terminal — idempotent no-op
            try:
                await self._repo.save(failed)
                await self._uow.commit()
            except ConcurrencyConflictError:
                # A concurrent transition (e.g. a cancel) advanced the row; leave
                # whatever terminal state won the race.
                logger.info(
                    "sar_activity_projection_mark_failed_conflict",
                    projection_id=str(payload.projection_id),
                )
