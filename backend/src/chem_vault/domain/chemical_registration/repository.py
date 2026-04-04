"""Repository protocols for chemical registration entities."""

from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable

from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.chemical_registration.molecule_relationship import MoleculeRelationship
from chem_vault.domain.shared.value_objects import RegistrationNumber


@runtime_checkable
class MoleculeRepository(Protocol):
    """Repository for Molecule aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> Molecule | None: ...

    async def find_by_inchi_key(
        self, workspace_id: uuid.UUID, inchi_key: str
    ) -> Molecule | None: ...

    async def find_by_registration_number(
        self, workspace_id: uuid.UUID, reg_number: str
    ) -> Molecule | None: ...

    async def find_by_identifier(
        self, workspace_id: uuid.UUID, identifier: str
    ) -> Molecule | None: ...

    async def find_active(
        self, workspace_id: uuid.UUID, *, filters: dict[str, Any] | None = None
    ) -> list[Molecule]: ...

    async def next_registration_number(
        self, workspace_id: uuid.UUID
    ) -> RegistrationNumber: ...

    async def save(self, aggregate: Molecule) -> None: ...


@runtime_checkable
class MoleculeRelationshipRepository(Protocol):
    """Repository for MoleculeRelationship entities."""

    async def find_by_id(self, id: uuid.UUID) -> MoleculeRelationship | None: ...

    async def find_by_source(
        self, source_molecule_id: uuid.UUID
    ) -> list[MoleculeRelationship]: ...

    async def find_by_target(
        self, target_molecule_id: uuid.UUID
    ) -> list[MoleculeRelationship]: ...

    async def save(self, entity: MoleculeRelationship) -> None: ...

    async def delete(self, id: uuid.UUID) -> None: ...
