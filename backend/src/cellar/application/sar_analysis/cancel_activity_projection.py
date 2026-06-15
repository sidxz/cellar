from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import SarActivityProjectionRepository
from cellar.application.sar_analysis.start_activity_projection import (
    SarActivityProjectionOrchestrator,
)
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.sar_activity_projection import (
    InvalidSarProjectionTransition,
    SarActivityProjection,
)
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class CancelActivityProjectionInput:
    projection_id: UUID
    workspace_id: UUID
    now: datetime


class CancelActivityProjection:
    def __init__(
        self,
        *,
        repository: SarActivityProjectionRepository,
        orchestrator: SarActivityProjectionOrchestrator,
        uow: UnitOfWork,
    ) -> None:
        self._repo = repository
        self._orchestrator = orchestrator
        self._uow = uow

    async def execute(
        self, payload: CancelActivityProjectionInput
    ) -> Result[SarActivityProjection, DomainError]:
        async with self._uow:
            proj = await self._repo.find_by_id(
                payload.projection_id, workspace_id=payload.workspace_id
            )
            if proj is None:
                return Failure(NotFoundError("SarActivityProjection", str(payload.projection_id)))
            try:
                cancelled = proj.mark_cancelled(payload.now)
            except InvalidSarProjectionTransition:
                return Success(proj)  # already terminal — idempotent no-op
            await self._repo.save(cancelled)
            await self._uow.commit()
        await self._orchestrator.cancel(projection_id=proj.id)
        return Success(cancelled)
