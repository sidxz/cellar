"""MoleculeActivityService -- read-model crossing Molecule and Screening boundaries.

This service provides activity data for molecule detail pages and enriched
search results. It queries readout data and dose-response curves grouped
by protocol.
"""

from __future__ import annotations

import uuid
from typing import Any

from chem_vault.application.screening import _condense_raw_data
from chem_vault.domain.screening_assay.activity_types import (
    ActivitySummary,
    ActivityValue,
    ProtocolActivitySummary,
)
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.repository import (
    DoseResponseCurveRepository,
    ProtocolRepository,
    ReadoutDataRepository,
)


class MoleculeActivityService:
    """Read-model service for molecule activity queries."""

    def __init__(
        self,
        uow: UnitOfWork,
        readout_repo: ReadoutDataRepository,
        curve_repo: DoseResponseCurveRepository,
        protocol_repo: ProtocolRepository,
    ) -> None:
        self._uow = uow
        self._readout_repo = readout_repo
        self._curve_repo = curve_repo
        self._protocol_repo = protocol_repo

    async def get_activity_summary(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> ActivitySummary:
        """Full activity summary for molecule detail page.
        Groups dose-response curves by protocol."""
        if self._uow.is_active:
            return await self._get_activity_summary(workspace_id, molecule_id)
        async with self._uow:
            return await self._get_activity_summary(workspace_id, molecule_id)

    async def _get_activity_summary(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> ActivitySummary:
        curves = await self._curve_repo.find_by_molecule(workspace_id, molecule_id)

        # Group curves by protocol
        curves_by_proto: dict[uuid.UUID, list[dict[str, Any]]] = {}
        proto_ids: set[uuid.UUID] = set()
        for curve in curves:
            proto_ids.add(curve.protocol_id)
            # Condense raw_data to [{x, y}] for sparkline rendering
            data_points = None
            if curve.raw_data and isinstance(curve.raw_data, list):
                data_points = _condense_raw_data(curve.raw_data)

            curves_by_proto.setdefault(curve.protocol_id, []).append(
                {
                    "curve_type": curve.curve_type.value,
                    "fitted_value": curve.fitted_value,
                    "fitted_unit": curve.fitted_unit,
                    "r_squared": curve.r_squared,
                    "hill_slope": curve.hill_slope,
                    "top": curve.top,
                    "bottom": curve.bottom,
                    "num_points": curve.num_points,
                    "curve_class": curve.curve_class.value if curve.curve_class else None,
                    "data_points": data_points,
                }
            )

        # Fetch protocol metadata (single query)
        protocols_by_id: dict[uuid.UUID, tuple[str, str]] = {}
        if proto_ids:
            protos = await self._protocol_repo.find_by_ids(workspace_id, list(proto_ids))
            for proto in protos:
                protocols_by_id[proto.id] = (proto.name, proto.protocol_type.value)

        summaries: list[ProtocolActivitySummary] = []
        for pid in sorted(proto_ids):
            name, ptype = protocols_by_id.get(pid, ("Unknown", "unknown"))
            summaries.append(
                ProtocolActivitySummary(
                    protocol_id=pid,
                    protocol_name=name,
                    protocol_type=ptype,
                    best_curves=curves_by_proto.get(pid, []),
                )
            )

        return ActivitySummary(molecule_id=molecule_id, protocols=summaries)

    async def enrich_molecules(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        protocol_columns: list[str],
    ) -> dict[uuid.UUID, dict[str, ActivityValue]]:
        """Batch enrichment for search results.

        protocol_columns format:
          - "rd:{readout_definition_id}" -- aggregated readout value
          - "drc:{protocol_id}:{curve_type}" -- best dose-response curve
        """
        if not molecule_ids or not protocol_columns:
            return {}

        if self._uow.is_active:
            return await self._enrich_molecules(workspace_id, molecule_ids, protocol_columns)
        async with self._uow:
            return await self._enrich_molecules(workspace_id, molecule_ids, protocol_columns)

    async def _enrich_molecules(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        protocol_columns: list[str],
    ) -> dict[uuid.UUID, dict[str, ActivityValue]]:
        # Parse column specs
        rd_def_ids: list[uuid.UUID] = []
        drc_specs: list[tuple[uuid.UUID, str]] = []  # (protocol_id, curve_type)
        for col in protocol_columns:
            if col.startswith("rd:"):
                rd_def_ids.append(uuid.UUID(col[3:]))
            elif col.startswith("drc:"):
                parts = col.split(":")
                drc_specs.append((uuid.UUID(parts[1]), parts[2]))

        # Fetch aggregated readouts
        rd_data: dict[uuid.UUID, dict[uuid.UUID, object]] = {}
        if rd_def_ids:
            rd_data = await self._readout_repo.find_aggregated_by_molecules(
                workspace_id, molecule_ids, rd_def_ids
            )

        # Fetch best curves
        curve_proto_ids = list({spec[0] for spec in drc_specs})
        curve_data: dict[uuid.UUID, dict[uuid.UUID, object]] = {}
        if curve_proto_ids:
            curve_data = await self._curve_repo.find_best_curves_for_molecules(
                workspace_id, molecule_ids, curve_proto_ids
            )

        # Build result
        result: dict[uuid.UUID, dict[str, ActivityValue]] = {}
        for mol_id in molecule_ids:
            mol_activity: dict[str, ActivityValue] = {}

            # Readout columns
            mol_rds = rd_data.get(mol_id, {})
            for rd_def_id in rd_def_ids:
                col_key = f"rd:{rd_def_id}"
                agg = mol_rds.get(rd_def_id)
                if agg:
                    mol_activity[col_key] = ActivityValue(
                        value=agg.value,
                        qualifier=agg.qualifier,
                        unit=agg.unit,
                        source="readout",
                        data_point_count=agg.data_point_count,
                    )

            # Dose-response columns
            mol_curves = curve_data.get(mol_id, {})
            for proto_id, curve_type in drc_specs:
                col_key = f"drc:{proto_id}:{curve_type}"
                curve = mol_curves.get(proto_id)
                if curve and curve.curve_type.value == curve_type:
                    mol_activity[col_key] = ActivityValue(
                        value=curve.fitted_value,
                        qualifier=None,
                        unit=curve.fitted_unit,
                        source="dose_response",
                        curve_type=curve.curve_type.value,
                        r_squared=curve.r_squared,
                        data_point_count=curve.num_points,
                    )

            if mol_activity:
                result[mol_id] = mol_activity

        return result
