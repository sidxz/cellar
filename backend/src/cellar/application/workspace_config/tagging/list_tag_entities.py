"""List all entities (across types) carrying a given tag — workspace-scoped read.

Pure read path — the reader protocol + row DTO live here (CQRS reader, same
pattern as ``application.chemical_registration.molecule_reader``).  The
concrete implementation is in
``infrastructure.persistence.sqlalchemy.tagging.tag_browse_repository``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class TaggedEntityRow:
    entity_type: str
    entity_id: uuid.UUID
    label: str
    assigned_at: datetime


@runtime_checkable
class TagBrowseReader(Protocol):
    """Application-layer protocol for the cross-entity tag browse read-model."""

    async def find_entities_for_tags(
        self,
        workspace_id: uuid.UUID,
        tag_ids: list[uuid.UUID],
        *,
        match_all: bool = False,
        types: list[str] | None = None,
        limit: int = 200,
        excluded_org_ids: set[uuid.UUID] | None = None,
    ) -> list[TaggedEntityRow]: ...


@dataclass(frozen=True, kw_only=True)
class ListTagEntitiesQuery(Query):
    workspace_id: uuid.UUID
    tag_ids: list[uuid.UUID]
    match_all: bool = False
    types: list[str] | None = None
    limit: int = 200


class ListTagEntities:
    def __init__(
        self, uow: UnitOfWork, repo: TagBrowseReader, visibility: PlateVisibilityService
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._visibility = visibility

    async def __call__(
        self, input: ListTagEntitiesQuery, auth: AuthContext | None = None
    ) -> Result[list[TaggedEntityRow], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            rows = await self._repo.find_entities_for_tags(
                input.workspace_id,
                input.tag_ids,
                match_all=input.match_all,
                types=input.types,
                limit=input.limit,
                excluded_org_ids=excluded,
            )
        return Success(rows)
