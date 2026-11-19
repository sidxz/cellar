"""MoleculeIdentifier — owned entity mapping external IDs to a molecule."""

from __future__ import annotations

import uuid
from datetime import datetime

from cellar.domain.shared.entity import Entity
from cellar.domain.shared.errors import ValidationError


def normalize_identifier(text: str) -> str:
    """The text a compound stores for an identifier: surrounding whitespace dropped,
    a vault's trailing non-breaking space included. Compare with this, not the raw text."""
    return text.strip()


class MoleculeIdentifier(Entity):
    """An external/vendor identifier mapped to a molecule.

    Fully owned by the parent Molecule aggregate.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        molecule_id: uuid.UUID,
        identifier: str,
        identifier_type: str,
        source: str,
        registered_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        if not identifier or not normalize_identifier(identifier):
            raise ValidationError("Identifier must not be empty")
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)
        self.molecule_id = molecule_id
        self.identifier = normalize_identifier(identifier)
        self.identifier_type = identifier_type
        self.source = source
        self.registered_by = registered_by

    @classmethod
    def create(
        cls,
        *,
        molecule_id: uuid.UUID,
        identifier: str,
        identifier_type: str,
        source: str,
        registered_by: uuid.UUID,
    ) -> MoleculeIdentifier:
        return cls(
            molecule_id=molecule_id,
            identifier=identifier,
            identifier_type=identifier_type,
            source=source,
            registered_by=registered_by,
        )
