"""Repository protocols for chemical registration entities."""

from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable

from cellar.domain.chemical_registration.bulk_disclosure import BulkDisclosure
from cellar.domain.chemical_registration.bulk_registration import (
    BulkRegistration,
    BulkRegistrationItem,
)
from cellar.domain.chemical_registration.cdd_molecule_import import CddMoleculeImport
from cellar.domain.chemical_registration.disclosure_request import DisclosureRequest
from cellar.domain.chemical_registration.merge_event import MergeEvent
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.molecule_relationship import MoleculeRelationship
from cellar.domain.chemical_registration.synthesis_route import SynthesisRoute
from cellar.domain.shared.value_objects import RegistrationNumber


@runtime_checkable
class MoleculeRepository(Protocol):
    """Repository for Molecule aggregates."""

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Molecule | None: ...

    async def find_by_ids(
        self, workspace_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> list[Molecule]: ...

    async def find_by_inchi_key(
        self, workspace_id: uuid.UUID, inchi_key: str
    ) -> Molecule | None: ...

    async def find_by_registration_number(
        self, workspace_id: uuid.UUID, reg_number: str
    ) -> Molecule | None: ...

    async def find_by_identifier(
        self, workspace_id: uuid.UUID, identifier: str
    ) -> Molecule | None: ...

    async def find_undisclosed_by_identifiers(
        self, workspace_id: uuid.UUID, identifiers: set[str]
    ) -> Molecule | None:
        """Find a single undisclosed molecule whose identifiers overlap with the given set.

        Returns None if no match or if identifiers map to multiple different molecules (ambiguous).
        Only matches molecules with structure_status == UNDISCLOSED and no tombstone (merged_into_id is None).
        """
        ...

    async def find_identifiers_in_workspace(
        self, workspace_id: uuid.UUID, identifiers: set[str]
    ) -> dict[str, uuid.UUID]: ...

    async def find_active(
        self,
        workspace_id: uuid.UUID,
        *,
        filters: dict[str, Any] | None = None,
        search_term: str | None = None,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> list[Molecule]: ...

    async def next_registration_number(self, workspace_id: uuid.UUID) -> RegistrationNumber: ...

    async def save(self, aggregate: Molecule) -> None: ...


@runtime_checkable
class MoleculeRelationshipRepository(Protocol):
    """Repository for MoleculeRelationship entities."""


    async def find_by_source(
        self, workspace_id: uuid.UUID, source_molecule_id: uuid.UUID
    ) -> list[MoleculeRelationship]: ...

    async def find_by_target(
        self, workspace_id: uuid.UUID, target_molecule_id: uuid.UUID
    ) -> list[MoleculeRelationship]: ...

    async def save(self, entity: MoleculeRelationship) -> None: ...

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@runtime_checkable
class DisclosureRequestRepository(Protocol):
    """Repository for DisclosureRequest aggregates."""

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> DisclosureRequest | None: ...
    async def find_by_molecule(
        self,
        workspace_id: uuid.UUID,
        molecule_id: uuid.UUID,
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> list[DisclosureRequest]: ...
    async def find_by_bulk_disclosure(
        self, workspace_id: uuid.UUID, bulk_disclosure_id: uuid.UUID
    ) -> list[DisclosureRequest]: ...
    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        status: str | None = None,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> list[DisclosureRequest]: ...
    async def save(self, aggregate: DisclosureRequest) -> None: ...


@runtime_checkable
class BulkDisclosureRepository(Protocol):
    """Repository for BulkDisclosure aggregates."""

    async def save(self, aggregate: BulkDisclosure) -> None: ...


@runtime_checkable
class MergeEventRepository(Protocol):
    """Repository for MergeEvent entities (insert-only, no versioning)."""

    async def find_by_source(
        self, workspace_id: uuid.UUID, source_molecule_id: uuid.UUID
    ) -> list[MergeEvent]: ...
    async def find_by_target(
        self, workspace_id: uuid.UUID, target_molecule_id: uuid.UUID
    ) -> list[MergeEvent]: ...
    async def find_by_molecule(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[MergeEvent]: ...
    async def save(self, entity: MergeEvent) -> None: ...


@runtime_checkable
class BulkRegistrationRepository(Protocol):
    """Repository for BulkRegistration aggregates.

    save() is responsible for persisting both the aggregate counters and any
    pending per-row items collected via BulkRegistration.record_item(...).
    """

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> BulkRegistration | None: ...
    async def find_by_workflow_id_in_workspace(
        self, workspace_id: uuid.UUID, workflow_id: str
    ) -> BulkRegistration | None: ...
    async def find_by_workspace(self, workspace_id: uuid.UUID) -> list[BulkRegistration]: ...
    async def save(self, aggregate: BulkRegistration) -> None: ...
    async def insert_items(self, items: list[BulkRegistrationItem]) -> None:
        """Bulk-insert per-row items. Idempotent on (bulk_registration_id, row_index)."""
        ...


@runtime_checkable
class CddMoleculeImportRepository(Protocol):
    """Repository for CddMoleculeImport aggregates."""

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> CddMoleculeImport | None: ...
    async def find_by_workflow_id_in_workspace(
        self, workspace_id: uuid.UUID, workflow_id: str
    ) -> CddMoleculeImport | None: ...
    async def find_by_workspace(self, workspace_id: uuid.UUID) -> list[CddMoleculeImport]: ...
    async def save(self, aggregate: CddMoleculeImport) -> None: ...


@runtime_checkable
class SynthesisRouteRepository(Protocol):
    """Repository for SynthesisRoute aggregates."""

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> SynthesisRoute | None: ...
    async def find_by_target_molecule(
        self, workspace_id: uuid.UUID, target_molecule_id: uuid.UUID
    ) -> list[SynthesisRoute]: ...
    async def find_preferred(
        self, workspace_id: uuid.UUID, target_molecule_id: uuid.UUID
    ) -> SynthesisRoute | None: ...
    async def save(self, aggregate: SynthesisRoute) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...
