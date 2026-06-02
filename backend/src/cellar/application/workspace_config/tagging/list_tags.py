"""ListTags — autocomplete / listing of tags in a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.tagging.repository import TagRepository
from cellar.domain.workspace_config.tagging.tag import Tag


@dataclass(frozen=True, kw_only=True)
class ListTagsQuery(Query):
    workspace_id: uuid.UUID
    q: str | None = None
    created_by: uuid.UUID | None = None
    limit: int = 50


class ListTags:
    def __init__(self, uow: UnitOfWork, tag_repo: TagRepository) -> None:
        self._uow = uow
        self._tag_repo = tag_repo

    async def __call__(
        self, input: ListTagsQuery, auth: AuthContext | None = None
    ) -> Result[list[Tag], DomainError]:
        async with self._uow:
            tags = await self._tag_repo.search(
                input.workspace_id,
                q=input.q,
                created_by=input.created_by,
                limit=input.limit,
            )
        return Success(tags)
