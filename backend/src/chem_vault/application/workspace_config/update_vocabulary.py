"""UpdateVocabulary command — rename, update terms, lock/unlock."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.command import Command
from chem_vault.domain.shared.errors import ConflictError, DomainError, NotFoundError
from chem_vault.domain.workspace_config.controlled_vocabulary import ControlledVocabulary
from chem_vault.domain.workspace_config.repository import ControlledVocabularyRepository
from chem_vault.application.shared.unit_of_work import UnitOfWork

_SENTINEL = object()


@dataclass(frozen=True, kw_only=True)
class UpdateVocabularyCommand(Command):
    workspace_id: uuid.UUID
    vocab_id: uuid.UUID
    name: str | None = None
    terms: list[str] | None | object = _SENTINEL
    is_locked: bool | None = None


class UpdateVocabulary:
    def __init__(self, uow: UnitOfWork, repo: ControlledVocabularyRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: UpdateVocabularyCommand
    ) -> Result[ControlledVocabulary, DomainError]:
        async with self._uow:
            vocab = await self._repo.find_by_id(input.vocab_id)
            if vocab is None or vocab.workspace_id != input.workspace_id:
                return Failure(NotFoundError("ControlledVocabulary", str(input.vocab_id)))

            if input.name is not None:
                existing = await self._repo.find_by_name(
                    input.workspace_id, input.name.strip()
                )
                if existing is not None and existing.id != vocab.id:
                    return Failure(
                        ConflictError(f"Vocabulary '{input.name.strip()}' already exists")
                    )
                vocab.rename(input.name)

            if input.terms is not _SENTINEL and input.terms is not None:
                vocab.set_terms(input.terms)  # type: ignore[arg-type]

            if input.is_locked is True:
                vocab.lock()
            elif input.is_locked is False:
                vocab.unlock()

            await self._repo.save(vocab)
            await self._uow.commit()
            return Success(vocab)
