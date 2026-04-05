"""Repository protocols for research organization entities."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from chem_vault.domain.research_organization.collection import Collection
from chem_vault.domain.research_organization.project import Project
from chem_vault.domain.research_organization.saved_search import SavedSearch


@runtime_checkable
class ProjectRepository(Protocol):
    """Repository for Project aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> Project | None: ...

    async def save(self, aggregate: Project) -> None: ...

    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[Project]: ...

    async def find_by_name(
        self, workspace_id: uuid.UUID, name: str
    ) -> Project | None: ...


@runtime_checkable
class CollectionRepository(Protocol):
    """Repository for Collection aggregates.

    Membership (molecule join table) is managed here, not in the aggregate.
    """

    async def find_by_id(self, id: uuid.UUID) -> Collection | None: ...

    async def save(self, aggregate: Collection) -> None: ...

    async def delete(self, id: uuid.UUID) -> None: ...

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None = None,
    ) -> list[Collection]: ...

    async def add_molecules(
        self, collection_id: uuid.UUID, molecule_ids: list[uuid.UUID]
    ) -> int: ...

    async def remove_molecules(
        self, collection_id: uuid.UUID, molecule_ids: list[uuid.UUID]
    ) -> int: ...

    async def get_molecule_ids(
        self,
        collection_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[uuid.UUID]: ...

    async def count_molecules(self, collection_id: uuid.UUID) -> int: ...

    async def find_collections_containing(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[Collection]: ...

    async def replace_molecule(
        self,
        workspace_id: uuid.UUID,
        old_molecule_id: uuid.UUID,
        new_molecule_id: uuid.UUID,
    ) -> int: ...


@runtime_checkable
class SavedSearchRepository(Protocol):
    """Repository for SavedSearch aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> SavedSearch | None: ...

    async def save(self, aggregate: SavedSearch) -> None: ...

    async def delete(self, id: uuid.UUID) -> None: ...

    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[SavedSearch]: ...

    async def find_by_project(
        self, project_id: uuid.UUID
    ) -> list[SavedSearch]: ...

    async def find_by_creator(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[SavedSearch]: ...
