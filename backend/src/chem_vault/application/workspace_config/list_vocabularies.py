"""ListVocabularies query — retrieve all controlled vocabularies for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_workspace_role
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError
from chem_vault.domain.workspace_config.controlled_vocabulary import ControlledVocabulary
from chem_vault.domain.workspace_config.repository import ControlledVocabularyRepository


@dataclass(frozen=True, kw_only=True)
class ListVocabulariesQuery(Query):
    workspace_id: uuid.UUID


class ListVocabularies:
    def __init__(self, uow: UnitOfWork, repo: ControlledVocabularyRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListVocabulariesQuery, auth: AuthContext | None = None
    ) -> Result[list[ControlledVocabulary], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            vocabs = await self._repo.find_by_workspace(input.workspace_id)
            return Success(vocabs)
