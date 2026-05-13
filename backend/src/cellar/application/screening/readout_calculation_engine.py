"""ReadoutCalculationEngine — application-layer orchestrator for the full
computation pipeline after raw readout data is imported into a run.

Pipeline steps (in order):
1. Load context (run + protocol)
2. Idempotent cleanup of previous computed data
3. Load raw data
4. Normalize per-plate values
5. Aggregate replicates
6. Evaluate intra-protocol calculated readout formulas (topologically sorted)
7. Persist computed results
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.screening.fit_dose_response import (
    FitDoseResponseCurves,
    FitOverrides,
)
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import (
    ReadoutAggregation,
    WellType,
)
from cellar.domain.screening_assay.formula_evaluator import FormulaEvaluator
from cellar.domain.screening_assay.plate_normalizer import PlateNormalizer
from cellar.domain.screening_assay.plate_quality import PlateQualityCalculator
from cellar.domain.screening_assay.protocol import ReadoutDefinition
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.replicate_aggregator import ReplicateAggregator
from cellar.domain.screening_assay.repository import (
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.shared.value_objects import QualifiedValue

# Regex to detect cross-protocol references: @ProtocolName.ReadoutName or @{Protocol Name}.Readout
_CROSS_PROTOCOL_RE = re.compile(r"@\{?[\w\s]+\}?\.[\w\s]+")


@dataclass(frozen=True)
class ComputeRunResult:
    """Outcome of a full compute pipeline run.

    ``computed_readouts`` is the list of newly persisted ``ReadoutData`` rows.
    ``fit_warnings`` accumulates any per-compound dose-response fit failures
    so callers can surface them instead of silently swallowing them.
    """

    computed_readouts: list[ReadoutData]
    fit_warnings: list[str] = field(default_factory=list)


class ReadoutCalculationEngine:
    """Runs the full computation pipeline for a screening run.

    Steps: normalize -> aggregate -> evaluate formulas -> persist.

    Cross-protocol formulas (containing ``@`` references) are intentionally
    skipped — those are resolved on-read by ``CrossProtocolResolver``.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        formula_evaluator: FormulaEvaluator,
        plate_normalizer: PlateNormalizer,
        replicate_aggregator: ReplicateAggregator,
        readout_data_repo: ReadoutDataRepository,
        run_repo: RunRepository,
        protocol_repo: ProtocolRepository,
        dispatcher: EventDispatcherProtocol,
        fit_dose_response: FitDoseResponseCurves | None = None,
        plate_quality: PlateQualityCalculator | None = None,
    ) -> None:
        self._uow = uow
        self._formula_evaluator = formula_evaluator
        self._plate_normalizer = plate_normalizer
        self._replicate_aggregator = replicate_aggregator
        self._readout_data_repo = readout_data_repo
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo
        self._dispatcher = dispatcher
        self._fit_dose_response = fit_dose_response
        self._plate_quality = plate_quality

    async def compute_for_run(
        self,
        run_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        fit_overrides: FitOverrides | None = None,
    ) -> Result[ComputeRunResult, DomainError]:
        """Execute the full computation pipeline for *run_id*.

        Returns:
            Success(ComputeRunResult) — newly computed readouts + any
                non-fatal dose-response fit warnings.
            Failure(DomainError) — if run/protocol not found or a computation fails.
        """
        if self._uow.is_active:
            # Caller owns the transaction; they will commit and dispatch.
            return await self._execute(
                run_id, workspace_id=workspace_id, fit_overrides=fit_overrides
            )
        events: list = []
        async with self._uow:
            result = await self._execute(
                run_id, workspace_id=workspace_id, fit_overrides=fit_overrides
            )
            # Computed readouts and qc_metrics live in the session until we
            # commit. Without this commit they were silently rolled back on
            # context exit.
            if isinstance(result, Success):
                events = await self._uow.commit()
        if events:
            await self._dispatcher.dispatch_all(events)
        return result

    async def _execute(
        self,
        run_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        fit_overrides: FitOverrides | None = None,
    ) -> Result[ComputeRunResult, DomainError]:
        # ------------------------------------------------------------------
        # 1. Load context + workspace ownership check
        # ------------------------------------------------------------------
        run = await self._run_repo.find_by_id_in_workspace(workspace_id, run_id)
        if run is None:
            return Failure(NotFoundError("Run", str(run_id)))

        protocol = await self._protocol_repo.find_by_id_in_workspace(workspace_id, run.protocol_id)
        if protocol is None:
            return Failure(NotFoundError("Protocol", str(run.protocol_id)))

        # ------------------------------------------------------------------
        # 2. Idempotent cleanup
        # ------------------------------------------------------------------
        await self._readout_data_repo.delete_computed_for_run(workspace_id, run_id)

        # ------------------------------------------------------------------
        # 3. Load raw data
        # ------------------------------------------------------------------
        raw_data = await self._readout_data_repo.find_by_run(run.workspace_id, run_id)
        if not raw_data:
            return Success(ComputeRunResult(computed_readouts=[]))

        computed: list[ReadoutData] = []

        # Build lookup maps once — the inner loops below are O(W*R*D) without
        # them on a 384-well, multi-readout run.
        rd_by_id: dict[uuid.UUID, ReadoutDefinition] = {
            rd.id: rd for rd in protocol.readout_definitions
        }
        rd_by_name: dict[str, ReadoutDefinition] = {
            rd.name: rd for rd in protocol.readout_definitions
        }
        wells_by_id: dict[uuid.UUID, Any] = {w.id: w for w in run.wells}
        # (well_id, readout_definition_id) -> raw readout, used by the
        # normalization path to map a normalized value back to its source.
        raw_by_well_def: dict[tuple[uuid.UUID, uuid.UUID], ReadoutData] = {}
        for r in raw_data:
            if r.well_id is not None and r.readout_definition_id is not None:
                raw_by_well_def[(r.well_id, r.readout_definition_id)] = r

        # ------------------------------------------------------------------
        # 4. Normalize per-plate
        # ------------------------------------------------------------------
        for rd in protocol.readout_definitions:
            if not rd.normalizations or rd.is_calculated:
                continue

            # Group raw data by plate for this readout definition
            plate_wells: dict[uuid.UUID, list] = defaultdict(list)
            plate_raw_values: dict[uuid.UUID, dict[uuid.UUID, float]] = defaultdict(dict)

            for readout in raw_data:
                if readout.readout_definition_id != rd.id:
                    continue
                if readout.well_id is None or readout.value is None:
                    continue
                well = wells_by_id.get(readout.well_id)
                if well is None:
                    continue
                plate_id = well.plate_id
                if well not in plate_wells[plate_id]:
                    plate_wells[plate_id].append(well)
                plate_raw_values[plate_id][well.id] = readout.value.value

            for plate_id, wells in plate_wells.items():
                try:
                    per_formula = self._plate_normalizer.normalize_many(
                        wells,
                        plate_raw_values[plate_id],
                        rd.normalizations,
                        protocol.pos_control_signal,
                    )
                except DomainError as exc:
                    return Failure(exc)

                for formula, norm_values in per_formula.items():
                    for nv in norm_values:
                        original = raw_by_well_def.get((nv.well_id, rd.id))
                        if original is None:
                            continue

                        computed.append(
                            ReadoutData(
                                workspace_id=run.workspace_id,
                                run_id=run_id,
                                well_id=nv.well_id,
                                molecule_id=original.molecule_id,
                                batch_id=original.batch_id,
                                readout_definition_id=rd.id,
                                value=QualifiedValue(value=nv.normalized_value),
                                is_computed=True,
                                normalization_applied=formula,
                            )
                        )

        # ------------------------------------------------------------------
        # 4.5. Z-prime QC from controls
        # ------------------------------------------------------------------
        if self._plate_quality is not None and run.plates:
            # Map well_id to its first non-null raw readout once, instead of
            # rescanning raw_data per well per plate.
            first_value_by_well: dict[uuid.UUID, ReadoutData] = {}
            for r in raw_data:
                if r.well_id is None or r.value is None:
                    continue
                if r.well_id not in first_value_by_well:
                    first_value_by_well[r.well_id] = r
            wells_by_plate: dict[uuid.UUID, list] = defaultdict(list)
            for w in run.wells:
                wells_by_plate[w.plate_id].append(w)

            z_prime_results = {}
            for plate in run.plates:
                pos_vals = []
                neg_vals = []
                for w in wells_by_plate.get(plate.id, []):
                    well_readout = first_value_by_well.get(w.id)
                    if well_readout is None:
                        continue
                    if w.well_type == WellType.POSITIVE_CONTROL:
                        pos_vals.append(well_readout.value.value)
                    elif w.well_type == WellType.NEGATIVE_CONTROL:
                        neg_vals.append(well_readout.value.value)

                if pos_vals and neg_vals:
                    qc = self._plate_quality.compute(pos_vals, neg_vals)
                    z_prime_results[str(plate.id)] = {
                        "z_prime": round(qc.z_prime, 3),
                        "classification": qc.classification,
                        "pos_mean": round(qc.positive_control_mean, 2),
                        "pos_sd": round(qc.positive_control_sd, 2),
                        "neg_mean": round(qc.negative_control_mean, 2),
                        "neg_sd": round(qc.negative_control_sd, 2),
                        "s2b": round(qc.signal_to_background, 2),
                    }

            if z_prime_results:
                # Re-bind to a fresh dict so SQLAlchemy detects the change
                # (in-place mutation on a JSONB column is not auto-tracked).
                run.qc_metrics = {**(run.qc_metrics or {}), "z_prime": z_prime_results}
                await self._run_repo.save(run)

        # ------------------------------------------------------------------
        # 5. Aggregate replicates (in-memory)
        # ------------------------------------------------------------------
        aggregated_values: dict[uuid.UUID, dict[str, float]] = defaultdict(dict)

        for rd in protocol.readout_definitions:
            if rd.is_calculated:
                continue

            # Per-molecule aggregation is meaningless for control-well readouts
            # (molecule_id is None on those). Filter them out here so they
            # don't pollute aggregated_values with a None key.
            rd_readouts = [
                r
                for r in raw_data
                if r.readout_definition_id == rd.id and r.molecule_id is not None
            ]

            if rd.aggregation != ReadoutAggregation.NONE:
                try:
                    agg_values = self._replicate_aggregator.aggregate(rd_readouts, rd.aggregation)
                except DomainError as exc:
                    return Failure(exc)

                for av in agg_values:
                    aggregated_values[av.molecule_id][rd.name] = av.value
            else:
                # No aggregation: use raw values directly, keyed by molecule_id.
                # If multiple readouts exist per molecule, take the first.
                for readout in rd_readouts:
                    if readout.value is not None and (
                        readout.molecule_id not in aggregated_values
                        or rd.name not in aggregated_values.get(readout.molecule_id, {})
                    ):
                        aggregated_values[readout.molecule_id][rd.name] = readout.value.value

        # ------------------------------------------------------------------
        # 6. Evaluate intra-protocol formulas (topologically sorted)
        # ------------------------------------------------------------------
        calculated_defs = [
            rd
            for rd in protocol.readout_definitions
            if rd.is_calculated
            and rd.calculation_formula
            and not _CROSS_PROTOCOL_RE.search(rd.calculation_formula)
        ]

        if calculated_defs:
            try:
                sorted_defs = self._topological_sort(calculated_defs, rd_by_name)
            except ValidationError as e:
                return Failure(e)

            # One pass to find a representative readout per molecule, used
            # below for batch_id attribution.
            representative_by_mol: dict[uuid.UUID, ReadoutData] = {}
            for r in raw_data:
                if r.molecule_id is not None and r.molecule_id not in representative_by_mol:
                    representative_by_mol[r.molecule_id] = r

            for rd in sorted_defs:
                for mol_id, bindings in aggregated_values.items():
                    try:
                        value = self._formula_evaluator.run(
                            rd.calculation_formula,  # type: ignore[arg-type]
                            bindings,
                        )
                    except DomainError as exc:
                        return Failure(exc)

                    representative = representative_by_mol.get(mol_id)
                    batch_id = representative.batch_id if representative else None

                    rd_entity = ReadoutData(
                        workspace_id=run.workspace_id,
                        run_id=run_id,
                        molecule_id=mol_id,
                        batch_id=batch_id,
                        readout_definition_id=rd.id,
                        value=QualifiedValue(value=value),
                        is_computed=True,
                    )
                    computed.append(rd_entity)

                    # Make the computed value available for downstream formulas
                    bindings[rd.name] = value

        # ------------------------------------------------------------------
        # 7.5. Auto-fit dose-response curves
        # ------------------------------------------------------------------
        fit_warnings: list[str] = []
        if self._fit_dose_response is not None:
            fit_outcome = await self._fit_dose_response.fit_for_run(
                run=run,
                protocol=protocol,
                readout_data=raw_data + computed,
                workspace_id=workspace_id,
                overrides=fit_overrides,
            )
            if isinstance(fit_outcome, Success):
                fit_warnings = list(fit_outcome.unwrap().warnings)

        # ------------------------------------------------------------------
        # 7. Persist
        # ------------------------------------------------------------------
        if computed:
            await self._readout_data_repo.save_bulk(computed)

        return Success(ComputeRunResult(computed_readouts=computed, fit_warnings=fit_warnings))

    # ------------------------------------------------------------------
    # Topological sort
    # ------------------------------------------------------------------

    @staticmethod
    def _topological_sort(
        calculated_defs: list[ReadoutDefinition],
        all_defs_by_name: dict[str, ReadoutDefinition],
    ) -> list[ReadoutDefinition]:
        """Sort calculated readout definitions so dependencies evaluate first.

        Raises ``ValidationError`` on circular dependency.
        """
        calc_names = {rd.name for rd in calculated_defs}
        calc_by_name = {rd.name: rd for rd in calculated_defs}

        visited: set[str] = set()
        in_stack: set[str] = set()
        order: list[ReadoutDefinition] = []

        def visit(name: str) -> None:
            if name in visited:
                return
            if name in in_stack:
                raise ValidationError(
                    f"Circular dependency detected in calculated readout '{name}'"
                )

            in_stack.add(name)
            try:
                rd = calc_by_name[name]
                formula = rd.calculation_formula or ""

                for dep_name in calc_names:
                    if dep_name == name:
                        continue
                    if re.search(rf"\b{re.escape(dep_name)}\b", formula):
                        visit(dep_name)
            finally:
                in_stack.discard(name)

            visited.add(name)
            order.append(rd)

        for rd in calculated_defs:
            visit(rd.name)

        return order
