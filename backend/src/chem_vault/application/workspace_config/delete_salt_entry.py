"""DeleteSaltEntry command — remove a salt catalog entry."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError, NotFoundError, ValidationError
from chem_vault.domain.workspace_config.repository import SaltEntryRepository


@dataclass(frozen=True, kw_only=True)
class DeleteSaltEntryCommand(Command):
    workspace_id: uuid.UUID
    entry_id: uuid.UUID


class DeleteSaltEntry:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SaltEntryRepository,
    ) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: DeleteSaltEntryCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)

        async with self._uow:
            entry = await self._repo.find_by_id(input.entry_id)
            if entry is None or entry.workspace_id != input.workspace_id:
                return Failure(NotFoundError("SaltEntry", str(input.entry_id)))

            if entry.is_default:
                return Failure(ValidationError("Cannot delete default salt entries"))

            await self._repo.delete(input.entry_id)
            await self._uow.commit()
            return Success(None)
