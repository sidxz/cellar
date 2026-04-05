"""Repository protocols for chemical registration entities."""

from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable

from chem_vault.domain.chemical_registration.bulk_disclosure import BulkDisclosure
from chem_vault.domain.chemical_registration.bulk_registration import BulkRegistration
from chem_vault.domain.chemical_registration.disclosure_request import DisclosureRequest
from chem_vault.domain.chemical_registration.merge_event import MergeEvent
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
        self,
        workspace_id: uuid.UUID,
        *,
        filters: dict[str, Any] | None = None,
        search_term: str | None = None,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> list[Molecule]: ...

    async def next_registration_number(
        self, workspace_id: uuid.UUID
    ) -> RegistrationNumber: ...

    async def search_substructure(
        self, workspace_id: uuid.UUID, smarts: str
    ) -> list[Molecule]: ...

    async def search_similarity(
        self, workspace_id: uuid.UUID, smiles: str, threshold: float = 0.7
    ) -> list[Molecule]: ...

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


@runtime_checkable
class DisclosureRequestRepository(Protocol):
    """Repository for DisclosureRequest aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> DisclosureRequest | None: ...
    async def find_by_molecule(self, molecule_id: uuid.UUID) -> list[DisclosureRequest]: ...
    async def find_by_bulk_disclosure(self, bulk_disclosure_id: uuid.UUID) -> list[DisclosureRequest]: ...
    async def save(self, aggregate: DisclosureRequest) -> None: ...


@runtime_checkable
class BulkDisclosureRepository(Protocol):
    """Repository for BulkDisclosure aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> BulkDisclosure | None: ...
    async def save(self, aggregate: BulkDisclosure) -> None: ...


@runtime_checkable
class MergeEventRepository(Protocol):
    """Repository for MergeEvent entities (insert-only, no versioning)."""

    async def find_by_id(self, id: uuid.UUID) -> MergeEvent | None: ...
    async def find_by_source(self, source_molecule_id: uuid.UUID) -> list[MergeEvent]: ...
    async def find_by_target(self, target_molecule_id: uuid.UUID) -> list[MergeEvent]: ...
    async def find_by_molecule(self, molecule_id: uuid.UUID) -> list[MergeEvent]: ...
    async def save(self, entity: MergeEvent) -> None: ...


@runtime_checkable
class BulkRegistrationRepository(Protocol):
    """Repository for BulkRegistration aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> BulkRegistration | None: ...
    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[BulkRegistration]: ...
    async def save(self, aggregate: BulkRegistration) -> None: ...
