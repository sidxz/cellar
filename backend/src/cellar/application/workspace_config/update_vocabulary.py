"""UpdateVocabulary command — rename, update terms, lock/unlock."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError
from cellar.domain.workspace_config.controlled_vocabulary import ControlledVocabulary
from cellar.domain.workspace_config.repository import ControlledVocabularyRepository


@dataclass(frozen=True, kw_only=True)
class UpdateVocabularyCommand(Command):
    workspace_id: uuid.UUID
    vocab_id: uuid.UUID
    name: str | None = None
    terms: list[str] | object | None = UNSET
    is_locked: bool | None = None


class UpdateVocabulary:
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
        self, input: UpdateVocabularyCommand, auth: AuthContext | None = None
    ) -> Result[ControlledVocabulary, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            vocab = await self._repo.find_by_id_in_workspace(input.workspace_id, input.vocab_id)
            if vocab is None:
                return Failure(NotFoundError("ControlledVocabulary", str(input.vocab_id)))

            if input.name is not None:
                existing = await self._repo.find_by_name(input.workspace_id, input.name.strip())
                if existing is not None and existing.id != vocab.id:
                    return Failure(
                        ConflictError(f"Vocabulary '{input.name.strip()}' already exists")
                    )
                vocab.rename(input.name)

            if input.terms is not UNSET and input.terms is not None:
                vocab.set_terms(input.terms)  # type: ignore[arg-type]

            if input.is_locked is True:
                vocab.lock()
            elif input.is_locked is False:
                vocab.unlock()

            await self._repo.save(vocab)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(vocab)
