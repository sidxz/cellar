"""MergeEvent — immutable audit/provenance record of a molecule merge."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from cellar.domain.chemical_registration.enums import MergeReason
from cellar.domain.shared.entity import Entity
from cellar.domain.shared.errors import ValidationError


class MergeEvent(Entity):
    """Insert-only record of a molecule merge operation.

    Not an AggregateRoot — no version, no domain events, append-only.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
        reason: MergeReason,
        merged_by: uuid.UUID,
        snapshot: dict[str, Any],
        disclosure_request_id: uuid.UUID | None = None,
        notes: str | None = None,
        merged_at: datetime | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)
        self.workspace_id = workspace_id
        self.source_molecule_id = source_molecule_id
        self.target_molecule_id = target_molecule_id
        self.reason = reason
        self.merged_by = merged_by
        self.snapshot = snapshot
        self.disclosure_request_id = disclosure_request_id
        self.notes = notes
        self.merged_at = merged_at or datetime.now(UTC)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
        reason: MergeReason,
        merged_by: uuid.UUID,
        snapshot: dict[str, Any],
        disclosure_request_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> MergeEvent:
        """Create a new MergeEvent with invariant validation."""
        if source_molecule_id == target_molecule_id:
            raise ValidationError("A molecule cannot merge into itself")

        return cls(
            workspace_id=workspace_id,
            source_molecule_id=source_molecule_id,
            target_molecule_id=target_molecule_id,
            reason=reason,
            merged_by=merged_by,
            snapshot=snapshot,
            disclosure_request_id=disclosure_request_id,
            notes=notes,
        )
