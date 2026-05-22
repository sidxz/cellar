"""BatchIdentifier — owned entity mapping external/foreign IDs to a Batch.

Mirrors MoleculeIdentifier. Used to resolve imports that reference a batch
by its name in some other system (CDD Vault lot id, vendor lot, partner
batch number, etc.).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from cellar.domain.shared.entity import Entity
from cellar.domain.shared.errors import ValidationError


class BatchIdentifier(Entity):
    """An external identifier mapped to a batch. Fully owned by the parent Batch."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        batch_id: uuid.UUID,
        identifier: str,
        identifier_type: str,
        source: str,
        registered_by: uuid.UUID,
        derived_from_molecule_identifier_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        if not identifier or not identifier.strip():
            raise ValidationError("Identifier must not be empty")
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)
        self.batch_id = batch_id
        self.identifier = identifier.strip()
        self.identifier_type = identifier_type
        self.source = source
        self.registered_by = registered_by
        self.derived_from_molecule_identifier_id = derived_from_molecule_identifier_id

    @classmethod
    def create(
        cls,
        *,
        batch_id: uuid.UUID,
        identifier: str,
        identifier_type: str,
        source: str,
        registered_by: uuid.UUID,
        derived_from_molecule_identifier_id: uuid.UUID | None = None,
    ) -> BatchIdentifier:
        return cls(
            batch_id=batch_id,
            identifier=identifier,
            identifier_type=identifier_type,
            source=source,
            registered_by=registered_by,
            derived_from_molecule_identifier_id=derived_from_molecule_identifier_id,
        )
