"""List all entities (across types) carrying a given tag — workspace-scoped read."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_browse_repository import (
    SQLAlchemyTagBrowseRepository,
    TaggedEntityRow,
)


@dataclass(frozen=True, kw_only=True)
class ListTagEntitiesQuery(Query):
    workspace_id: uuid.UUID
    tag_id: uuid.UUID
    types: list[str] | None = None
    limit: int = 200


class ListTagEntities:
    def __init__(self, uow: UnitOfWork, repo: SQLAlchemyTagBrowseRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListTagEntitiesQuery, auth: AuthContext | None = None
    ) -> Result[list[TaggedEntityRow], DomainError]:
        async with self._uow:
            rows = await self._repo.find_entities_for_tag(
                input.workspace_id, input.tag_id, types=input.types, limit=input.limit
            )
        return Success(rows)
