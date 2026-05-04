"""DeleteCompoundFlag command use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.repository import CompoundFlagRepository
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class DeleteCompoundFlagCommand(Command):
    workspace_id: uuid.UUID
    flag_id: uuid.UUID


class DeleteCompoundFlag:
    def __init__(self, uow: UnitOfWork, repo: CompoundFlagRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: DeleteCompoundFlagCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)

        async with self._uow:
            await self._repo.delete(input.workspace_id, input.flag_id)
            await self._uow.commit()

        return Success(None)
