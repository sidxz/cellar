"""CreateVocabulary command — create a new controlled vocabulary."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.command import Command
from chem_vault.domain.shared.errors import ConflictError, DomainError
from chem_vault.domain.workspace_config.controlled_vocabulary import ControlledVocabulary
from chem_vault.domain.workspace_config.repository import ControlledVocabularyRepository
from chem_vault.application.shared.unit_of_work import UnitOfWork


@dataclass(frozen=True, kw_only=True)
class CreateVocabularyCommand(Command):
    workspace_id: uuid.UUID
    name: str
    terms: list[str] | None = None
    created_by: uuid.UUID


class CreateVocabulary:
    def __init__(self, uow: UnitOfWork, repo: ControlledVocabularyRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: CreateVocabularyCommand
    ) -> Result[ControlledVocabulary, DomainError]:
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
            await self._uow.commit()
            return Success(vocab)
