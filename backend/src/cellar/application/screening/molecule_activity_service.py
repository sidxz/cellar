"""MoleculeActivityService -- read-model crossing Molecule and Screening boundaries.

This service provides activity data for molecule detail pages and enriched
search results. It queries readout data and dose-response curves grouped
by protocol.

DR enrichment uses the shared aggregator (``run_aggregation``) — same code
path the campaign grid uses — so the search grid stops cherry-picking the
best-R² curve and instead applies a chemist-correct selection rule (default
``LATEST_APPROVED_RUN`` with ``EXCLUDE_QUALIFIED`` handling) over every
in-scope run of the (compound, readout-def) cell.
"""

from __future__ import annotations

import uuid
from typing import Any

from cellar.application.screening import _condense_raw_data
from cellar.application.screening.curve_snapshot import build_aggregate_curve_snapshot
from cellar.application.screening.run_aggregation import (
    AggregateResult,
    ResolvedRun,
    apply_selection_rule,
    compute_aggregate_stats,
    detect_disagreement,
)
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.activity_types import (
    ActivitySummary,
    ActivityValue,
    AggregatedReadout,
    AnyProtocolActivity,
    AnyProtocolEntry,
    CurveParams,
    InterceptAggregate,
    ProtocolActivitySummary,
    RunSummary,
)
from cellar.domain.screening_assay.aggregation_types import (
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.screening_assay.curve_fitting import InterceptValue
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import RunStatus
from cellar.domain.screening_assay.repository import (
    DoseResponseCurveRepository,
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from cellar.domain.screening_assay.run import Run
from cellar.domain.screening_assay.run_scope import RunScope
from cellar.domain.shared.enums import ConcentrationUnit
from cellar.domain.shared.hit_criterion import InterceptKey

# Cap the per-cell wire payload of per-run summaries. Multi-year programs
# can accumulate dozens of runs on a single compound; the tooltip needs
# enough context to be useful without exploding the search response.
_MAX_RUNS_PAYLOAD: int = 10


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
        run_repo: RunRepository,
    ) -> None:
        self._uow = uow
        self._readout_repo = readout_repo
        self._curve_repo = curve_repo
        self._protocol_repo = protocol_repo
        self._run_repo = run_repo

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

            intercept_values_payload = _serialize_intercept_values(curve.intercept_values)

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
        *,
        selection_rule: SelectionRule = SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling: QualifierHandling = QualifierHandling.EXCLUDE_QUALIFIED,
        run_scopes: dict[str, RunScope] | None = None,
        any_readout_groups: list[tuple[str, str | None]] | None = None,
    ) -> dict[uuid.UUID, dict[str, ActivityValue | AnyProtocolActivity]]:
        """Batch enrichment for search results.

        protocol_columns format:
          - "rd:{readout_definition_id}" -- aggregated raw readout value
          - "rd:{protocol_id}:{readout_definition_id}" -- same, with protocol scope
          - "rd:{protocol_id}:{readout_definition_id}:{normalization}" -- the
            named normalization layer of the readout (e.g. ``percent_inhibition``,
            ``z_score``). Without the suffix the raw layer is returned.
          - "drc:{readout_definition_id}" -- aggregated dose-response curve for
            that DR readout-def. The readout-def identifies the column on
            multi-DR protocols (target IC50, counter-screen IC50, ...);
            curve_type was ambiguous when two DRs shared it.
          - "any" -- one AnyProtocolActivity listing every protocol the
            molecule has DR curves in (plus readout groups named in
            ``any_readout_groups``), best first, native units.

        DR columns flow through the shared run-aggregator (``run_aggregation``):
        every in-scope run contributes a ``ResolvedRun``, and ``selection_rule``
        collapses them into a single per-cell value. Default rule
        ``LATEST_APPROVED_RUN`` + ``EXCLUDE_QUALIFIED`` matches the campaign
        default + chemist mental model. ``run_scopes`` is a per-column override
        (key = ``"drc:<rd_id>"``); any column without an entry uses
        ``RunScope.all()``.
        """
        if not molecule_ids or not protocol_columns:
            return {}

        if self._uow.is_active:
            return await self._enrich_molecules(
                workspace_id,
                molecule_ids,
                protocol_columns,
                selection_rule=selection_rule,
                qualifier_handling=qualifier_handling,
                run_scopes=run_scopes,
                any_readout_groups=any_readout_groups,
            )
        async with self._uow:
            return await self._enrich_molecules(
                workspace_id,
                molecule_ids,
                protocol_columns,
                selection_rule=selection_rule,
                qualifier_handling=qualifier_handling,
                run_scopes=run_scopes,
                any_readout_groups=any_readout_groups,
            )

    async def _enrich_molecules(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        protocol_columns: list[str],
        *,
        selection_rule: SelectionRule = SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling: QualifierHandling = QualifierHandling.EXCLUDE_QUALIFIED,
        run_scopes: dict[str, RunScope] | None = None,
        any_readout_groups: list[tuple[str, str | None]] | None = None,
    ) -> dict[uuid.UUID, dict[str, ActivityValue | AnyProtocolActivity]]:
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
        want_any = "any" in protocol_columns

        # Fetch aggregated readouts
        rd_data: dict[uuid.UUID, dict[tuple[uuid.UUID, str | None], AggregatedReadout]] = {}
        if rd_specs:
            rd_data = await self._readout_repo.find_aggregated_by_molecules(
                workspace_id, molecule_ids, rd_specs
            )

        # Fetch ALL curves for the DR columns, grouped by per-column run_scope.
        # The shared aggregator collapses them to one ActivityValue per
        # (compound, rd) cell — same code path as the campaign grid.
        curve_data: dict[uuid.UUID, dict[uuid.UUID, list[DoseResponseCurve]]] = {}
        proto_dose_unit: dict[uuid.UUID, str] = {}
        runs_by_id: dict[uuid.UUID, Run] = {}
        if drc_specs:
            curve_data, runs_by_id = await self._fetch_curves_and_runs(
                workspace_id, molecule_ids, drc_specs, run_scopes or {}
            )
            # Resolve dose_unit per protocol once. The fitted IC50 unit
            # decoration is sourced from the owning protocol (not denormalized
            # on the curve), so we collect the protocols the picked curves
            # actually came from.
            curve_proto_ids = {
                curve.protocol_id
                for by_rd in curve_data.values()
                for curves in by_rd.values()
                for curve in curves
            }
            if curve_proto_ids:
                protos = await self._protocol_repo.find_by_ids(workspace_id, list(curve_proto_ids))
                proto_dose_unit = {p.id: p.dose_unit.value for p in protos}

        # "any" column: every curve the molecule has, in every protocol.
        any_curves: dict[uuid.UUID, dict[uuid.UUID, list[DoseResponseCurve]]] = {}
        any_runs: dict[uuid.UUID, Run] = {}
        any_protos: dict[uuid.UUID, Any] = {}
        any_targets: dict[uuid.UUID, list[str]] = {}
        any_readouts: dict[uuid.UUID, list[tuple[uuid.UUID, AggregatedReadout]]] = {}
        if want_any:
            any_curves = await self._curve_repo.find_all_curves_for_molecules(
                workspace_id, molecule_ids, readout_definition_ids=None, run_scope=RunScope.all()
            )
            any_run_ids = list(
                {c.run_id for by_rd in any_curves.values() for cs in by_rd.values() for c in cs}
            )
            any_runs = (
                await self._run_repo.find_by_ids(workspace_id, any_run_ids) if any_run_ids else {}
            )
            any_proto_ids = list(
                {
                    c.protocol_id
                    for by_rd in any_curves.values()
                    for cs in by_rd.values()
                    for c in cs
                }
            )
            if any_proto_ids:
                for p in await self._protocol_repo.find_by_ids(workspace_id, any_proto_ids):
                    any_protos[p.id] = p
                targets = await self._protocol_repo.find_effective_targets_for_protocols(
                    workspace_id, any_proto_ids
                )
                any_targets = {pid: [t.name for t in refs] for pid, refs in targets.items()}

            if any_readout_groups:
                any_readouts = await self._readout_repo.find_aggregated_by_molecules_and_names(
                    workspace_id, molecule_ids, any_readout_groups
                )
                extra_proto_ids = [
                    pid for lst in any_readouts.values() for pid, _ in lst if pid not in any_protos
                ]
                if extra_proto_ids:
                    for p in await self._protocol_repo.find_by_ids(workspace_id, extra_proto_ids):
                        any_protos[p.id] = p
                    more = await self._protocol_repo.find_effective_targets_for_protocols(
                        workspace_id, extra_proto_ids
                    )
                    any_targets.update({pid: [t.name for t in refs] for pid, refs in more.items()})

        # Build result
        result: dict[uuid.UUID, dict[str, ActivityValue | AnyProtocolActivity]] = {}
        for mol_id in molecule_ids:
            mol_activity: dict[str, ActivityValue | AnyProtocolActivity] = {}

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
                curves = mol_curves.get(rd_id) or []
                if not curves:
                    continue

                resolved_runs = self._build_resolved_runs(curves, runs_by_id)
                if not resolved_runs:
                    continue

                # Pick the dose unit from the first curve's protocol — every
                # curve under one rd_id shares a protocol (the rd_id IS keyed
                # by protocol), so any candidate gives the same answer.
                unit = proto_dose_unit.get(curves[0].protocol_id, "uM")

                activity = self._build_dr_activity(
                    resolved_runs=resolved_runs,
                    unit=unit,
                    selection_rule=selection_rule,
                    qualifier_handling=qualifier_handling,
                )
                if activity is not None:
                    mol_activity[col_key] = activity

            if want_any:
                block = self._build_any_activity(
                    any_curves.get(mol_id, {}),
                    readouts=any_readouts.get(mol_id, []),
                    runs_by_id=any_runs,
                    protos=any_protos,
                    targets=any_targets,
                    selection_rule=selection_rule,
                    qualifier_handling=qualifier_handling,
                )
                if block is not None:
                    mol_activity["any"] = block

            if mol_activity:
                result[mol_id] = mol_activity

        return result

    # ------------------------------------------------------------------
    # DR enrichment helpers
    # ------------------------------------------------------------------

    async def _fetch_curves_and_runs(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        drc_specs: list[uuid.UUID],
        run_scopes: dict[str, RunScope],
    ) -> tuple[
        dict[uuid.UUID, dict[uuid.UUID, list[DoseResponseCurve]]],
        dict[uuid.UUID, Run],
    ]:
        """Fetch curves (grouped by scope) and the runs they reference.

        Groups ``drc_specs`` by their per-column ``RunScope`` so we make
        one repo round-trip per distinct scope, then unions the results.
        Without scope-grouping a 20-column search would issue 20 separate
        ``find_all_curves_for_molecules`` calls; grouping shrinks that to
        one call per distinct scope (typically 1-2 in practice).
        """
        # Group rd_ids by the scope each one carries.
        scope_groups: dict[RunScope, list[uuid.UUID]] = {}
        for rd_id in drc_specs:
            scope = run_scopes.get(f"drc:{rd_id}") or RunScope.all()
            scope_groups.setdefault(scope, []).append(rd_id)

        merged: dict[uuid.UUID, dict[uuid.UUID, list[DoseResponseCurve]]] = {}
        for scope, rd_ids in scope_groups.items():
            grouped = await self._curve_repo.find_all_curves_for_molecules(
                workspace_id,
                molecule_ids,
                readout_definition_ids=rd_ids,
                run_scope=scope,
            )
            for mol_id, by_rd in grouped.items():
                bucket = merged.setdefault(mol_id, {})
                for rd_id, curves in by_rd.items():
                    bucket[rd_id] = curves

        # Batch-fetch the owning Run aggregates so the adapter has
        # run_date + run_approved without N+1.
        run_ids = list(
            {
                curve.run_id
                for by_rd in merged.values()
                for curves in by_rd.values()
                for curve in curves
            }
        )
        runs_by_id = await self._run_repo.find_by_ids(workspace_id, run_ids) if run_ids else {}
        return merged, runs_by_id

    @staticmethod
    def _build_resolved_runs(
        curves: list[DoseResponseCurve], runs_by_id: dict[uuid.UUID, Run]
    ) -> list[ResolvedRun]:
        """Adapt persisted curves + their owning runs to the aggregator's input.

        Curves whose owning run wasn't loaded (deleted? cross-workspace
        leak?) are silently dropped — defensive, the aggregator can't make
        a date-based selection without ``run_date``.
        """
        out: list[ResolvedRun] = []
        for c in curves:
            run = runs_by_id.get(c.run_id)
            if run is None:
                continue
            out.append(
                ResolvedRun(
                    run_id=run.id,
                    run_date=run.run_date,
                    run_approved=(run.status == RunStatus.APPROVED),
                    curve_id=c.id,
                    # `fitted_value` is the curve's primary intercept on the
                    # `EQ` path. The aggregator overrides this with the
                    # spec-resolved intercept value before display.
                    value=c.fitted_value,
                    # Curves themselves carry no wire-level GT/LT qualifier
                    # (that's a readout_data concept); the aggregator derives
                    # ND from `curve_class` and GT from `at_bound`.
                    qualifier=ValueQualifier.EQ,
                    unit="",  # filled in by the caller from protocol.dose_unit
                    z_prime=None,
                    protocol_name="",
                    protocol_version=0,
                    readout_id=None,
                    curve_class=c.curve_class.value if c.curve_class else None,
                    curve_top=c.top,
                    curve_bottom=c.bottom,
                    curve_hill_slope=c.hill_slope,
                    curve_r_squared=c.r_squared,
                    curve_raw_data=c.raw_data,
                    curve_excluded_points=c.excluded_points,
                    intercept_values=_serialize_intercept_values(c.intercept_values) or None,
                    curve_type=c.curve_type.value if c.curve_type else None,
                    curve_confidence_interval_low=c.confidence_interval_low,
                    curve_confidence_interval_high=c.confidence_interval_high,
                    curve_fit_quality_warnings=list(c.fit_quality_warnings or []),
                )
            )
        return out

    def _build_dr_activity(
        self,
        *,
        resolved_runs: list[ResolvedRun],
        unit: str,
        selection_rule: SelectionRule,
        qualifier_handling: QualifierHandling,
    ) -> ActivityValue | None:
        """Collapse N ResolvedRuns to one ActivityValue using the aggregator.

        Returns ``None`` when no rule application produces a representative
        run (e.g. the rule filtered everything out and no fallback latest
        is available — extremely rare; the aggregator's contract gives us
        a latest-by-date for every non-empty filtered input).
        """
        # Discover the intercept specs present across the candidate curves —
        # the union of (kind, level) tuples on every contributing curve's
        # `intercept_values`. Pragmatic: don't refetch the protocol just to
        # learn the spec list; if a curve was fit with EC50+EC90 it's in
        # the curve row already. Order is "first appearance" so the primary
        # intercept matches the protocol's declared first spec.
        intercept_keys = _discover_intercept_keys(resolved_runs)
        primary_key = intercept_keys[0] if intercept_keys else None

        # Apply the rule for the primary intercept first — its representative
        # run is the source of truth for the top-level value/qualifier/curve
        # display fields.
        primary_result = apply_selection_rule(
            resolved_runs, selection_rule, qualifier_handling, primary_key
        )
        rep = primary_result.representative_run
        if rep is None:
            return None

        # Build per-intercept aggregates (one for each discovered key).
        intercept_aggregates: list[InterceptAggregate] = []
        for key in intercept_keys:
            agg_result: AggregateResult = (
                primary_result
                if key == primary_key
                else apply_selection_rule(resolved_runs, selection_rule, qualifier_handling, key)
            )
            stats = compute_aggregate_stats(resolved_runs, key)
            disagree = detect_disagreement(resolved_runs, key)
            intercept_aggregates.append(
                InterceptAggregate(
                    spec=_intercept_key_spec(key, resolved_runs),
                    selected_value=agg_result.value,
                    selected_qualifier=agg_result.qualifier.value,
                    aggregate_stats=stats,
                    disagreement_flag=disagree,
                )
            )

        # Build the per-run tooltip payload from the latest N (regardless of
        # which selection rule won) — chemists want chronology, not "what
        # the rule picked". Cap at 10 to keep the wire payload bounded.
        runs_sorted = sorted(
            resolved_runs,
            key=lambda r: (r.run_date is not None, r.run_date),
            reverse=True,
        )
        runs_payload = [_to_run_summary(r) for r in runs_sorted[:_MAX_RUNS_PAYLOAD]]

        condensed = _condense_raw_data(rep.curve_raw_data) if rep.curve_raw_data else None

        # Cell-level qualifier: ND/GT from the primary aggregate's qualifier
        # overrides "no qualifier" on EQ; otherwise carry through.
        cell_qualifier = (
            primary_result.qualifier.value
            if primary_result.qualifier != ValueQualifier.EQ
            else None
        )

        # `intercept_values` on the wire still ships the representative
        # curve's intercept list — the FE search grid reads it directly to
        # render per-intercept cells that aren't part of the column's
        # aggregate pipeline (e.g. legacy display of EC50 alongside the
        # column's primary EC90 selection).
        intercepts_payload = rep.intercept_values

        # In aggregate modes the FE chart's per-curve intercept dashed line
        # would point at the rep's intercept, not the cell's aggregate value.
        # Carry the other contributors + an explicit marker so the chart can
        # overlay them muted and draw a single vertical line at the cell.
        # ``build_aggregate_curve_snapshot`` returns a full snapshot keyed
        # off the rep curve; we lift only the *extras* (the rep curve's own
        # drawable shape is already on this ActivityValue via raw_data /
        # curve_params / intercept_values).
        additional_curves: list[dict[str, Any]] | None = None
        aggregate_marker: dict[str, Any] | None = None
        is_aggregate = selection_rule in {
            SelectionRule.MEAN_ACROSS_RUNS,
            SelectionRule.GEOMETRIC_MEAN,
        }
        if is_aggregate and primary_result.value is not None:
            marker_label = "gmean" if selection_rule == SelectionRule.GEOMETRIC_MEAN else "mean"
            snap = build_aggregate_curve_snapshot(
                resolved_runs,
                aggregate_value=primary_result.value,
                aggregate_label=marker_label,
            )
            if snap is not None:
                additional_curves = snap.get("additional_curves") or None
                aggregate_marker = snap.get("aggregate")

        return ActivityValue(
            value=primary_result.value,
            qualifier=cell_qualifier,
            unit=unit,
            source="dose_response",
            curve_type=rep.curve_type,
            r_squared=rep.curve_r_squared,
            data_point_count=len(rep.curve_raw_data or []),
            raw_data=condensed,
            curve_params=CurveParams(
                hill_slope=rep.curve_hill_slope or 0.0,
                top=rep.curve_top or 0.0,
                bottom=rep.curve_bottom or 0.0,
                num_points=len(rep.curve_raw_data or []),
                curve_class=rep.curve_class,
                confidence_interval_low=rep.curve_confidence_interval_low,
                confidence_interval_high=rep.curve_confidence_interval_high,
                fit_quality_warnings=list(rep.curve_fit_quality_warnings or []) or None,
            ),
            intercept_values=intercepts_payload or None,
            run_count=len(resolved_runs),
            selection_rule=selection_rule.value,
            runs=runs_payload or None,
            intercept_aggregates=intercept_aggregates or None,
            disagreement_flag=(
                intercept_aggregates[0].disagreement_flag if intercept_aggregates else False
            ),
            additional_curves=additional_curves,
            aggregate=aggregate_marker,
        )

    def _build_any_activity(
        self,
        by_rd: dict[uuid.UUID, list[DoseResponseCurve]],
        *,
        readouts: list[tuple[uuid.UUID, AggregatedReadout]] | None = None,
        runs_by_id: dict[uuid.UUID, Run],
        protos: dict[uuid.UUID, Any],
        targets: dict[uuid.UUID, list[str]],
        selection_rule: SelectionRule,
        qualifier_handling: QualifierHandling,
    ) -> AnyProtocolActivity | None:
        """One entry per (protocol, DR readout-def) the molecule has curves in,
        collapsed per readout-def by the same run aggregation as the DR
        columns, plus one entry per matching readout-def named in
        ``any_readout_groups``. Native unit from the protocol; µM only for
        ordering (readout entries have no µM equivalent and sort last)."""
        entries: list[AnyProtocolEntry] = []
        for rd_id, curves in by_rd.items():
            resolved = self._build_resolved_runs(curves, runs_by_id)
            if not resolved:
                continue
            proto = protos.get(curves[0].protocol_id)
            unit = proto.dose_unit.value if proto is not None else "uM"
            av = self._build_dr_activity(
                resolved_runs=resolved,
                unit=unit,
                selection_rule=selection_rule,
                qualifier_handling=qualifier_handling,
            )
            if av is None:
                continue
            entries.append(
                AnyProtocolEntry(
                    protocol_id=curves[0].protocol_id,
                    protocol_name=proto.name if proto is not None else "",
                    protocol_type=proto.protocol_type.value if proto is not None else "",
                    target_names=targets.get(curves[0].protocol_id, []),
                    label=_primary_intercept_label(av),
                    source="dose_response",
                    readout_definition_id=rd_id,
                    value=av.value,
                    qualifier=av.qualifier,
                    unit=unit,
                    value_um=_value_to_micromolar(av.value, unit),
                    curve_class=av.curve_params.curve_class if av.curve_params else None,
                    run_count=av.run_count,
                )
            )
        for proto_id, agg in readouts or []:
            proto = protos.get(proto_id)
            entries.append(
                AnyProtocolEntry(
                    protocol_id=proto_id,
                    protocol_name=proto.name if proto is not None else "",
                    protocol_type=proto.protocol_type.value if proto is not None else "",
                    target_names=targets.get(proto_id, []),
                    label=agg.readout_name,
                    source="readout",
                    readout_definition_id=agg.readout_definition_id,
                    value=agg.value,
                    qualifier=agg.qualifier,
                    unit=agg.unit,
                    value_um=None,
                    curve_class=None,
                    run_count=agg.data_point_count,
                )
            )
        if not entries:
            return None
        entries.sort(key=lambda e: (e.value_um is None, e.value_um or 0.0, e.label))
        return AnyProtocolActivity(entries=entries)


def _discover_intercept_keys(runs: list[ResolvedRun]) -> list[InterceptKey]:
    """Union of (kind, level) tuples across every run's intercept_values.

    Preserves first-appearance order so the column's "primary intercept"
    aligns with the protocol's first declared spec (curves were fit in
    that order). Levels of 0 or 100 (illegal for InterceptKey) are
    silently skipped — a fitter bug would put one there, not chemistry.
    """
    out: list[InterceptKey] = []
    seen: set[tuple[str, float]] = set()
    for run in runs:
        for iv in run.intercept_values or []:
            spec = iv.get("spec") or {}
            kind = spec.get("kind")
            level = spec.get("level")
            if not isinstance(kind, str) or not isinstance(level, (int, float)):
                continue
            if not (0 < float(level) < 100):
                continue
            key = (kind, float(level))
            if key in seen:
                continue
            seen.add(key)
            out.append(InterceptKey(kind=kind, level=float(level)))
    return out


def _intercept_key_spec(key: InterceptKey, runs: list[ResolvedRun]) -> dict[str, Any]:
    """Echo back the persisted spec dict for an intercept key.

    The FE reads ``spec.label`` to render the column header; pulling the
    label from a real curve preserves the basis/label set by the protocol
    rather than re-deriving it.
    """
    for run in runs:
        for iv in run.intercept_values or []:
            spec = iv.get("spec") or {}
            if (
                spec.get("kind") == key.kind
                and isinstance(spec.get("level"), (int, float))
                and float(spec["level"]) == key.level
            ):
                return dict(spec)
    return {"kind": key.kind, "level": key.level}


def _to_run_summary(run: ResolvedRun) -> RunSummary:
    """Adapt a ResolvedRun to its tooltip-payload shape.

    ``run_date`` on RunSummary is non-optional — defensive callers will
    have already filtered out runs without dates, but if one slips through
    we fall back to ``date.min`` so the wire shape stays well-formed.
    """
    from datetime import date

    return RunSummary(
        run_id=run.run_id,
        run_date=run.run_date or date.min,
        curve_id=run.curve_id or run.run_id,
        curve_class=run.curve_class,
        r_squared=run.curve_r_squared,
        intercept_values=list(run.intercept_values or []),
    )


def _primary_intercept_label(av: ActivityValue) -> str:
    """Label of the cell's primary intercept: the protocol's declared label
    when the curve carries it, else the curve type upper-cased ("IC50")."""
    first = (av.intercept_values or [None])[0]
    if isinstance(first, dict):
        spec = first.get("spec") or {}
        if spec.get("label"):
            return str(spec["label"])
        if spec.get("kind") and spec.get("level") is not None:
            return f"{str(spec['kind']).upper()}{int(float(spec['level']))}"
    return (av.curve_type or "").upper()


def _value_to_micromolar(value: float | None, unit: str) -> float | None:
    """µM for ordering only (Python-side twin of the SQL CASE in _activity_query).

    mg/mL needs molecular weight, which this service does not load — those
    entries sort last (None)."""
    if value is None:
        return None
    try:
        factor = ConcentrationUnit(unit).micromolar_factor
    except ValueError:
        return None
    return None if factor is None else value * factor
