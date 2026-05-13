"""MoleculeRelationship — standalone entity capturing semantic relationships."""

from __future__ import annotations

import uuid
from datetime import datetime

from cellar.domain.chemical_registration.enums import RelationshipType
from cellar.domain.shared.entity import Entity
from cellar.domain.shared.errors import ValidationError


class MoleculeRelationship(Entity):
    """Semantic relationship between two molecules.

    Standalone entity — not inside either molecule's aggregate boundary.
    Neither molecule needs to know about relationships to enforce its own invariants.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
        relationship_type: RelationshipType,
        notes: str | None = None,
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)
        if source_molecule_id == target_molecule_id:
            raise ValidationError("A molecule cannot have a relationship with itself")
        self.workspace_id = workspace_id
        self.source_molecule_id = source_molecule_id
        self.target_molecule_id = target_molecule_id
        self.relationship_type = relationship_type
        self.notes = notes
        self.created_by = created_by

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
        relationship_type: RelationshipType,
        notes: str | None = None,
        created_by: uuid.UUID,
    ) -> MoleculeRelationship:
        return cls(
            workspace_id=workspace_id,
            source_molecule_id=source_molecule_id,
            target_molecule_id=target_molecule_id,
            relationship_type=relationship_type,
            notes=notes,
            created_by=created_by,
        )
