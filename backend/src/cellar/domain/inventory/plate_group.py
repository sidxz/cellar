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
  manual curation, not lineage. Membership changes emit
  ``PlateGroupMembershipChanged`` (audited — user decision 2026-08-13).
- Legacy-set metadata (state, location, initial vol/conc, compound count,
  scientist) lives on the group as optional fields (spec 2026-08-25 §5);
  ``plate_format`` is derived from member plates, never stored.
- ``collection_id`` optionally links the group (any level) to the Collection
  it physically realizes (spec 2026-08-26); existence is checked in the use
  case, inheritance to descendants is display-only.
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
MAX_STATE_LEN = 50
MAX_SCIENTIST_LEN = 200


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
        raise ValidationError(f"group_type must be at most {MAX_GROUP_TYPE_LEN} characters")
    return cleaned


def _validated_text(value: str | None, *, max_len: int, label: str) -> str | None:
    """Strip; empty → None; enforce a max length (same stance as group_type)."""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > max_len:
        raise ValidationError(f"{label} must be at most {max_len} characters")
    return cleaned


def _non_negative(value: float | int | None, *, label: str) -> float | int | None:
    if value is not None and (isinstance(value, bool) or value < 0):
        raise ValidationError(f"{label} must be >= 0")
    return value


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
        state: str | None = None,
        storage_location_id: uuid.UUID | None = None,
        initial_volume_ul: float | None = None,
        initial_concentration_mm: float | None = None,
        compound_count: int | None = None,
        scientist: str | None = None,
        collection_id: uuid.UUID | None = None,
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
        self.state = _validated_text(state, max_len=MAX_STATE_LEN, label="state")
        self.storage_location_id = storage_location_id
        self.initial_volume_ul = _non_negative(initial_volume_ul, label="initial_volume_ul")
        self.initial_concentration_mm = _non_negative(
            initial_concentration_mm, label="initial_concentration_mm"
        )
        self.compound_count = _non_negative(compound_count, label="compound_count")
        self.scientist = _validated_text(scientist, max_len=MAX_SCIENTIST_LEN, label="scientist")
        self.collection_id = collection_id
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
        state: str | None = None,
        storage_location_id: uuid.UUID | None = None,
        initial_volume_ul: float | None = None,
        initial_concentration_mm: float | None = None,
        compound_count: int | None = None,
        scientist: str | None = None,
        collection_id: uuid.UUID | None = None,
    ) -> PlateGroup:
        group = cls(
            workspace_id=workspace_id,
            owner_org_id=owner_org_id,
            name=name,
            parent_group_id=parent_group_id,
            group_type=group_type,
            description=description,
            state=state,
            storage_location_id=storage_location_id,
            initial_volume_ul=initial_volume_ul,
            initial_concentration_mm=initial_concentration_mm,
            compound_count=compound_count,
            scientist=scientist,
            collection_id=collection_id,
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
        state: str | None = ...,  # type: ignore[assignment]
        storage_location_id: uuid.UUID | None = ...,  # type: ignore[assignment]
        initial_volume_ul: float | None = ...,  # type: ignore[assignment]
        initial_concentration_mm: float | None = ...,  # type: ignore[assignment]
        compound_count: int | None = ...,  # type: ignore[assignment]
        scientist: str | None = ...,  # type: ignore[assignment]
        collection_id: uuid.UUID | None = ...,  # type: ignore[assignment]
    ) -> None:
        """Update mutable fields. Uses sentinel ``...`` for optional nullable fields."""
        if name is not None:
            self.name = _validated_name(name)
        if group_type is not ...:
            self.group_type = _validated_group_type(group_type)
        if description is not ...:
            self.description = description
        if state is not ...:
            self.state = _validated_text(state, max_len=MAX_STATE_LEN, label="state")
        if storage_location_id is not ...:
            self.storage_location_id = storage_location_id
        if initial_volume_ul is not ...:
            self.initial_volume_ul = _non_negative(initial_volume_ul, label="initial_volume_ul")
        if initial_concentration_mm is not ...:
            self.initial_concentration_mm = _non_negative(
                initial_concentration_mm, label="initial_concentration_mm"
            )
        if compound_count is not ...:
            self.compound_count = _non_negative(compound_count, label="compound_count")
        if scientist is not ...:
            self.scientist = _validated_text(
                scientist, max_len=MAX_SCIENTIST_LEN, label="scientist"
            )
        if collection_id is not ...:
            self.collection_id = collection_id
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
