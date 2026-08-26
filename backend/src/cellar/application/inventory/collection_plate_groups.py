"""ListPlateGroupsForCollection — the physical plate groups realizing a collection (S16 §5).

Reader Protocol + row live here (single consumer); the SQLAlchemy implementation
is ``infrastructure.persistence.sqlalchemy.inventory.collection_plate_groups_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.repository import CollectionRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class CollectionPlateGroupRow:
    """One group linked to the collection, with its ancestry path and plate/loan counts.

    ``plate_count`` is direct members; the other three cover the group's whole
    subtree. ``on_loan_count`` = plates with an active item on an open loan;
    ``overdue_count`` = those whose loan ``due_date`` is before today.
    """

    group_id: uuid.UUID
    name: str
    group_type: str | None
    owner_org_id: uuid.UUID
    path: str
    plate_count: int
    subtree_plate_count: int
    on_loan_count: int
    overdue_count: int


@runtime_checkable
class CollectionPlateGroupsReader(Protocol):
    async def groups_for_collection(
        self, workspace_id: uuid.UUID, collection_id: uuid.UUID
    ) -> list[CollectionPlateGroupRow]: ...


@dataclass(frozen=True, kw_only=True)
class ListPlateGroupsForCollectionQuery(Query):
    workspace_id: uuid.UUID
    collection_id: uuid.UUID


class ListPlateGroupsForCollection:
    """Collection must exist (404); rows are filtered by strict group visibility."""

    def __init__(
        self,
        uow: UnitOfWork,
        collection_repo: CollectionRepository,
        visibility: PlateVisibilityService,
        reader: CollectionPlateGroupsReader,
    ) -> None:
        self._uow = uow
        self._collection_repo = collection_repo
        self._visibility = visibility
        self._reader = reader

    async def __call__(
        self, input: ListPlateGroupsForCollectionQuery, auth: AuthContext | None = None
    ) -> Result[list[CollectionPlateGroupRow], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            collection = await self._collection_repo.find_by_id_in_workspace(
                input.workspace_id, input.collection_id
            )
            if collection is None:
                return Failure(NotFoundError("Collection", str(input.collection_id)))
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            rows = await self._reader.groups_for_collection(
                input.workspace_id, input.collection_id
            )
            return Success(
                [r for r in rows if self._visibility.can_view_owner(r.owner_org_id, excluded)]
            )
