"""PlateGroup aggregate — an open, org-owned hierarchy for organizing plates.

Adjacency-list tree: any group may be root, any group may nest. A plate
belongs to at most one group (cross-cutting labels are tags). Invariants that
need sibling/tree knowledge (name uniqueness per parent, no cycles, parent in
same workspace+org) are enforced at the application layer + DB constraints —
the aggregate alone cannot see its siblings.

Decisions:
- ``owner_org_id`` is required. Groups are net-new (no legacy NULL-owner rows
  to honor, unlike plates); an unowned hierarchy has no policy to govern it.
- ``group_type`` is a free optional string. The UI sources suggestions from
  the ``plate_group_type`` ControlledVocabulary, but membership is not
  domain-validated (no live CV-validation precedent in this codebase).
- ``RegisteredPlate.derive()`` does NOT copy ``group_id`` — grouping is
  manual curation, not lineage.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellar.domain.inventory.events import (
    PlateGroupCreated,
    PlateGroupMoved,
    PlateGroupUpdated,
)
from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ValidationError

MAX_NAME_LEN = 300
MAX_GROUP_TYPE_LEN = 100


def _validated_name(name: str) -> str:
    cleaned = name.strip() if name else ""
    if not cleaned:
        raise ValidationError("Group name must not be empty")
    if len(cleaned) > MAX_NAME_LEN:
        raise ValidationError(f"Group name must be at most {MAX_NAME_LEN} characters")
    return cleaned


def _validated_group_type(group_type: str | None) -> str | None:
    if group_type is None:
        return None
    cleaned = group_type.strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_GROUP_TYPE_LEN:
        raise ValidationError(
            f"group_type must be at most {MAX_GROUP_TYPE_LEN} characters"
        )
    return cleaned


class PlateGroup(AggregateRoot):
    """An org-owned node in the plate-organization hierarchy."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        owner_org_id: uuid.UUID,
        name: str,
        parent_group_id: uuid.UUID | None = None,
        group_type: str | None = None,
        description: str | None = None,
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.owner_org_id = owner_org_id
        self.name = _validated_name(name)
        self.parent_group_id = parent_group_id
        self.group_type = _validated_group_type(group_type)
        self.description = description
        self.created_by = created_by

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        owner_org_id: uuid.UUID,
        name: str,
        created_by: uuid.UUID,
        parent_group_id: uuid.UUID | None = None,
        group_type: str | None = None,
        description: str | None = None,
    ) -> PlateGroup:
        group = cls(
            workspace_id=workspace_id,
            owner_org_id=owner_org_id,
            name=name,
            parent_group_id=parent_group_id,
            group_type=group_type,
            description=description,
            created_by=created_by,
        )
        group.register_event(
            PlateGroupCreated(
                aggregate_id=group.id,
                aggregate_type="PlateGroup",
                workspace_id=workspace_id,
                name=group.name,
                owner_org_id=owner_org_id,
                parent_group_id=parent_group_id,
                created_by=created_by,
            )
        )
        return group

    def update(
        self,
        *,
        name: str | None = None,
        group_type: str | None = ...,  # type: ignore[assignment]
        description: str | None = ...,  # type: ignore[assignment]
    ) -> None:
        """Update mutable fields. Uses sentinel ``...`` for optional nullable fields."""
        if name is not None:
            self.name = _validated_name(name)
        if group_type is not ...:
            self.group_type = _validated_group_type(group_type)
        if description is not ...:
            self.description = description
        self.updated_at = datetime.now(UTC)
        self.register_event(
            PlateGroupUpdated(
                aggregate_id=self.id,
                aggregate_type="PlateGroup",
                workspace_id=self.workspace_id,
                name=self.name,
            )
        )

    def move_to(self, new_parent_group_id: uuid.UUID | None) -> None:
        """Reparent (None = make root). Cycle/same-org checks happen in the
        use case — the aggregate can only rule out the trivial self-cycle."""
        if new_parent_group_id == self.id:
            raise ValidationError("A group cannot be its own parent")
        old = self.parent_group_id
        self.parent_group_id = new_parent_group_id
        self.updated_at = datetime.now(UTC)
        self.register_event(
            PlateGroupMoved(
                aggregate_id=self.id,
                aggregate_type="PlateGroup",
                workspace_id=self.workspace_id,
                old_parent_group_id=old,
                new_parent_group_id=new_parent_group_id,
            )
        )
