"""ReadoutCalculationEngine — application-layer orchestrator for the full
computation pipeline after raw readout data is imported into a run.

Pipeline steps (in order):
1. Load context (run + protocol)
2. Idempotent cleanup of previous computed data
3. Load raw data
4. Normalize per-plate values
4.6. Tm and ΔTm per temperature window, from the run's melting steps
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

from cellar.application.screening._dose_response_config_serde import (
    serialize_dose_response_config,
)
from cellar.application.screening.fit_dose_response import (
    FitDoseResponseCurves,
    FitOverrides,
)
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.screening_assay.curve_fitting import (
    ConcentrationResponsePoint,
    CurveFittingService,
)
from cellar.domain.screening_assay.enums import (
    ReadoutAggregation,
    ReadoutDataType,
    WellType,
    primary_normalization,
)
from cellar.domain.screening_assay.excluded_point_detail import ExclusionSource
from cellar.domain.screening_assay.formula_evaluator import FormulaEvaluator
from cellar.domain.screening_assay.intercept_report import report_intercept
from cellar.domain.screening_assay.melt_series import series_points, series_values
from cellar.domain.screening_assay.melt_window import (
    MeltMeasure,
    WindowResult,
    evaluate_window,
    window_positions,
)
from cellar.domain.screening_assay.plate_normalizer import PlateNormalizer
from cellar.domain.screening_assay.plate_quality import PlateQualityCalculator
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.replicate_aggregator import ReplicateAggregator
from cellar.domain.screening_assay.repository import (
    DoseResponseCurveRepository,
    MeasuredCurveRepository,
    MeltingStepRepository,
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.aggregation_types import ValueQualifier
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.shared.value_objects import QualifiedValue

RAW_LAYER = "raw"
_CONTROL_TYPES = frozenset({WellType.POSITIVE_CONTROL, WellType.NEGATIVE_CONTROL})
# Control roles whose compound gets a per-plate potency, and the doses a curve needs.
_FITTED_CONTROL_TYPES = (WellType.POSITIVE_CONTROL, WellType.REFERENCE)
_MIN_FIT_DOSES = 4
# A curve's own fit settings, as its config snapshot stores them.
_CONSTRAINTS = (
    "top_constraint",
    "top_constraint_min",
    "top_constraint_max",
    "bottom_constraint",
    "bottom_constraint_min",
    "bottom_constraint_max",
    "hill_slope_constraint",
    "hill_slope_min",
    "hill_slope_max",
)

# Regex to detect cross-protocol references: @ProtocolName.ReadoutName or @{Protocol Name}.Readout
_CROSS_PROTOCOL_RE = re.compile(r"@\{?[A-Z]{2,8}-\d+\}?\.")


@dataclass(frozen=True)
class ComputeRunResult:
    """Outcome of a full compute pipeline run.

    ``computed_readouts`` is the list of newly persisted ``ReadoutData`` rows.
    ``fit_warnings`` accumulates any per-compound dose-response fit failures
    so callers can surface them instead of silently swallowing them;
    ``fit_notes`` are the fit's neutral facts (compounds tested at too few doses).
    """

    computed_readouts: list[ReadoutData]
    fit_warnings: list[str] = field(default_factory=list)
    fit_notes: list[str] = field(default_factory=list)


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
        melting_step_repo: MeltingStepRepository | None = None,
        measured_curve_repo: MeasuredCurveRepository | None = None,
        batch_repo: BatchRepository | None = None,
        curve_fitter: CurveFittingService | None = None,
        curve_repo: DoseResponseCurveRepository | None = None,
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
        self._melting_step_repo = melting_step_repo
        self._measured_curve_repo = measured_curve_repo
        self._batch_repo = batch_repo
        self._curve_fitter = curve_fitter
        self._curve_repo = curve_repo

    async def compute_for_run(
        self,
        run_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        fit_overrides: FitOverrides | None = None,
        refit_curves: bool = True,
    ) -> Result[ComputeRunResult, DomainError]:
        """Execute the full computation pipeline for *run_id*.

        ``refit_curves=False`` leaves the dose-response curves to the caller (an outlier
        flag refits only the curves it touches, keeping their edits).

        Returns:
            Success(ComputeRunResult) — newly computed readouts + any
                non-fatal dose-response fit warnings.
            Failure(DomainError) — if run/protocol not found or a computation fails.
        """
        if self._uow.is_active:
            # Caller owns the transaction; they will commit and dispatch.
            return await self._execute(
                run_id,
                workspace_id=workspace_id,
                fit_overrides=fit_overrides,
                refit_curves=refit_curves,
            )
        events: list = []
        async with self._uow:
            result = await self._execute(
                run_id,
                workspace_id=workspace_id,
                fit_overrides=fit_overrides,
                refit_curves=refit_curves,
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
        refit_curves: bool = True,
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

        computed: list[ReadoutData] = []

        # Build lookup maps once — the inner loops below are O(W*R*D) without
        # them on a 384-well, multi-readout run.
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
            # Outlier-flagged wells are no anchor, but still get a normalized value.
            outliers = frozenset(
                r.well_id
                for r in raw_data
                if r.readout_definition_id == rd.id and r.is_outlier and r.well_id is not None
            )

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
                        outlier_well_ids=outliers,
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
                                is_outlier=original.is_outlier,
                                is_computed=True,
                                normalization_applied=formula,
                            )
                        )

        # ------------------------------------------------------------------
        # 4.5. Plate QC from controls, per readout x layer
        # ------------------------------------------------------------------
        if self._plate_quality is not None and run.plates:
            plates = self._plate_qc(run, protocol, raw_data + computed)
            self._add_control_fits(plates, run, protocol, raw_data + computed, fit_overrides)
            # The engine owns both blocks: replaced even when no plate qualifies, so
            # flags or roles that leave a plate without controls drop its stale QC.
            # Re-bind to a fresh dict so SQLAlchemy detects the change
            # (in-place mutation on a JSONB column is not auto-tracked).
            run.qc_metrics = {
                **(run.qc_metrics or {}),
                "z_prime": _legacy_z_prime(plates),
                "plates": plates,
            }
            await self._run_repo.save(run)

        # ------------------------------------------------------------------
        # 4.6. Tm and ΔTm per temperature window
        # ------------------------------------------------------------------
        window_rows, series_rows = await self._window_rows(run, protocol, workspace_id)
        if not raw_data and not window_rows and not series_rows:
            return Success(ComputeRunResult(computed_readouts=[]))
        computed.extend(window_rows + series_rows)
        # Per-position window rows aggregate like raw rows, so formulas can name
        # them. Series rows do not: the in-run aggregator ignores qualifiers, and
        # a censored "> 50" from one lot would be averaged as 50. A formula reads a
        # compound's results only: unflagged sample wells and well-less rows.
        plate_qc_wells = {w.id for w in run.wells if w.well_type != WellType.SAMPLE}
        source_rows = [
            r
            for r in raw_data + window_rows
            if not r.is_outlier and r.well_id not in plate_qc_wells
        ]

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
                for r in source_rows
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
            for r in source_rows:
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
        fit_notes: list[str] = []
        if self._fit_dose_response is not None and refit_curves:
            edited = await self._edited_curves(run, protocol, fit_overrides)
            fit_outcome = await self._fit_dose_response.fit_for_run(
                run=run,
                protocol=protocol,
                readout_data=raw_data + computed,
                workspace_id=workspace_id,
                overrides=fit_overrides,
            )
            if isinstance(fit_outcome, Success):
                fit_warnings = list(fit_outcome.unwrap().warnings)
                fit_notes = list(fit_outcome.unwrap().notes)
            if edited and self._curve_repo is not None:
                kept = {c.id for c in await self._curve_repo.find_by_run(workspace_id, run_id)}
                if n := len(edited - kept):
                    fit_notes.append(
                        f"{n} curve{'' if n == 1 else 's'} with excluded points or fit settings "
                        "of their own refitted with these settings; those edits were reset"
                    )

        # ------------------------------------------------------------------
        # 7. Persist
        # ------------------------------------------------------------------
        if computed:
            await self._readout_data_repo.save_bulk(computed)

        return Success(
            ComputeRunResult(
                computed_readouts=computed, fit_warnings=fit_warnings, fit_notes=fit_notes
            )
        )

    async def _edited_curves(
        self, run: Run, protocol: Protocol, fit_overrides: FitOverrides | None
    ) -> set[uuid.UUID]:
        """The run's curves a chemist changed: points excluded by hand (or an accepted 3σ
        suggestion), or fit constraints other than the ones this refit uses."""
        if self._curve_repo is None:
            return set()
        configs = {
            rd.id: serialize_dose_response_config(
                fit_overrides.apply(rd.dose_response_config)
                if fit_overrides is not None
                else rd.dose_response_config
            )
            for rd in protocol.readout_definitions
            if rd.dose_response_config is not None
        }
        edited = set()
        for c in await self._curve_repo.find_by_run(run.workspace_id, run.id):
            config = configs.get(c.readout_definition_id)
            snapshot = c.dose_response_config_snapshot or {}
            if any(
                e.excluded and e.source != ExclusionSource.WELL_FLAG
                for e in c.excluded_points or []
            ) or (
                config is not None
                and snapshot
                and any(snapshot.get(k) != config.get(k) for k in _CONSTRAINTS)
            ):
                edited.add(c.id)
        return edited

    def _plate_qc(
        self, run: Run, protocol: Protocol, rows: list[ReadoutData]
    ) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
        """``plates[plate_id][readout_definition_id][layer]``: Z′, each control's mean,
        SD and n, and S/B (raw layer only), for every readout x layer whose plate has
        both control types. Layers are ``raw`` and each normalization. Outlier-flagged
        wells are left out."""
        assert self._plate_quality is not None
        wells = {w.id: w for w in run.wells}
        # (plate, readout, layer) -> control type -> well -> value (the last row wins)
        values: dict[tuple[uuid.UUID, uuid.UUID, str], dict[WellType, dict[uuid.UUID, float]]]
        values = defaultdict(lambda: defaultdict(dict))
        for r in rows:
            if r.well_id is None or r.value is None or r.readout_definition_id is None:
                continue
            if r.is_outlier:
                continue
            if r.is_computed and r.normalization_applied is None:
                continue  # formula and melt-window rows are not plate layers
            well = wells.get(r.well_id)
            if well is None or well.well_type not in _CONTROL_TYPES:
                continue
            layer = str(r.normalization_applied or RAW_LAYER)
            key = (well.plate_id, r.readout_definition_id, layer)
            values[key][well.well_type][well.id] = r.value.value

        order = {rd.id: i for i, rd in enumerate(protocol.readout_definitions)}
        plate_order = {p.id: p.plate_number for p in run.plates}
        out: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
        for plate_id, rd_id, layer in sorted(
            values,
            key=lambda k: (plate_order.get(k[0], 0), order.get(k[1], 0), k[2] != RAW_LAYER, k[2]),
        ):
            by_type = values[(plate_id, rd_id, layer)]
            pos = list(by_type[WellType.POSITIVE_CONTROL].values())
            neg = list(by_type[WellType.NEGATIVE_CONTROL].values())
            if not pos or not neg:
                continue
            qc = self._plate_quality.compute(pos, neg)
            enough = qc.classification != "insufficient_data"
            entry = {
                "z_prime": qc.z_prime if enough else None,
                "classification": qc.classification,
                "pos_mean": qc.positive_control_mean,
                "pos_sd": qc.positive_control_sd if len(pos) >= 2 else None,
                "pos_n": len(pos),
                "neg_mean": qc.negative_control_mean,
                "neg_sd": qc.negative_control_sd if len(neg) >= 2 else None,
                "neg_n": len(neg),
                # A ratio of means only reads on the raw signal.
                "s2b": qc.signal_to_background if enough and layer == RAW_LAYER else None,
            }
            out.setdefault(str(plate_id), {}).setdefault(str(rd_id), {})[layer] = entry
        return out

    def _add_control_fits(
        self,
        plates: dict[str, dict[str, dict[str, dict[str, Any]]]],
        run: Run,
        protocol: Protocol,
        rows: list[ReadoutData],
        fit_overrides: FitOverrides | None,
    ) -> None:
        """Fit each positive-control and reference compound with a dose series of
        at least four doses, per plate, on the layer the samples' curves read; the
        primary intercept and curve class go into that layer's plate QC as
        ``control_fits`` — QC, never the compound's curve. Outlier-flagged wells are left out."""
        if self._curve_fitter is None:
            return
        wells = {w.id: w for w in run.wells}
        rd_by_name = {rd.name: rd for rd in protocol.readout_definitions}
        for dr_def in protocol.readout_definitions:
            base = dr_def.dose_response_config
            if dr_def.data_type != ReadoutDataType.DOSE_RESPONSE or base is None:
                continue
            config = fit_overrides.apply(base) if fit_overrides is not None else base
            y_rd = rd_by_name.get(config.y_readout_name)
            if y_rd is None or y_rd.is_calculated:
                continue  # formula values are per compound, not per well
            layer = (
                str(config.y_normalization or primary_normalization(y_rd.normalizations))
                if y_rd.normalizations
                else RAW_LAYER
            )
            # (plate, role, molecule) -> well -> (dose, value)
            series: dict[
                tuple[uuid.UUID, WellType, uuid.UUID], dict[uuid.UUID, tuple[float, float]]
            ] = defaultdict(dict)
            for r in rows:
                if (
                    r.readout_definition_id != y_rd.id
                    or str(r.normalization_applied or RAW_LAYER) != layer
                    or r.is_outlier
                ):
                    continue
                if r.is_computed and r.normalization_applied is None:
                    continue
                well = wells.get(r.well_id) if r.well_id is not None else None
                if (
                    well is None
                    or well.well_type not in _FITTED_CONTROL_TYPES
                    or well.dose is None
                    or r.molecule_id is None
                    or r.value is None
                ):
                    continue
                series[(well.plate_id, well.well_type, r.molecule_id)][well.id] = (
                    well.dose,
                    r.value.value,
                )
            for (plate_id, role, molecule_id), by_well in series.items():
                if len({dose for dose, _ in by_well.values()}) < _MIN_FIT_DOSES:
                    continue
                points = [
                    ConcentrationResponsePoint(concentration=d, response=v)
                    for d, v in by_well.values()
                ]
                fit = self._curve_fitter.fit(points, config)
                if isinstance(fit, Failure):
                    continue
                fitted = fit.unwrap()
                primary = fitted.intercept_values[0] if fitted.intercept_values else None
                doses = [d for d, _ in by_well.values() if d > 0]
                # A potency only when the fit reads it inside the doses: an inactive series,
                # one active at every dose, a bound or n.d. has none.
                value, qualifier = report_intercept(
                    fitted.curve_class,
                    primary.qualifier if primary else None,
                    fitted.fitted_value,
                    min(doses, default=None),
                    max(doses, default=None),
                    at_bound=primary.at_bound if primary else False,
                    primary=True,
                )
                entry = (
                    plates.setdefault(str(plate_id), {})
                    .setdefault(str(y_rd.id), {})
                    .setdefault(layer, {})
                )
                entry.setdefault("control_fits", []).append(
                    {
                        "role": str(role),
                        "molecule_id": str(molecule_id),
                        "label": config.intercepts[0].display_label,
                        "value": value if qualifier == ValueQualifier.EQ else None,
                        "curve_class": str(fitted.curve_class),
                    }
                )

    async def _window_rows(
        self, run: Run, protocol: Protocol, workspace_id: uuid.UUID
    ) -> tuple[list[ReadoutData], list[ReadoutData]]:
        """Per-position Tm/ΔTm rows, and one series row per batch, for each window readout."""
        melt_defs = [
            (rd, rd.melt_config)
            for rd in protocol.readout_definitions
            if rd.melt_config is not None
        ]
        if not melt_defs or self._melting_step_repo is None or self._measured_curve_repo is None:
            return [], []
        steps = [s.fact for s in await self._melting_step_repo.find_by_run(workspace_id, run.id)]
        traced = await self._measured_curve_repo.list_traced(workspace_id, run.id)
        wells = [(w.id, w.well_type) for w in run.wells]
        batch_and_dose = {w.id: (w.batch_id, w.dose) for w in run.wells}
        # Window names per channel: an assignment to any other name is stale.
        on_signal: dict[str, set[str]] = {}
        for _, mc in melt_defs:
            on_signal.setdefault(mc.channel_key, set()).add(mc.window)

        # Readouts of one window share its channel and limits (Protocol enforces it).
        by_window: dict[str, WindowResult] = {}
        # (readout, well or None, batch, value)
        values: list[tuple[ReadoutDefinition, uuid.UUID | None, uuid.UUID | None, QualifiedValue]]
        values = []
        for rd, mc in melt_defs:
            result = by_window.get(mc.window)
            if result is None:
                result = by_window[mc.window] = evaluate_window(
                    mc.window,
                    mc.low,
                    mc.high,
                    window_positions(wells, steps, mc.channel_key, traced),
                    on_signal[mc.channel_key],
                )
            if mc.measure.is_series:
                for sv in series_values(mc, series_points(result, batch_and_dose)):
                    values.append(
                        (
                            rd,
                            None,
                            sv.batch_id,
                            QualifiedValue(value=sv.value, qualifier=sv.qualifier),
                        )
                    )
                continue
            for p in result.positions:
                v = p.tm if mc.measure is MeltMeasure.TM else p.delta_tm
                if v is not None:
                    values.append(
                        (rd, p.well_id, batch_and_dose[p.well_id][0], QualifiedValue(value=v))
                    )
        if not values:
            return [], []

        batch_ids = list(dict.fromkeys(b for _, _, b, _ in values if b))
        molecule_by_batch: dict[uuid.UUID, uuid.UUID] = {}
        if batch_ids and self._batch_repo is not None:
            molecule_by_batch = {
                b.id: b.molecule_id
                for b in await self._batch_repo.find_by_ids(workspace_id, batch_ids)
            }
        position_rows: list[ReadoutData] = []
        series_rows: list[ReadoutData] = []
        for rd, well_id, batch_id, value in values:
            row = ReadoutData(
                workspace_id=run.workspace_id,
                run_id=run.id,
                well_id=well_id,
                molecule_id=molecule_by_batch.get(batch_id) if batch_id else None,
                batch_id=batch_id,
                readout_definition_id=rd.id,
                value=value,
                is_computed=True,
            )
            (position_rows if well_id is not None else series_rows).append(row)
        return position_rows, series_rows

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


def _legacy_z_prime(
    plates: dict[str, dict[str, dict[str, dict[str, Any]]]],
) -> dict[str, dict[str, Any]]:
    """``qc_metrics.z_prime`` as its readers know it: per plate, the raw layer of the
    first readout (protocol order) that has one, rounded as before."""
    legacy: dict[str, dict[str, Any]] = {}
    for plate_id, readouts in plates.items():
        raw = next((r[RAW_LAYER] for r in readouts.values() if RAW_LAYER in r), None)
        if raw is None:
            continue
        legacy[plate_id] = {
            "z_prime": round(raw["z_prime"] or 0.0, 3),
            "classification": raw["classification"],
            "pos_mean": round(raw["pos_mean"], 2),
            "pos_sd": round(raw["pos_sd"] or 0.0, 2),
            "neg_mean": round(raw["neg_mean"], 2),
            "neg_sd": round(raw["neg_sd"] or 0.0, 2),
            "s2b": round(raw["s2b"] or 0.0, 2),
        }
    return legacy
