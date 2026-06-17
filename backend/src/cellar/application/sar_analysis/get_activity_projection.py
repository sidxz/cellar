from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import SarActivityProjectionRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class GetActivityProjectionInput:
    projection_id: UUID
    workspace_id: UUID


class GetActivityProjection:
    def __init__(self, *, repository: SarActivityProjectionRepository, uow: UnitOfWork) -> None:
        self._repo = repository
        self._uow = uow

    async def execute(
        self, payload: GetActivityProjectionInput
    ) -> Result[SarActivityProjection, DomainError]:
        async with self._uow:
            proj = await self._repo.find_by_id_in_workspace(
                payload.workspace_id, payload.projection_id
            )
        if proj is None:
            return Failure(NotFoundError("SarActivityProjection", str(payload.projection_id)))
        return Success(proj)
