"""GetTarget and ListTargets query use cases."""

from __future__ import annotations

import uuid

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_same_workspace
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.repository import TargetRepository
from chem_vault.domain.screening_assay.target import Target
from chem_vault.domain.shared.errors import DomainError, NotFoundError


class GetTarget:
    def __init__(self, uow: UnitOfWork, repo: TargetRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, target_id: uuid.UUID, auth: AuthContext | None = None
    ) -> Result[Target, DomainError]:
        async with self._uow:
            target = await self._repo.find_by_id(target_id)
            if target is None:
                return Failure(NotFoundError("Target"))
            require_same_workspace(auth, target.workspace_id)
            return Success(target)


class ListTargets:
    def __init__(self, uow: UnitOfWork, repo: TargetRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, auth: AuthContext | None = None
    ) -> Result[list[Target], DomainError]:
        if auth is None:
            return Failure(NotFoundError("Target"))
        async with self._uow:
            targets = await self._repo.find_by_workspace(auth.workspace_id)
            return Success(targets)
