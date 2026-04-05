"""SavedSearch aggregate — persisted search criteria for re-execution."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from chem_vault.domain.research_organization.events import SavedSearchCreated
from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError


class SearchVisibility(StrEnum):
    PRIVATE = "private"
    PROJECT = "project"


class SavedSearch(AggregateRoot):
    """A reusable, named search definition.

    Invariants:
    - Name must be non-empty (stripped).
    - PROJECT visibility requires a project_id.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: str,
        query: dict,
        columns: list[str] | None = None,
        visibility: SearchVisibility = SearchVisibility.PRIVATE,
        project_id: uuid.UUID | None = None,
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        if not name or not name.strip():
            raise ValidationError("SavedSearch name must not be empty")
        self.workspace_id = workspace_id
        self.name = name.strip()
        self.query = dict(query)
        self.columns = list(columns) if columns else None
        self.visibility = visibility
        self.project_id = project_id
        self.created_by = created_by
        self._validate_visibility()

    def _validate_visibility(self) -> None:
        if self.visibility == SearchVisibility.PROJECT and self.project_id is None:
            raise ValidationError(
                "PROJECT visibility requires a project_id"
            )

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        query: dict,
        columns: list[str] | None = None,
        visibility: SearchVisibility = SearchVisibility.PRIVATE,
        project_id: uuid.UUID | None = None,
        created_by: uuid.UUID,
    ) -> SavedSearch:
        search = cls(
            workspace_id=workspace_id,
            name=name,
            query=query,
            columns=columns,
            visibility=visibility,
            project_id=project_id,
            created_by=created_by,
        )
        search.register_event(
            SavedSearchCreated(
                aggregate_id=search.id,
                aggregate_type="SavedSearch",
                workspace_id=workspace_id,
                name=search.name,
            )
        )
        return search

    def update(
        self,
        *,
        name: str | None = None,
        query: dict | None = None,
        columns: list[str] | None = ...,  # type: ignore[assignment]
        visibility: SearchVisibility | None = None,
        project_id: uuid.UUID | None = ...,  # type: ignore[assignment]
    ) -> None:
        """Update mutable fields.

        Uses sentinel ``...`` for nullable fields so callers can
        explicitly pass ``None`` to clear them.
        """
        if name is not None:
            if not name.strip():
                raise ValidationError("SavedSearch name must not be empty")
            self.name = name.strip()
        if query is not None:
            self.query = dict(query)
        if columns is not ...:
            self.columns = list(columns) if columns else None
        if visibility is not None:
            self.visibility = visibility
        if project_id is not ...:
            self.project_id = project_id
        self._validate_visibility()
        self.updated_at = datetime.now(UTC)
