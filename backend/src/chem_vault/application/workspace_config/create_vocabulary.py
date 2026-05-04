"""CreateVocabulary command — create a new controlled vocabulary."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import ConflictError, DomainError
from chem_vault.domain.workspace_config.controlled_vocabulary import ControlledVocabulary
from chem_vault.domain.workspace_config.repository import ControlledVocabularyRepository


@dataclass(frozen=True, kw_only=True)
class CreateVocabularyCommand(Command):
    workspace_id: uuid.UUID
    name: str
    terms: list[str] | None = None
    created_by: uuid.UUID


class CreateVocabulary:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ControlledVocabularyRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateVocabularyCommand, auth: AuthContext | None = None
    ) -> Result[ControlledVocabulary, DomainError]:
        require_editor(auth)

        async with self._uow:
            existing = await self._repo.find_by_name(input.workspace_id, input.name.strip())
            if existing is not None:
                return Failure(
                    ConflictError(f"Vocabulary '{input.name.strip()}' already exists")
                )

            vocab = ControlledVocabulary.create(
                workspace_id=input.workspace_id,
                name=input.name,
                terms=input.terms,
                created_by=input.created_by,
            )
            await self._repo.save(vocab)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(vocab)
