"""GetTagsForEntity — the tags currently applied to one entity."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.tagging.repository import TagLinkRepositoryProvider
from cellar.domain.workspace_config.tagging.tag import Tag, TaggableEntityType


@dataclass(frozen=True, kw_only=True)
class GetTagsForEntityQuery(Query):
    workspace_id: uuid.UUID
    entity_type: TaggableEntityType
    entity_id: uuid.UUID


class GetTagsForEntity:
    def __init__(
        self, uow: UnitOfWork, link_provider: TagLinkRepositoryProvider
    ) -> None:
        self._uow = uow
        self._link_provider = link_provider

    async def __call__(
        self, input: GetTagsForEntityQuery, auth: AuthContext | None = None
    ) -> Result[list[Tag], DomainError]:
        async with self._uow:
            link_repo = self._link_provider.for_type(input.entity_type)
            tags = await link_repo.find_tags_for_entity(
                input.workspace_id, input.entity_id
            )
        return Success(tags)
