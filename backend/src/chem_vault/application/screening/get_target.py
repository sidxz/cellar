"""GetTarget and ListTargets query use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_workspace_role
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.repository import TargetRepository
from chem_vault.domain.screening_assay.target import Target
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetTargetQuery(Query):
    workspace_id: uuid.UUID
    target_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListTargetsQuery(Query):
    workspace_id: uuid.UUID


class GetTarget:
    def __init__(self, uow: UnitOfWork, repo: TargetRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetTargetQuery, auth: AuthContext | None = None
    ) -> Result[Target, DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            target = await self._repo.find_by_id_in_workspace(input.workspace_id, input.target_id)
            if target is None:
                return Failure(NotFoundError("Target", str(input.target_id)))
            return Success(target)


class ListTargets:
    def __init__(self, uow: UnitOfWork, repo: TargetRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListTargetsQuery, auth: AuthContext | None = None
    ) -> Result[list[Target], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            targets = await self._repo.find_by_workspace(input.workspace_id)
            return Success(targets)
