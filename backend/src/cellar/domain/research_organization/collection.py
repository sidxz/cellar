"""Collection aggregate — metadata-only grouping of molecules."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellar.domain.research_organization.enums import CollectionType, CollectionVisibility
from cellar.domain.research_organization.events import CollectionCreated
from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import CollectionFrozenError, ValidationError


class Collection(AggregateRoot):
    """A curated set of molecules within a workspace.

    Membership (the join table) is managed by the repository, not in-memory.
    The aggregate only tracks metadata and a denormalized molecule_count.

    Invariants:
    - Name must be non-empty (stripped).
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: str,
        description: str | None = None,
        project_id: uuid.UUID | None = None,
        owned_by_org_id: uuid.UUID | None = None,
        created_by: uuid.UUID,
        molecule_count: int = 0,
        visibility: CollectionVisibility = CollectionVisibility.PRIVATE,
        type: CollectionType = CollectionType.GENERIC,
        is_frozen: bool = False,
        derived_from_campaign_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        if not name or not name.strip():
            raise ValidationError("Collection name must not be empty")
        self.workspace_id = workspace_id
        self.name = name.strip()
        self.description = description
        self.project_id = project_id
        self.owned_by_org_id = owned_by_org_id
        self.created_by = created_by
        self.molecule_count = molecule_count
        self.visibility = visibility
        self.type = type
        self.is_frozen = is_frozen
        self.derived_from_campaign_id = derived_from_campaign_id

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        description: str | None = None,
        project_id: uuid.UUID | None = None,
        owned_by_org_id: uuid.UUID | None = None,
        created_by: uuid.UUID,
        visibility: CollectionVisibility = CollectionVisibility.PRIVATE,
        type: CollectionType = CollectionType.GENERIC,
    ) -> Collection:
        collection = cls(
            workspace_id=workspace_id,
            name=name,
            description=description,
            project_id=project_id,
            owned_by_org_id=owned_by_org_id,
            created_by=created_by,
            visibility=visibility,
            type=type,
        )
        collection.register_event(
            CollectionCreated(
                aggregate_id=collection.id,
                aggregate_type="Collection",
                workspace_id=workspace_id,
                name=collection.name,
                type=collection.type.value,
            )
        )
        return collection

    def update(
        self,
        *,
        name: str | None = None,
        description: str | None = ...,  # type: ignore[assignment]
        project_id: uuid.UUID | None = ...,  # type: ignore[assignment]
        owned_by_org_id: uuid.UUID | None = ...,  # type: ignore[assignment]
        visibility: CollectionVisibility | None = None,
        type: CollectionType | None = None,
    ) -> None:
        """Update mutable fields.

        Uses sentinel ``...`` for nullable fields so callers can
        explicitly pass ``None`` to clear them.
        """
        if self.is_frozen:
            raise CollectionFrozenError("Cannot update a frozen collection")
        if name is not None:
            if not name.strip():
                raise ValidationError("Collection name must not be empty")
            self.name = name.strip()
        if description is not ...:
            self.description = description
        if project_id is not ...:
            self.project_id = project_id
        if owned_by_org_id is not ...:
            self.owned_by_org_id = owned_by_org_id
        if visibility is not None:
            self.visibility = visibility
        if type is not None:
            self.type = type
        self.updated_at = datetime.now(UTC)

    def freeze(self, *, derived_from_campaign_id: uuid.UUID) -> None:
        """Mark the collection as frozen — origin campaign owns it forever.

        Idempotent when called with the same origin. Raises if already
        frozen with a different origin.

        A no-op re-entry (same origin) does not advance updated_at.
        """
        if self.is_frozen:
            if self.derived_from_campaign_id != derived_from_campaign_id:
                raise CollectionFrozenError("Collection is already frozen with a different origin")
            return
        self.is_frozen = True
        self.derived_from_campaign_id = derived_from_campaign_id
        self.updated_at = datetime.now(UTC)
