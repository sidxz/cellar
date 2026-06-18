"""ListProtocolVocabulary — distinct existing readout names / categories.

Read-only query backing autocomplete-at-entry. Suggests; never enforces.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.shared.errors import DomainError

_ALLOWED_FIELDS = {"readout_name", "category"}


@dataclass(frozen=True, kw_only=True)
class ListProtocolVocabularyQuery(Query):
    workspace_id: uuid.UUID
    field: str
    q: str | None = None
    limit: int = 10


class ListProtocolVocabulary:
    def __init__(self, uow: UnitOfWork, repo: ProtocolRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListProtocolVocabularyQuery, auth: AuthContext | None = None
    ) -> Result[list[str], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        if input.field not in _ALLOWED_FIELDS:
            return Success([])
        async with self._uow:
            values = await self._repo.list_distinct_values(
                input.workspace_id, field=input.field, q=input.q, limit=input.limit
            )
            return Success(values)
