"""MoleculeIdentifier — owned entity mapping external IDs to a molecule."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.shared.errors import ValidationError


class MoleculeIdentifier:
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
    ) -> None:
        if not identifier or not identifier.strip():
            raise ValidationError("Identifier must not be empty")
        self.id = id or uuid.uuid4()
        self.molecule_id = molecule_id
        self.identifier = identifier.strip()
        self.identifier_type = identifier_type
        self.source = source
        self.registered_by = registered_by
        self.created_at = created_at or datetime.now(UTC)

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

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MoleculeIdentifier):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __repr__(self) -> str:
        return f"MoleculeIdentifier(id={self.id}, identifier={self.identifier!r})"
