"""MoleculeActivityService -- read-model crossing Molecule and Screening boundaries.

This service provides activity data for molecule detail pages and enriched
search results. It queries readout data and dose-response curves grouped
by protocol.
"""

from __future__ import annotations

import uuid
from typing import Any

from cellar.application.screening import _condense_raw_data
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.activity_types import (
    ActivitySummary,
    ActivityValue,
    AggregatedReadout,
    CurveParams,
    ProtocolActivitySummary,
)
from cellar.domain.screening_assay.curve_fitting import InterceptValue
from cellar.domain.screening_assay.repository import (
    DoseResponseCurveRepository,
    ProtocolRepository,
    ReadoutDataRepository,
)


def _serialize_intercept_values(
    values: list[InterceptValue] | None,
) -> list[dict[str, Any]]:
    """Flatten domain ``InterceptValue`` objects into wire-shape dicts.

    Same shape consumed by ``CurveDetail.intercept_values`` on the molecule
    activity tab and ``ActivityValue.intercept_values`` on the search grid —
    one helper keeps the two payloads from drifting.
    """
    if not values:
        return []
    return [
        {
            "spec": {
                "kind": iv.spec.kind.value,
                "level": iv.spec.level,
                "basis": iv.spec.basis.value,
                "label": iv.spec.label,
            },
            "value": iv.value,
            "confidence_interval_low": iv.confidence_interval_low,
            "confidence_interval_high": iv.confidence_interval_high,
            "at_bound": iv.at_bound,
        }
        for iv in values
    ]


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

        # Fetch protocol metadata (single query) — used for display
        # name/type, dose_unit (for IC50 unit decoration), and the
        # protocol's declared intercept specs (per-Card column headers
        # on the molecule activity tab).
        protocols_by_id: dict[uuid.UUID, tuple[str, str, str]] = {}
        intercepts_by_proto: dict[uuid.UUID, list[dict[str, Any]]] = {}
        if proto_ids:
            protos = await self._protocol_repo.find_by_ids(workspace_id, list(proto_ids))
            for proto in protos:
                protocols_by_id[proto.id] = (
                    proto.name,
                    proto.protocol_type.value,
                    proto.dose_unit.value,
                )
                # Pull intercept specs from the first DR readout-def on the
                # protocol. Multi-DR (per-readout spec lists) is out of
                # scope for this round — see Spec §"Multi-readout-def".
                dr_def = next(
                    (
                        rd
                        for rd in proto.readout_definitions
                        if rd.dose_response_config is not None
                    ),
                    None,
                )
                if dr_def and dr_def.dose_response_config:
                    raw_intercepts = dr_def.dose_response_config.intercepts or []
                    intercepts_by_proto[proto.id] = [
                        {
                            "kind": spec.kind.value,
                            "level": spec.level,
                            "basis": spec.basis.value,
                            "label": spec.label,
                        }
                        for spec in raw_intercepts
                    ]

        for curve in curves:
            data_points = None
            if curve.raw_data and isinstance(curve.raw_data, list):
                data_points = _condense_raw_data(curve.raw_data)

            intercept_values_payload = _serialize_intercept_values(
                curve.intercept_values
            )

            unit = protocols_by_id.get(curve.protocol_id, ("", "", "uM"))[2]
            curves_by_proto.setdefault(curve.protocol_id, []).append(
                {
                    "curve_type": curve.curve_type.value,
                    "fitted_value": curve.fitted_value,
                    "fitted_unit": unit,
                    "r_squared": curve.r_squared,
                    "hill_slope": curve.hill_slope,
                    "top": curve.top,
                    "bottom": curve.bottom,
                    "num_points": curve.num_points,
                    "curve_class": curve.curve_class.value if curve.curve_class else None,
                    "data_points": data_points,
                    "intercept_values": intercept_values_payload,
                }
            )

        summaries: list[ProtocolActivitySummary] = []
        for pid in sorted(proto_ids):
            name, ptype, _unit = protocols_by_id.get(pid, ("Unknown", "unknown", "uM"))
            summaries.append(
                ProtocolActivitySummary(
                    protocol_id=pid,
                    protocol_name=name,
                    protocol_type=ptype,
                    best_curves=curves_by_proto.get(pid, []),
                    intercepts=intercepts_by_proto.get(pid, []),
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
          - "rd:{readout_definition_id}" -- aggregated raw readout value
          - "rd:{protocol_id}:{readout_definition_id}" -- same, with protocol scope
          - "rd:{protocol_id}:{readout_definition_id}:{normalization}" -- the
            named normalization layer of the readout (e.g. ``percent_inhibition``,
            ``z_score``). Without the suffix the raw layer is returned.
          - "drc:{readout_definition_id}" -- best dose-response curve for that
            DR readout-def. The readout-def identifies the column on multi-DR
            protocols (target IC50, counter-screen IC50, ...); curve_type was
            ambiguous when two DRs shared it.
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
        # Formats:
        #   "rd:{rd_def_id}"                          -- raw, legacy/unscoped
        #   "rd:{proto_id}:{rd_def_id}"               -- raw, protocol-scoped
        #   "rd:{proto_id}:{rd_def_id}:{normalization}" -- normalized layer
        #   "drc:{rd_def_id}"                         -- best DR curve for the
        #                                                DR readout-def
        rd_specs: list[tuple[uuid.UUID, str | None]] = []
        rd_col_map: dict[tuple[uuid.UUID, str | None], str] = {}
        drc_specs: list[uuid.UUID] = []  # readout_definition_id
        for col in protocol_columns:
            if col.startswith("rd:"):
                parts = col.split(":")
                # Identify the rd_def_id and optional normalization. Last UUID
                # segment is the readout def; anything after it is a formula.
                if len(parts) == 4:
                    rd_id = uuid.UUID(parts[2])
                    normalization: str | None = parts[3] or None
                else:
                    rd_id = uuid.UUID(parts[-1])
                    normalization = None
                spec = (rd_id, normalization)
                rd_specs.append(spec)
                rd_col_map[spec] = col
            elif col.startswith("drc:"):
                drc_specs.append(uuid.UUID(col.split(":", 1)[1]))

        # Fetch aggregated readouts
        rd_data: dict[uuid.UUID, dict[tuple[uuid.UUID, str | None], AggregatedReadout]] = {}
        if rd_specs:
            rd_data = await self._readout_repo.find_aggregated_by_molecules(
                workspace_id, molecule_ids, rd_specs
            )

        # Fetch best curves keyed by readout-def
        curve_data: dict[uuid.UUID, dict[uuid.UUID, object]] = {}
        proto_dose_unit: dict[uuid.UUID, str] = {}
        if drc_specs:
            curve_data = await self._curve_repo.find_best_curves_for_molecules(
                workspace_id, molecule_ids, drc_specs
            )
            # Resolve dose_unit per protocol once. The fitted IC50 unit
            # decoration is sourced from the owning protocol (not denormalized
            # on the curve), so we collect the protocols the picked curves
            # actually came from.
            curve_proto_ids = {
                curve.protocol_id
                for by_rd in curve_data.values()
                for curve in by_rd.values()
            }
            if curve_proto_ids:
                protos = await self._protocol_repo.find_by_ids(
                    workspace_id, list(curve_proto_ids)
                )
                proto_dose_unit = {p.id: p.dose_unit.value for p in protos}

        # Build result
        result: dict[uuid.UUID, dict[str, ActivityValue]] = {}
        for mol_id in molecule_ids:
            mol_activity: dict[str, ActivityValue] = {}

            # Readout columns
            mol_rds = rd_data.get(mol_id, {})
            for spec in rd_specs:
                col_key = rd_col_map[spec]
                agg = mol_rds.get(spec)
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
            for rd_id in drc_specs:
                col_key = f"drc:{rd_id}"
                curve = mol_curves.get(rd_id)
                if curve:
                    # Condense raw_data to [{x, y}] for inline sparkline
                    condensed = None
                    if curve.raw_data and isinstance(curve.raw_data, list):
                        condensed = _condense_raw_data(curve.raw_data)

                    intercepts_payload = _serialize_intercept_values(
                        curve.intercept_values
                    )
                    mol_activity[col_key] = ActivityValue(
                        value=curve.fitted_value,
                        qualifier=None,
                        unit=proto_dose_unit.get(curve.protocol_id, "uM"),
                        source="dose_response",
                        curve_type=curve.curve_type.value,
                        r_squared=curve.r_squared,
                        data_point_count=curve.num_points,
                        raw_data=condensed,
                        curve_params=CurveParams(
                            hill_slope=curve.hill_slope,
                            top=curve.top,
                            bottom=curve.bottom,
                            num_points=curve.num_points,
                            curve_class=curve.curve_class.value if curve.curve_class else None,
                            confidence_interval_low=curve.confidence_interval_low,
                            confidence_interval_high=curve.confidence_interval_high,
                            fit_quality_warnings=list(curve.fit_quality_warnings)
                            if curve.fit_quality_warnings
                            else None,
                        ),
                        intercept_values=intercepts_payload or None,
                    )

            if mol_activity:
                result[mol_id] = mol_activity

        return result
