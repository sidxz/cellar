"""DeleteVocabulary command — remove a controlled vocabulary."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.command import Command
from chem_vault.domain.shared.errors import DomainError, NotFoundError, ValidationError
from chem_vault.domain.workspace_config.repository import ControlledVocabularyRepository
from chem_vault.application.shared.unit_of_work import UnitOfWork


@dataclass(frozen=True, kw_only=True)
class DeleteVocabularyCommand(Command):
    workspace_id: uuid.UUID
    vocab_id: uuid.UUID


class DeleteVocabulary:
    def __init__(self, uow: UnitOfWork, repo: ControlledVocabularyRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: DeleteVocabularyCommand
    ) -> Result[None, DomainError]:
        async with self._uow:
            vocab = await self._repo.find_by_id(input.vocab_id)
            if vocab is None or vocab.workspace_id != input.workspace_id:
                return Failure(NotFoundError("ControlledVocabulary", str(input.vocab_id)))

            if vocab.is_locked:
                return Failure(
                    ValidationError("Cannot delete a locked vocabulary")
                )

            await self._repo.delete(input.vocab_id)
            await self._uow.commit()
            return Success(None)
