"""MoleculeActivityService -- read-model crossing Molecule and Screening boundaries.

This service provides activity data for molecule detail pages and enriched
search results. It queries readout data and dose-response curves grouped
by protocol.

DR enrichment uses the shared aggregator (``run_aggregation``) — same code
path the campaign grid uses — so the search grid stops cherry-picking the
best-R² curve and instead applies a chemist-correct selection rule (default
``LATEST_RUN`` with ``EXCLUDE_QUALIFIED`` handling) over every
in-scope run of the (compound, readout-def) cell.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from cellar.application.screening import _condense_raw_data
from cellar.application.screening.curve_snapshot import build_aggregate_curve_snapshot
from cellar.application.screening.run_aggregation import (
    AggregateResult,
    ResolvedRun,
    apply_selection_rule,
    combine_replicates,
    compute_aggregate_stats,
    detect_disagreement,
    effective_rule,
)
from cellar.application.screening.search_column_plan import (
    ANY_COLUMN,
    ColumnGroup,
    ColumnPlan,
    SearchColumnPlanner,
)
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.activity_types import (
    ActivitySummary,
    ActivityValue,
    AnyProtocolActivity,
    AnyProtocolEntry,
    CurveParams,
    InterceptAggregate,
    ProtocolActivitySummary,
    ReadoutSummary,
    RunHeader,
    RunLink,
    RunReadoutStats,
    RunSummary,
)
from cellar.domain.screening_assay.aggregation_types import (
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.screening_assay.curve_fitting import InterceptValue
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import ReadoutDataType, RunStatus
from cellar.domain.screening_assay.readout_best import best_direction, pick_best
from cellar.domain.screening_assay.repository import (
    DoseResponseCurveRepository,
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from cellar.domain.screening_assay.run import Run
from cellar.domain.screening_assay.run_scope import RunScope
from cellar.domain.shared.enums import ConcentrationUnit
from cellar.domain.shared.hit_criterion import HitCriterion, InterceptKey
from cellar.domain.shared.units import is_concentration_unit

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


_FINISHED = (RunStatus.COMPLETED, RunStatus.APPROVED)
_VALUE_QUALIFIER = {"=": ValueQualifier.EQ, ">": ValueQualifier.GT, "<": ValueQualifier.LT}


def _plain_readouts(
    proto: Any, rows: list[Any], runs_by_id: dict[uuid.UUID, Run]
) -> list[ReadoutSummary]:
    """One summary per plain numeric readout of the protocol the molecule has values on.

    Raw layer only (a normalized layer is a different quantity), outliers left
    out, every run counted (drafts too, counted separately for the page to mark).
    """
    out: list[ReadoutSummary] = []
    for rd in getattr(proto, "readout_definitions", []):
        if getattr(rd, "data_type", None) != ReadoutDataType.NUMERIC or getattr(
            rd, "dose_response_config", None
        ):
            continue
        mine = [
            r
            for r in rows
            if r.readout_definition_id == rd.id
            and r.normalization_applied is None
            and not r.is_outlier
            and r.value is not None
        ]
        if not mine:
            continue
        mc = rd.melt_config
        direction = best_direction(rd.data_type.value, mc.measure.value if mc else None)
        best = pick_best([(r.value.value, r.value.qualifier) for r in mine], direction)
        run_ids = {r.run_id for r in mine}
        out.append(
            ReadoutSummary(
                readout_definition_id=rd.id,
                readout_name=rd.name,
                value=best[0],  # type: ignore[index]
                qualifier=best[1].value,  # type: ignore[index]
                unit=rd.unit,
                data_point_count=len(mine),
                run_count=len(run_ids),
                draft_run_count=sum(
                    1
                    for rid in run_ids
                    if (run := runs_by_id.get(rid)) is not None and run.status not in _FINISHED
                ),
                best_direction=direction.value,
            )
        )
    return out


def _has_melt_readout(proto: Any, plain: list[ReadoutSummary]) -> bool:
    """A thermal-shift readout among the shown ones: its results live on the Traces tab."""
    shown = {p.readout_definition_id for p in plain}
    return any(
        rd.id in shown and getattr(rd, "melt_config", None) is not None
        for rd in getattr(proto, "readout_definitions", [])
    )


def _protocol_hit(
    rules: list[HitCriterion],
    proto: Any,
    plain: list[ReadoutSummary],
    curves: list[DoseResponseCurve],
) -> bool:
    """Every recommended rule met by the molecule's values (the protocol Activity tab's rule).

    A plain readout uses its best value; a dose-response readout its best
    (lowest) fit, or the named intercept; Curve Class any curve's class. A
    rule with no value to test is not met.
    """
    plain_by_name = {p.readout_name: p for p in plain}
    rd_by_name = {rd.name: rd for rd in getattr(proto, "readout_definitions", [])}
    for rule in rules:
        if rule.readout_name == "Curve Class":
            classes = {c.curve_class.value for c in curves if c.curve_class is not None}
            met = isinstance(rule.value, list) and bool(classes & set(rule.value))
        elif (p := plain_by_name.get(rule.readout_name)) is not None:
            met = bool(rule.is_met(p.value, _VALUE_QUALIFIER.get(p.qualifier, ValueQualifier.EQ)))
        else:
            rd = rd_by_name.get(rule.readout_name)
            fits: list[float] = []
            for c in curves:
                if rd is None or c.readout_definition_id != rd.id:
                    continue
                if rule.intercept_key is None:
                    fits.append(c.fitted_value)
                else:
                    fits.extend(
                        iv.value
                        for iv in c.intercept_values or []
                        if iv.spec.kind.value == rule.intercept_key.kind
                        and iv.spec.level == rule.intercept_key.level
                    )
            met = bool(fits) and bool(rule.is_met(min(fits)))
        if not met:
            return False
    return True


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

        # Reported-endpoint fallback (spec D1) — the detail-page twin of the
        # `drc:` fallback in ``_enrich_molecules``. A summary-imported IC50
        # leaves no curve behind, so curves alone would hide its protocol from
        # this page entirely. The raw readout rows name the runs, the runs name
        # the protocols.
        # ponytail: loads every readout row for the compound (one query, single
        # molecule); swap for a DISTINCT (run_id, readout_definition_id)
        # projection if a heavily-screened compound makes it bite.
        readout_rows = await self._readout_repo.find_by_molecule(workspace_id, molecule_id)
        # Raw layer AND well-less: a reported endpoint records no plate
        # position, so per-well response readings can't masquerade as one.
        endpoint_rows = [
            row
            for row in readout_rows
            if row.normalization_applied is None and row.well_id is None
        ]
        raw_rd_ids = {row.readout_definition_id for row in endpoint_rows}
        # Every run behind a readout row: endpoints and plain readouts name
        # their protocol through it, and plain readouts mark draft runs.
        run_ids = {r.run_id for r in readout_rows} | {
            c.run_id for c in curves if getattr(c, "run_id", None) is not None
        }
        runs_by_id = (
            await self._run_repo.find_by_ids(workspace_id, list(run_ids)) if run_ids else {}
        )
        curve_proto_ids = {curve.protocol_id for curve in curves}
        proto_ids |= {run.protocol_id for run in runs_by_id.values()}
        protocols_found: dict[uuid.UUID, Any] = {}

        # Fetch protocol metadata (single query) — used for display
        # name/type, dose_unit (for IC50 unit decoration), and the
        # protocol's declared intercept specs (per-Card column headers
        # on the molecule activity tab).
        protocols_by_id: dict[uuid.UUID, tuple[str, str, str]] = {}
        intercepts_by_proto: dict[uuid.UUID, list[dict[str, Any]]] = {}
        # (readout_definition_id, protocol_id) for every DR readout-def this
        # molecule has a raw row but no fitted curve for.
        endpoint_defs: dict[uuid.UUID, uuid.UUID] = {}
        curve_rd_ids = {curve.readout_definition_id for curve in curves}
        if proto_ids:
            protos = await self._protocol_repo.find_by_ids(workspace_id, list(proto_ids))
            for proto in protos:
                protocols_found[proto.id] = proto
                endpoint_defs.update(
                    {
                        rd.id: proto.id
                        for rd in proto.readout_definitions
                        if rd.dose_response_config is not None
                        and rd.id in raw_rd_ids
                        and rd.id not in curve_rd_ids
                    }
                )
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

        # One aggregate query for every reported endpoint on the page.
        endpoints_by_proto: dict[uuid.UUID, list[ActivityValue]] = {}
        if endpoint_defs:
            aggregated = await self._readout_repo.find_aggregated_by_molecules(
                workspace_id,
                [molecule_id],
                [(rd_id, None) for rd_id in endpoint_defs],
                wellless_only=True,
            )
            for (rd_id, _norm), agg in aggregated.get(molecule_id, {}).items():
                endpoints_by_proto.setdefault(endpoint_defs[rd_id], []).append(
                    ActivityValue(
                        value=agg.value,
                        qualifier=agg.qualifier,
                        unit=agg.unit,
                        source="readout",
                        data_point_count=agg.data_point_count,
                    )
                )

        summaries: list[ProtocolActivitySummary] = []
        for pid in sorted(proto_ids):
            # A protocol reached only through readout rows earns a card only if
            # it actually yielded an endpoint — otherwise a well-less row on
            # some unrelated readout would add an empty card.
            proto = protocols_found.get(pid)
            plain = _plain_readouts(proto, readout_rows, runs_by_id) if proto else []
            if pid not in curve_proto_ids and not endpoints_by_proto.get(pid) and not plain:
                continue
            name, ptype, _unit = protocols_by_id.get(pid, ("Unknown", "unknown", "uM"))
            rules = list(getattr(proto, "recommended_hit_criteria", None) or [])
            summaries.append(
                ProtocolActivitySummary(
                    protocol_id=pid,
                    protocol_name=name,
                    protocol_type=ptype,
                    readouts=endpoints_by_proto.get(pid, []),
                    best_curves=curves_by_proto.get(pid, []),
                    intercepts=intercepts_by_proto.get(pid, []),
                    plain_readouts=plain,
                    hit=(
                        _protocol_hit(
                            rules, proto, plain, [c for c in curves if c.protocol_id == pid]
                        )
                        if rules
                        else None
                    ),
                    hit_criteria=[r.to_dict() for r in rules],
                    protocol_code=getattr(proto, "code", None),
                    runs=sorted(
                        (
                            RunLink(run.id, run.run_date, run.status.value, run.notes)
                            for run in runs_by_id.values()
                            if run.protocol_id == pid
                        ),
                        key=lambda r: (r.run_date, str(r.run_id)),
                        reverse=True,
                    ),
                    results_tab=(
                        "curves"
                        if _has_melt_readout(proto, plain)
                        else "dose-response"
                        if pid in curve_proto_ids
                        else None
                    ),
                )
            )

        return ActivitySummary(molecule_id=molecule_id, protocols=summaries)

    @property
    def planner(self) -> SearchColumnPlanner:
        """Plans search columns over this service's protocol and run repositories."""
        return SearchColumnPlanner(self._protocol_repo, self._run_repo)

    async def enrich_molecules(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        protocol_columns: list[str],
        *,
        selection_rule: SelectionRule = SelectionRule.LATEST_RUN,
        qualifier_handling: QualifierHandling = QualifierHandling.INCLUDE_QUALIFIED,
        run_scopes: dict[str, RunScope] | None = None,
        any_readout_groups: list[tuple[str, str | None]] | None = None,
    ) -> dict[uuid.UUID, dict[str, ActivityValue | AnyProtocolActivity]]:
        """Unsplit columns with a run scope per token — the SAR colour channels.

        Same calculation as :meth:`enrich_plan`; ``run_scopes`` keys are the
        tokens (``drc:<rd>``, ``rd:<protocol>:<rd>``); a token without one
        reads every non-rejected run.
        """
        if not molecule_ids or not protocol_columns:
            return {}

        async def run() -> dict[uuid.UUID, dict[str, ActivityValue | AnyProtocolActivity]]:
            plan = await self.planner.plan_from_scopes(
                workspace_id, protocol_columns, run_scopes or {}
            )
            return await self._enrich_plan(
                workspace_id,
                molecule_ids,
                plan,
                selection_rule=selection_rule,
                qualifier_handling=qualifier_handling,
                any_readout_groups=any_readout_groups,
                lean=False,
            )

        return await self._in_uow(run)

    async def enrich_plan(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        plan: ColumnPlan,
        *,
        selection_rule: SelectionRule = SelectionRule.LATEST_RUN,
        qualifier_handling: QualifierHandling = QualifierHandling.INCLUDE_QUALIFIED,
        any_readout_groups: list[tuple[str, str | None]] | None = None,
        lean: bool = False,
    ) -> dict[uuid.UUID, dict[str, ActivityValue | AnyProtocolActivity]]:
        """One cell per (molecule, planned column, group), keyed ``column.key(group)``.

        Every cell's runs are the column's protocol's non-rejected runs in its
        run scope, narrowed to the group. Dose-response cells use the fitted
        curves; with no curve in the group they fall back to reported endpoints
        (well-less readout rows). Single-point cells combine each run's
        replicates (``combine_replicates``) and then the runs. Both go through
        ``run_aggregation`` with the column's effective rule. ``lean`` (sorting)
        skips the drawing payload: point arrays, run history, overlays.
        """
        if not molecule_ids or not (plan.columns or plan.want_any):
            return {}
        return await self._in_uow(
            lambda: self._enrich_plan(
                workspace_id,
                molecule_ids,
                plan,
                selection_rule=selection_rule,
                qualifier_handling=qualifier_handling,
                any_readout_groups=any_readout_groups,
                lean=lean,
            )
        )

    async def _in_uow[T](self, fn: Callable[[], Awaitable[T]]) -> T:
        if self._uow.is_active:
            return await fn()
        async with self._uow:
            return await fn()

    async def _enrich_plan(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        plan: ColumnPlan,
        *,
        selection_rule: SelectionRule,
        qualifier_handling: QualifierHandling,
        any_readout_groups: list[tuple[str, str | None]] | None,
        lean: bool,
    ) -> dict[uuid.UUID, dict[str, ActivityValue | AnyProtocolActivity]]:
        dr_by_scope: dict[RunScope, list[uuid.UUID]] = {}
        rd_by_scope: dict[RunScope, list[tuple[uuid.UUID, str | None]]] = {}
        for col in plan.columns:
            if col.kind == "drc":
                dr_by_scope.setdefault(col.run_scope, []).append(col.readout_definition_id)
            else:
                rd_by_scope.setdefault(col.run_scope, []).append(
                    (col.readout_definition_id, col.normalization)
                )

        curves: dict[tuple[uuid.UUID, uuid.UUID], list[DoseResponseCurve]] = {}
        endpoints: dict[tuple[uuid.UUID, uuid.UUID], list[RunReadoutStats]] = {}
        for scope, rd_ids in dr_by_scope.items():
            grouped = await self._curve_repo.find_all_curves_for_molecules(
                workspace_id,
                molecule_ids,
                readout_definition_ids=rd_ids,
                run_scope=scope,
                exclude_rejected=True,
                lean=lean,
            )
            for mol_id, by_rd in grouped.items():
                for rd_id, found in by_rd.items():
                    curves[(mol_id, rd_id)] = found
            for row in await self._readout_repo.find_run_stats(
                workspace_id,
                molecule_ids,
                [(rd_id, None) for rd_id in rd_ids],
                run_scope=scope,
                wellless_only=True,
            ):
                endpoints.setdefault((row.molecule_id, row.readout_definition_id), []).append(row)

        readings: dict[tuple[uuid.UUID, uuid.UUID, str | None], list[RunReadoutStats]] = {}
        for scope, specs in rd_by_scope.items():
            for row in await self._readout_repo.find_run_stats(
                workspace_id, molecule_ids, specs, run_scope=scope
            ):
                key = (row.molecule_id, row.readout_definition_id, row.normalization)
                readings.setdefault(key, []).append(row)

        run_ids = list({c.run_id for found in curves.values() for c in found})
        headers = await self._run_repo.find_headers(workspace_id, run_ids) if run_ids else {}
        dr_protocols = list({c.protocol_id for c in plan.columns if c.kind == "drc"})
        dr_protos = (
            await self._protocol_repo.find_by_ids(workspace_id, dr_protocols)
            if dr_protocols
            else []
        )
        dose_unit = {p.id: p.dose_unit.value for p in dr_protos}
        # A reported endpoint stands for its readout's primary intercept.
        primary_spec = {
            rd.id: _spec_dict(rd.dose_response_config.intercepts[0])
            for p in dr_protos
            for rd in p.readout_definitions
            if rd.dose_response_config and rd.dose_response_config.intercepts
        }

        any_block = (
            await self._any_column(
                workspace_id,
                molecule_ids,
                any_readout_groups=any_readout_groups,
                selection_rule=selection_rule,
                qualifier_handling=qualifier_handling,
                lean=lean,
            )
            if plan.want_any
            else {}
        )

        result: dict[uuid.UUID, dict[str, ActivityValue | AnyProtocolActivity]] = {}
        for mol_id in molecule_ids:
            cells: dict[str, ActivityValue | AnyProtocolActivity] = {}
            for col in plan.columns:
                rd_id = col.readout_definition_id
                for group in col.groups:
                    if col.kind == "drc":
                        av = self._dose_response_cell(
                            [c for c in curves.get((mol_id, rd_id), []) if _in(group, c.run_id)],
                            [
                                r
                                for r in endpoints.get((mol_id, rd_id), [])
                                if _in(group, r.run_id)
                            ],
                            headers=headers,
                            unit=dose_unit.get(col.protocol_id, "uM"),
                            intercept_spec=primary_spec.get(rd_id),
                            selection_rule=selection_rule,
                            qualifier_handling=qualifier_handling,
                            lean=lean,
                        )
                    else:
                        av = _single_point_cell(
                            [
                                r
                                for r in readings.get((mol_id, rd_id, col.normalization), [])
                                if _in(group, r.run_id)
                            ],
                            selection_rule=selection_rule,
                            qualifier_handling=qualifier_handling,
                            lean=lean,
                        )
                    if av is not None:
                        cells[col.key(group)] = av
            if (block := any_block.get(mol_id)) is not None:
                cells[ANY_COLUMN] = block
            if cells:
                result[mol_id] = cells
        return result

    def _dose_response_cell(
        self,
        curves: list[DoseResponseCurve],
        endpoints: list[RunReadoutStats],
        *,
        headers: dict[uuid.UUID, RunHeader],
        unit: str,
        intercept_spec: dict[str, Any] | None,
        selection_rule: SelectionRule,
        qualifier_handling: QualifierHandling,
        lean: bool,
    ) -> ActivityValue | None:
        """Fitted curves win (any class); reported endpoints only when the
        group has none — the campaign channel resolver's rule D1. An endpoint
        cell carries its readout's primary intercept (``intercept_spec``) so
        the grid, sorting and export read it like a fitted cell."""
        resolved = self._build_resolved_runs(curves, headers)
        if resolved:
            return self._build_dr_activity(
                resolved_runs=resolved,
                unit=unit,
                selection_rule=selection_rule,
                qualifier_handling=qualifier_handling,
                lean=lean,
            )
        return _single_point_cell(
            endpoints,
            selection_rule=selection_rule,
            qualifier_handling=qualifier_handling,
            lean=lean,
            intercept_spec=intercept_spec,
        )

    async def _any_column(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        *,
        any_readout_groups: list[tuple[str, str | None]] | None,
        selection_rule: SelectionRule,
        qualifier_handling: QualifierHandling,
        lean: bool = False,
    ) -> dict[uuid.UUID, AnyProtocolActivity]:
        """The "Active in" column: every protocol the molecule has curves in
        (plus readout groups the search names), each collapsed like a column."""
        any_curves = await self._curve_repo.find_all_curves_for_molecules(
            workspace_id,
            molecule_ids,
            readout_definition_ids=None,
            exclude_rejected=True,
            lean=True,  # entries are values only; no point drawing here
        )
        run_ids = list(
            {c.run_id for by_rd in any_curves.values() for cs in by_rd.values() for c in cs}
        )
        headers = await self._run_repo.find_headers(workspace_id, run_ids) if run_ids else {}

        readout_rows: dict[uuid.UUID, dict[uuid.UUID, list[RunReadoutStats]]] = {}
        readout_protocol: dict[uuid.UUID, uuid.UUID] = {}
        if any_readout_groups:
            readout_protocol = await self._readout_repo.find_readout_definitions_by_names(
                workspace_id, any_readout_groups
            )
            if readout_protocol:
                for row in await self._readout_repo.find_run_stats(
                    workspace_id,
                    molecule_ids,
                    [(rd_id, None) for rd_id in readout_protocol],
                    run_scope=RunScope.all(),
                ):
                    readout_rows.setdefault(row.molecule_id, {}).setdefault(
                        row.readout_definition_id, []
                    ).append(row)

        protocol_ids = {
            c.protocol_id for by_rd in any_curves.values() for cs in by_rd.values() for c in cs
        } | set(readout_protocol.values())
        protos: dict[uuid.UUID, Any] = {}
        targets: dict[uuid.UUID, list[str]] = {}
        if protocol_ids:
            for p in await self._protocol_repo.find_by_ids(workspace_id, list(protocol_ids)):
                protos[p.id] = p
            found = await self._protocol_repo.find_effective_targets_for_protocols(
                workspace_id, list(protocol_ids)
            )
            targets = {pid: [t.name for t in refs] for pid, refs in found.items()}

        out: dict[uuid.UUID, AnyProtocolActivity] = {}
        for mol_id in molecule_ids:
            readouts: list[tuple[uuid.UUID, uuid.UUID, ActivityValue, str]] = []
            for rd_id, rows in readout_rows.get(mol_id, {}).items():
                av = _single_point_cell(
                    rows,
                    selection_rule=selection_rule,
                    qualifier_handling=qualifier_handling,
                    lean=True,
                )
                if av is not None:
                    readouts.append((readout_protocol[rd_id], rd_id, av, rows[0].readout_name))
            block = self._build_any_activity(
                any_curves.get(mol_id, {}),
                readouts=readouts,
                runs_by_id=headers,
                protos=protos,
                targets=targets,
                selection_rule=selection_rule,
                qualifier_handling=qualifier_handling,
                lean=lean,
            )
            if block is not None:
                out[mol_id] = block
        return out

    @staticmethod
    def _build_resolved_runs(
        curves: list[DoseResponseCurve], runs_by_id: dict[uuid.UUID, RunHeader]
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
        lean: bool = False,
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
        runs_payload = (
            [] if lean else [_to_run_summary(r) for r in runs_sorted[:_MAX_RUNS_PAYLOAD]]
        )

        condensed = (
            _condense_raw_data(rep.curve_raw_data) if rep.curve_raw_data and not lean else None
        )

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
        if is_aggregate and primary_result.value is not None and not lean:
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
            representative_curve_id=rep.curve_id,
            run_ids=[r.run_id for r in runs_sorted],
        )

    def _build_any_activity(
        self,
        by_rd: dict[uuid.UUID, list[DoseResponseCurve]],
        *,
        readouts: list[tuple[uuid.UUID, uuid.UUID, ActivityValue, str]] | None = None,
        runs_by_id: dict[uuid.UUID, RunHeader],
        protos: dict[uuid.UUID, Any],
        targets: dict[uuid.UUID, list[str]],
        selection_rule: SelectionRule,
        qualifier_handling: QualifierHandling,
        lean: bool = True,
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
                lean=lean,
            )
            if av is None:
                continue
            entries.append(
                AnyProtocolEntry(
                    protocol_id=curves[0].protocol_id,
                    protocol_name=proto.name if proto is not None else "",
                    protocol_code=proto.code if proto is not None else None,
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
        for proto_id, rd_id, av, readout_name in readouts or []:
            proto = protos.get(proto_id)
            entries.append(
                AnyProtocolEntry(
                    protocol_id=proto_id,
                    protocol_name=proto.name if proto is not None else "",
                    protocol_code=proto.code if proto is not None else None,
                    protocol_type=proto.protocol_type.value if proto is not None else "",
                    target_names=targets.get(proto_id, []),
                    label=readout_name,
                    source="readout",
                    readout_definition_id=rd_id,
                    value=av.value,
                    qualifier=av.qualifier,
                    unit=av.unit,
                    value_um=None,
                    curve_class=None,
                    run_count=av.run_count,
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


def _spec_dict(spec: Any) -> dict[str, Any]:
    """An ``InterceptSpec`` in the wire shape intercept values carry."""
    return {
        "kind": spec.kind.value,
        "level": spec.level,
        "basis": spec.basis.value,
        "label": spec.label,
    }


def _in(group: ColumnGroup, run_id: uuid.UUID) -> bool:
    return group.run_ids is None or run_id in group.run_ids


def _single_point_cell(
    rows: list[RunReadoutStats],
    *,
    selection_rule: SelectionRule,
    qualifier_handling: QualifierHandling,
    lean: bool,
    intercept_spec: dict[str, Any] | None = None,
) -> ActivityValue | None:
    """A cell from per-run replicate summaries (single-point readouts and
    reported dose-response endpoints): each run's replicates become one value
    (``combine_replicates``), then the column's effective rule combines runs."""
    if not rows:
        return None
    unit = rows[0].unit
    spec = intercept_spec or {"kind": "value", "label": rows[0].readout_name}
    runs: list[ResolvedRun] = []
    for row in rows:
        value, qualifier = combine_replicates(row.stats, row.aggregation, unit=unit)
        runs.append(
            ResolvedRun(
                run_id=row.run_id,
                run_date=row.run_date,
                run_approved=row.run_status == RunStatus.APPROVED,
                curve_id=None,
                value=value,
                qualifier=qualifier,
                unit=unit or "",
                z_prime=None,
                protocol_name="",
                protocol_version=0,
                readout_id=row.readout_definition_id,
                intercept_values=[{"spec": spec, "value": value, "qualifier": qualifier.value}],
            )
        )
    rule = effective_rule(selection_rule, unit=unit, single_point=True)
    picked = apply_selection_rule(runs, rule, qualifier_handling, None)
    if picked.representative_run is None:
        return None
    newest_first = sorted(runs, key=lambda r: (r.run_date is not None, r.run_date), reverse=True)
    log_scale = is_concentration_unit(unit)
    disagree = detect_disagreement(runs, None, log_scale=log_scale)
    return ActivityValue(
        value=picked.value,
        qualifier=picked.qualifier.value if picked.qualifier != ValueQualifier.EQ else None,
        unit=unit,
        source="readout",
        data_point_count=sum(r.stats.eq_count + r.stats.gt_count + r.stats.lt_count for r in rows),
        run_count=len(runs),
        selection_rule=rule.value,
        runs=None if lean else [_to_run_summary(r) for r in newest_first[:_MAX_RUNS_PAYLOAD]],
        disagreement_flag=disagree,
        # An endpoint cell stands for its readout's primary intercept: the same
        # field a fitted cell's intercept columns, sorting and export read.
        intercept_aggregates=(
            [
                InterceptAggregate(
                    spec=dict(intercept_spec),
                    selected_value=picked.value,
                    selected_qualifier=picked.qualifier.value,
                    aggregate_stats=compute_aggregate_stats(runs, None) if log_scale else None,
                    disagreement_flag=disagree,
                )
            ]
            if intercept_spec
            else None
        ),
        run_ids=[r.run_id for r in newest_first],
    )


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
        curve_id=run.curve_id,
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
