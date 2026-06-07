"""Repository protocols for research organization entities."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol, runtime_checkable

from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.collection import Collection
from cellar.domain.research_organization.collection_import_template import (
    CollectionImportTemplate,
)
from cellar.domain.research_organization.project import Project
from cellar.domain.research_organization.project_membership import (
    ProjectMember,
    ProjectRole,
)
from cellar.domain.research_organization.project_scope_stats import ProjectScopeStats
from cellar.domain.research_organization.saved_search import SavedSearch
from cellar.domain.shared.target_ref import TargetRef


@runtime_checkable
class ProjectRepository(Protocol):
    """Repository for Project aggregates."""

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Project | None: ...

    async def save(self, aggregate: Project) -> None: ...

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> list[Project]: ...

    async def find_by_name(self, workspace_id: uuid.UUID, name: str) -> Project | None: ...

    async def get_scope_stats(
        self, workspace_id: uuid.UUID, project_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ProjectScopeStats]: ...


@runtime_checkable
class CollectionRepository(Protocol):
    """Repository for Collection aggregates.

    Membership (molecule join table) is managed here, not in the aggregate.
    """

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Collection | None: ...

    async def save(self, aggregate: Collection) -> None: ...

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        project_ids: list[uuid.UUID] | None = None,
        cursor: tuple[datetime, uuid.UUID] | None = None,
        limit: int | None = None,
    ) -> list[Collection]:
        """List collections newest-activity-first (``updated_at DESC, id DESC``).

        ``cursor`` is the (updated_at, id) of the last row of the previous page
        for keyset pagination.
        """
        ...

    async def add_molecules(
        self, workspace_id: uuid.UUID, collection_id: uuid.UUID, molecule_ids: list[uuid.UUID]
    ) -> int: ...

    async def remove_molecules(
        self, workspace_id: uuid.UUID, collection_id: uuid.UUID, molecule_ids: list[uuid.UUID]
    ) -> int: ...

    async def get_molecule_ids(
        self,
        workspace_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[uuid.UUID]: ...

    async def count_molecules(self, workspace_id: uuid.UUID, collection_id: uuid.UUID) -> int: ...

    async def find_collections_containing(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[Collection]: ...

    async def replace_molecule(
        self,
        workspace_id: uuid.UUID,
        old_molecule_id: uuid.UUID,
        new_molecule_id: uuid.UUID,
    ) -> int: ...

    async def compose_molecule_ids(
        self,
        workspace_id: uuid.UUID,
        operation: str,
        collection_ids: list[uuid.UUID],
    ) -> list[uuid.UUID]: ...


@runtime_checkable
class SavedSearchRepository(Protocol):
    """Repository for SavedSearch aggregates."""

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> SavedSearch | None: ...

    async def save(self, aggregate: SavedSearch) -> None: ...

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...

    async def find_by_workspace(self, workspace_id: uuid.UUID) -> list[SavedSearch]: ...

    async def find_by_project(
        self, workspace_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[SavedSearch]: ...

    async def find_by_creator(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[SavedSearch]: ...


@runtime_checkable
class ProjectMemberRepository(Protocol):
    """Repository for project membership records.

    All mutation/query methods take ``workspace_id`` as the first parameter
    for defense-in-depth workspace scoping.
    """

    async def find_accessible_project_ids(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[uuid.UUID]: ...

    async def find_members(
        self, workspace_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[ProjectMember]: ...

    async def add_member(
        self, workspace_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID, role: ProjectRole
    ) -> None: ...

    async def remove_member(
        self, workspace_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> None: ...

    async def update_role(
        self, workspace_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID, role: ProjectRole
    ) -> None: ...

    async def get_role(
        self, workspace_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> ProjectRole | None: ...


@runtime_checkable
class CampaignRepository(Protocol):
    """Repository for Campaign aggregates.

    Owns the loading/saving of channels, results, and measurements via
    aggregate-cascade semantics. The is_locked method also satisfies the
    CampaignLockChecker Protocol structurally.
    """

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Campaign | None: ...

    async def save(self, aggregate: Campaign) -> None: ...

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...

    async def find_by_project(
        self,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
        tags: list[uuid.UUID] | None = None,
        tag_logic: str = "any",
    ) -> list[Campaign]: ...

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
        tags: list[uuid.UUID] | None = None,
        tag_logic: str = "any",
    ) -> list[Campaign]: ...

    async def is_locked(self, workspace_id: uuid.UUID, campaign_id: uuid.UUID) -> bool: ...

    async def project_targets(
        self, workspace_id: uuid.UUID, campaigns: list[Campaign]
    ) -> dict[uuid.UUID, list[TargetRef]]:
        """Distinct targets per campaign, unioned from its runs' run_targets.

        Read-time projection (never stored). Returns {} entries omitted for
        campaigns with no measured targets.
        """
        ...


@runtime_checkable
class CollectionImportTemplateRepository(Protocol):
    """Repository for CollectionImportTemplate aggregates."""

    async def save(self, template: CollectionImportTemplate) -> None: ...

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, template_id: uuid.UUID
    ) -> CollectionImportTemplate | None: ...

    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[CollectionImportTemplate]: ...

    async def delete(self, workspace_id: uuid.UUID, template_id: uuid.UUID) -> None: ...
