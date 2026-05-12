"""CreateSaltEntry command — create a new salt catalog entry."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import ConflictError, DomainError
from cellar.domain.workspace_config.salt_entry import SaltEntry
from cellar.domain.workspace_config.repository import SaltEntryRepository


@dataclass(frozen=True, kw_only=True)
class CreateSaltEntryCommand(Command):
    workspace_id: uuid.UUID
    code: str
    name: str
    smiles: str
    molecular_weight: float
    is_default: bool = False


class CreateSaltEntry:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SaltEntryRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateSaltEntryCommand, auth: AuthContext | None = None
    ) -> Result[SaltEntry, DomainError]:
        require_editor(auth)

        async with self._uow:
            # Check for duplicate code in this workspace
            existing = await self._repo.find_by_code(input.workspace_id, input.code.strip())
            if existing is not None:
                return Failure(
                    ConflictError(
                        f"Salt entry with code '{input.code.strip()}' already exists in this workspace"
                    )
                )

            entry = SaltEntry.create(
                workspace_id=input.workspace_id,
                code=input.code,
                name=input.name,
                smiles=input.smiles,
                molecular_weight=input.molecular_weight,
                is_default=input.is_default,
            )
            await self._repo.save(entry)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(entry)
