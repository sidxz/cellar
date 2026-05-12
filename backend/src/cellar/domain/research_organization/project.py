"""Project aggregate — workspace-level research project."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellar.domain.research_organization.enums import ProjectStatus
from cellar.domain.research_organization.events import ProjectArchived, ProjectCreated
from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ValidationError


class Project(AggregateRoot):
    """A research project that organizes collections, saved searches, and ELN entries.

    Invariants:
    - Name must be non-empty (stripped).
    - Archived projects cannot be modified.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: str,
        description: str | None = None,
        status: ProjectStatus = ProjectStatus.ACTIVE,
        created_by: uuid.UUID,
        archived_by: uuid.UUID | None = None,
        archived_at: datetime | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        if not name or not name.strip():
            raise ValidationError("Project name must not be empty")
        self.workspace_id = workspace_id
        self.name = name.strip()
        self.description = description
        self.status = status
        self.created_by = created_by
        self.archived_by = archived_by
        self.archived_at = archived_at

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        description: str | None = None,
        created_by: uuid.UUID,
    ) -> Project:
        project = cls(
            workspace_id=workspace_id,
            name=name,
            description=description,
            created_by=created_by,
        )
        project.register_event(
            ProjectCreated(
                aggregate_id=project.id,
                aggregate_type="Project",
                workspace_id=workspace_id,
                name=project.name,
            )
        )
        return project

    def update(
        self,
        *,
        name: str | None = None,
        description: str | None = ...,  # type: ignore[assignment]
    ) -> None:
        """Update mutable fields.

        Uses sentinel ``...`` for nullable ``description`` so callers can
        explicitly pass ``None`` to clear it.
        """
        self._guard_archived()
        if name is not None:
            if not name.strip():
                raise ValidationError("Project name must not be empty")
            self.name = name.strip()
        if description is not ...:
            self.description = description
        self.updated_at = datetime.now(UTC)

    def archive(self, *, archived_by: uuid.UUID) -> None:
        """Archive the project. Archived projects cannot be modified."""
        if self.status == ProjectStatus.ARCHIVED:
            raise ValidationError("Project is already archived")
        self.status = ProjectStatus.ARCHIVED
        self.archived_by = archived_by
        self.archived_at = datetime.now(UTC)
        self.updated_at = self.archived_at
        self.register_event(
            ProjectArchived(
                aggregate_id=self.id,
                aggregate_type="Project",
                workspace_id=self.workspace_id,
                archived_by=archived_by,
            )
        )

    def _guard_archived(self) -> None:
        if self.status == ProjectStatus.ARCHIVED:
            raise ValidationError("Cannot modify an archived project")
