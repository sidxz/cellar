"""Repository protocols for Screening & Assay entities."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from chem_vault.domain.screening_assay.activity_types import AggregatedReadout
from chem_vault.domain.screening_assay.dose_response_curve import DoseResponseCurve
from chem_vault.domain.screening_assay.plate_template import PlateTemplate
from chem_vault.domain.screening_assay.protocol import Protocol as AssayProtocol
from chem_vault.domain.screening_assay.readout_data import ReadoutData
from chem_vault.domain.screening_assay.run import Run
from chem_vault.domain.screening_assay.target import Target


@runtime_checkable
class ProtocolRepository(Protocol):
    """Repository for AssayProtocol aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> AssayProtocol | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> AssayProtocol | None: ...
    async def find_by_ids(
        self, workspace_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> list[AssayProtocol]: ...
    async def find_active_by_lineage(
        self, workspace_id: uuid.UUID, parent_protocol_id: uuid.UUID
    ) -> AssayProtocol | None: ...
    async def find_by_name(
        self, workspace_id: uuid.UUID, name: str
    ) -> AssayProtocol | None: ...
    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[AssayProtocol]: ...
    async def add_to_project(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, project_id: uuid.UUID
    ) -> None: ...
    async def remove_from_project(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, project_id: uuid.UUID
    ) -> None: ...
    async def find_by_project(
        self, workspace_id: uuid.UUID, project_id: uuid.UUID
    ) -> list: ...
    async def find_project_ids(self, workspace_id: uuid.UUID, protocol_id: uuid.UUID) -> list[uuid.UUID]: ...
    async def save(self, aggregate: AssayProtocol) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@runtime_checkable
class TargetRepository(Protocol):
    """Repository for Target entities."""

    async def find_by_id(self, id: uuid.UUID) -> Target | None: ...
    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[Target]: ...
    async def save(self, entity: Target) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@runtime_checkable
class PlateTemplateRepository(Protocol):
    """Repository for PlateTemplate entities."""

    async def find_by_id(self, id: uuid.UUID) -> PlateTemplate | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> PlateTemplate | None: ...
    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[PlateTemplate]: ...
    async def save(self, entity: PlateTemplate) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...
    async def count_references(self, workspace_id: uuid.UUID, template_id: uuid.UUID) -> int: ...


@runtime_checkable
class RunRepository(Protocol):
    """Repository for Run aggregates.

    Also satisfies ``RunLockChecker`` protocol via ``is_locked()``.
    """

    async def find_by_id(self, id: uuid.UUID) -> Run | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Run | None: ...
    async def find_by_protocol(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> list[Run]: ...
    async def find_children(
        self, workspace_id: uuid.UUID, parent_run_id: uuid.UUID
    ) -> list[Run]: ...
    async def save(self, aggregate: Run) -> None: ...
    async def is_locked(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> bool: ...


@runtime_checkable
class ReadoutDataRepository(Protocol):
    """Repository for ReadoutData entities."""

    async def find_by_id(self, id: uuid.UUID) -> ReadoutData | None: ...
    async def find_by_run(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID
    ) -> list[ReadoutData]: ...
    async def find_by_molecule(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[ReadoutData]: ...
    async def find_aggregated_by_molecules(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        readout_definition_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, dict[uuid.UUID, AggregatedReadout]]: ...
    async def find_by_molecule_and_definition(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, readout_definition_id: uuid.UUID
    ) -> list: ...
    async def find_grouped_by_condition(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, condition_name: str
    ) -> list: ...
    async def get_molecule_counts(
        self, workspace_id: uuid.UUID, run_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]: ...
    async def delete_computed_for_run(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID
    ) -> int: ...
    async def save(self, entity: ReadoutData) -> None: ...
    async def save_bulk(self, entities: list[ReadoutData]) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@runtime_checkable
class CompoundFlagRepository(Protocol):
    """Repository for CompoundFlag entities."""

    async def list_by_protocol(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> list: ...
    async def save(self, flag: object) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, flag_id: uuid.UUID) -> None: ...


@runtime_checkable
class DoseResponseCurveRepository(Protocol):
    """Repository for DoseResponseCurve entities."""

    async def find_by_id(self, id: uuid.UUID) -> DoseResponseCurve | None: ...
    async def find_by_run(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID
    ) -> list[DoseResponseCurve]: ...
    async def find_by_molecule(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[DoseResponseCurve]: ...
    async def find_best_curves_for_molecules(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        protocol_ids: list[uuid.UUID] | None = None,
    ) -> dict[uuid.UUID, dict[uuid.UUID, DoseResponseCurve]]: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> DoseResponseCurve | None: ...
    async def save(self, entity: DoseResponseCurve) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...
    async def delete_by_run(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> None: ...
