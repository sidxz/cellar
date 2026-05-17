"""Repository protocols for Screening & Assay entities."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Protocol, runtime_checkable

from cellar.domain.screening_assay.activity_types import AggregatedReadout
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.plate_template import PlateTemplate
from cellar.domain.screening_assay.protocol import Protocol as AssayProtocol
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.run import Run
from cellar.domain.screening_assay.run_import_template import RunImportTemplate
from cellar.domain.screening_assay.run_scope import RunScope
from cellar.domain.screening_assay.target import Target


@runtime_checkable
class ProtocolRepository(Protocol):
    """Repository for AssayProtocol aggregates."""

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> AssayProtocol | None: ...
    async def find_by_ids(
        self, workspace_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> list[AssayProtocol]: ...
    async def find_active_by_lineage(
        self, workspace_id: uuid.UUID, parent_protocol_id: uuid.UUID
    ) -> AssayProtocol | None: ...
    async def find_by_name(self, workspace_id: uuid.UUID, name: str) -> AssayProtocol | None: ...
    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> list[AssayProtocol]: ...
    async def add_to_project(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, project_id: uuid.UUID
    ) -> None: ...
    async def remove_from_project(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, project_id: uuid.UUID
    ) -> None: ...
    async def find_by_project(
        self,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> list: ...
    async def find_protocol_ids_in_projects(
        self, workspace_id: uuid.UUID, project_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        """Return the set of protocol IDs linked to ANY of the given projects.

        Used by pickers (e.g. the search panel) to scope option lists to the
        union of protocols across the user's selected projects.
        """
        ...

    async def find_project_ids(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> list[uuid.UUID]: ...
    async def save(self, aggregate: AssayProtocol) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@runtime_checkable
class TargetRepository(Protocol):
    """Repository for Target entities."""

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> list[Target]: ...
    async def save(self, entity: Target) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@runtime_checkable
class PlateTemplateRepository(Protocol):
    """Repository for PlateTemplate entities."""

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> PlateTemplate | None: ...
    async def find_by_workspace(self, workspace_id: uuid.UUID) -> list[PlateTemplate]: ...
    async def save(self, entity: PlateTemplate) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...
    async def count_references(self, workspace_id: uuid.UUID, template_id: uuid.UUID) -> int: ...


@runtime_checkable
class RunRepository(Protocol):
    """Repository for Run aggregates.

    Also satisfies ``RunLockChecker`` protocol via ``is_locked()``.
    """

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Run | None: ...
    async def find_by_ids(
        self, workspace_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Run]:
        """Bulk-fetch runs by id, scoped to workspace.

        Returns ``{run.id: run, ...}`` so adapters can join ``DoseResponseCurve``
        rows back to their owning runs in O(1) without an N+1 over
        ``find_by_id_in_workspace``. Missing ids are silently dropped.
        """
        ...

    async def find_by_protocol(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> list[Run]: ...
    async def aggregate_stats_by_protocol(
        self, workspace_id: uuid.UUID
    ) -> dict[uuid.UUID, tuple[int, "date | None"]]: ...
    async def find_children(
        self, workspace_id: uuid.UUID, parent_run_id: uuid.UUID
    ) -> list[Run]: ...
    async def save(self, aggregate: Run) -> None: ...
    async def is_locked(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> bool: ...
    async def delete(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> None: ...


@runtime_checkable
class ReadoutDataRepository(Protocol):
    """Repository for ReadoutData entities."""

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
        specs: list[tuple[uuid.UUID, str | None]],
    ) -> dict[uuid.UUID, dict[tuple[uuid.UUID, str | None], AggregatedReadout]]: ...
    async def find_by_molecule_and_definition(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, readout_definition_id: uuid.UUID
    ) -> list: ...
    async def find_grouped_by_condition(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, condition_name: str
    ) -> list: ...
    async def get_molecule_counts(
        self, workspace_id: uuid.UUID, run_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]: ...
    async def delete_computed_for_run(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> int: ...
    async def delete_for_run(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> int: ...
    async def save(self, entity: ReadoutData) -> None: ...
    async def save_bulk(self, entities: list[ReadoutData]) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@runtime_checkable
class CompoundFlagRepository(Protocol):
    """Repository for CompoundFlag entities."""

    async def list_by_protocol(self, workspace_id: uuid.UUID, protocol_id: uuid.UUID) -> list: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> object | None: ...
    async def save(self, flag: object) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, flag_id: uuid.UUID) -> None: ...


@runtime_checkable
class DoseResponseCurveRepository(Protocol):
    """Repository for DoseResponseCurve entities."""

    async def find_by_run(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID
    ) -> list[DoseResponseCurve]: ...
    async def find_by_molecule(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[DoseResponseCurve]: ...
    async def find_by_ids(
        self, workspace_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> list[DoseResponseCurve]: ...
    async def find_best_curves_for_molecules(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        readout_definition_ids: list[uuid.UUID] | None = None,
    ) -> dict[uuid.UUID, dict[uuid.UUID, DoseResponseCurve]]: ...
    async def find_all_curves_for_molecules(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        readout_definition_ids: list[uuid.UUID] | None = None,
        run_scope: RunScope | None = None,
    ) -> dict[uuid.UUID, dict[uuid.UUID, list[DoseResponseCurve]]]:
        """Return ALL curves keyed by (molecule_id, readout_definition_id).

        Returns ``{molecule_id: {readout_definition_id: [curves sorted by run_date desc]}}``.
        Used by the search aggregator and Activity tabs to feed multi-run
        selection rules. ``run_scope=None`` means all runs.
        """
        ...

    async def count_distinct_protocols_per_molecule(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        project_id: uuid.UUID | None = None,
    ) -> dict[uuid.UUID, int]:
        """Return distinct protocol count per molecule.

        For each molecule_id in ``molecule_ids``, count how many distinct
        protocols that molecule has a dose-response curve in.  When
        ``project_id`` is provided, only protocols linked to that project
        are counted.  Molecules with no curves are returned with count=0.
        """
        ...

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> DoseResponseCurve | None: ...
    async def save(self, entity: DoseResponseCurve) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...
    async def delete_by_run(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> None: ...


@runtime_checkable
class RunImportTemplateRepository(Protocol):
    """Repository for RunImportTemplate entities."""

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> RunImportTemplate | None: ...
    async def find_by_workspace(self, workspace_id: uuid.UUID) -> list[RunImportTemplate]: ...
    async def save(self, entity: RunImportTemplate) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...
