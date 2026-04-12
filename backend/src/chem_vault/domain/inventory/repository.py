"""Repository protocols for inventory entities."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from chem_vault.application.shared.pagination import PageResult
from chem_vault.domain.inventory.batch import Batch
from chem_vault.domain.inventory.import_template import ImportTemplate
from chem_vault.domain.inventory.registered_plate import RegisteredPlate
from chem_vault.domain.inventory.sample import Sample
from chem_vault.domain.inventory.sample_request import SampleRequest
from chem_vault.domain.inventory.shipment import Shipment
from chem_vault.domain.inventory.storage_location import StorageLocation
from chem_vault.domain.inventory.synthesis_request import SynthesisRequest
from chem_vault.domain.shared.value_objects import BatchNumber


@runtime_checkable
class BatchRepository(Protocol):
    """Repository for Batch aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> Batch | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Batch | None: ...
    async def find_by_molecule(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[Batch]: ...
    async def find_by_batch_number(
        self, workspace_id: uuid.UUID, batch_number: str
    ) -> Batch | None: ...
    async def next_batch_number(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> BatchNumber: ...
    async def list_global(
        self,
        workspace_id: uuid.UUID,
        *,
        search: str | None = None,
        sources: list[str] | None = None,
        expiring_within_days: int | None = None,
        cursor: uuid.UUID | None = None,
        limit: int = 50,
    ) -> PageResult[dict]: ...
    async def save(self, aggregate: Batch) -> None: ...


@runtime_checkable
class SampleRepository(Protocol):
    """Repository for Sample aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> Sample | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Sample | None: ...
    async def find_by_batch(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> list[Sample]: ...
    async def find_by_location(
        self, workspace_id: uuid.UUID, location_id: uuid.UUID
    ) -> list[Sample]: ...
    async def find_by_barcode(
        self, workspace_id: uuid.UUID, barcode: str
    ) -> Sample | None: ...
    async def find_low_stock(self, workspace_id: uuid.UUID) -> list[Sample]: ...
    async def save(self, aggregate: Sample) -> None: ...


@runtime_checkable
class StorageLocationRepository(Protocol):
    """Repository for StorageLocation entities."""

    async def find_by_id(self, id: uuid.UUID) -> StorageLocation | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> StorageLocation | None: ...
    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[StorageLocation]: ...
    async def find_children(
        self, workspace_id: uuid.UUID, parent_id: uuid.UUID
    ) -> list[StorageLocation]: ...
    async def save(self, entity: StorageLocation) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@runtime_checkable
class SampleRequestRepository(Protocol):
    """Repository for SampleRequest aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> SampleRequest | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> SampleRequest | None: ...
    async def find_by_workspace(
        self, workspace_id: uuid.UUID, *, status: str | None = None
    ) -> list[SampleRequest]: ...
    async def save(self, aggregate: SampleRequest) -> None: ...


@runtime_checkable
class ShipmentRepository(Protocol):
    """Repository for Shipment aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> Shipment | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Shipment | None: ...
    async def find_by_workspace(
        self, workspace_id: uuid.UUID, *, status: str | None = None
    ) -> list[Shipment]: ...
    async def save(self, aggregate: Shipment) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@runtime_checkable
class SynthesisRequestRepository(Protocol):
    """Repository for SynthesisRequest aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> SynthesisRequest | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> SynthesisRequest | None: ...
    async def find_by_workspace(
        self, workspace_id: uuid.UUID, *, status: str | None = None
    ) -> list[SynthesisRequest]: ...
    async def find_by_molecule(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[SynthesisRequest]: ...
    async def save(self, aggregate: SynthesisRequest) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@runtime_checkable
class RegisteredPlateRepository(Protocol):
    """Repository for RegisteredPlate aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> RegisteredPlate | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> RegisteredPlate | None: ...
    async def find_by_barcode(
        self, workspace_id: uuid.UUID, barcode: str
    ) -> RegisteredPlate | None: ...
    async def find_by_location(
        self, workspace_id: uuid.UUID, storage_location_id: uuid.UUID
    ) -> list[RegisteredPlate]: ...
    async def find_children(
        self, workspace_id: uuid.UUID, parent_plate_id: uuid.UUID
    ) -> list[RegisteredPlate]: ...
    async def find_by_project(
        self, workspace_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[RegisteredPlate]: ...
    async def search(
        self,
        workspace_id: uuid.UUID,
        *,
        barcode: str | None = None,
        plate_label: str | None = None,
        plate_type: str | None = None,
        status: str | None = None,
        format: str | None = None,
        storage_location_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> list[RegisteredPlate]: ...
    async def save(self, aggregate: RegisteredPlate) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@runtime_checkable
class ImportTemplateRepository(Protocol):
    """Repository for ImportTemplate entities."""

    async def find_by_id(self, id: uuid.UUID) -> ImportTemplate | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> ImportTemplate | None: ...
    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[ImportTemplate]: ...
    async def save(self, entity: ImportTemplate) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...
