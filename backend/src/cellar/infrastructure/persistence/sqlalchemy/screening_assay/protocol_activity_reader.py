"""SQLAlchemy implementation of ProtocolActivityReader."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Row,
    Select,
    Subquery,
    and_,
    case,
    column,
    distinct,
    func,
    join,
    literal_column,
    or_,
    select,
    true,
    union_all,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.application.screening.protocol_activity_reader import (
    ActivityAggregates,
    AggregateScope,
    BestParamsRow,
    DRAggRow,
    MoleculeBaseRow,
    NumericReadoutRow,
    ProtocolActivityData,
    ProtocolRow,
)
from cellar.domain.screening_assay.enums import CurveClass
from cellar.infrastructure.persistence.sqlalchemy._sql import any_id
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeIdentifierModel,
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay._compound_rows_sql import (
    COMPOUND_RESULT,
    curve_doses,
    primary_intercept,
    reported_curve_value,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
    PlateModel,
    ProtocolModel,
    ReadoutDataModel,
    ReadoutDefinitionModel,
    RunModel,
    WellModel,
)

# The one aggregation behind the Activity summary and the workbench's Batches /
# Compounds levels. Qualifier predicates are find_run_stats's: "~" is a value.
_rd = ReadoutDataModel
_UNQUALIFIED = or_(_rd.value_qualifier.is_(None), _rd.value_qualifier.in_(("=", "", "~")))
_GT = _rd.value_qualifier.in_((">", ">="))
_LT = _rd.value_qualifier.in_(("<", "<="))


def _run_condition_sets(ws: uuid.UUID, pid: uuid.UUID) -> Subquery:
    """Each run's condition set (run_id, conditions), computed once per run. Null and
    blank values count as absent, so SQL NULL, JSON null, {}, {"NADP": null} and
    {"NADP": " "} are all {} (``aggregated_dataset._condition_set`` reads runs alike)."""
    conds = RunModel.conditions
    e = (
        func.jsonb_each(case((func.jsonb_typeof(conds) == "object", conds)))
        .table_valued("key", column("value", JSONB))
        .lateral("e")
    )
    blank = and_(
        func.jsonb_typeof(e.c.value) == "string",
        e.c.value.op("#>>")(literal_column("'{}'")).op("~")(literal_column(r"'^\s*$'")),
    )
    kept = and_(func.jsonb_typeof(e.c.value) != "null", ~blank)
    return (
        select(
            RunModel.id.label("run_id"),
            func.coalesce(
                func.jsonb_object_agg(e.c.key, e.c.value).filter(kept),
                literal_column("'{}'::jsonb"),
                type_=JSONB,
            ).label("conditions"),
        )
        .select_from(RunModel)
        .outerjoin(e, true())
        .where(RunModel.workspace_id == ws, RunModel.protocol_id == pid)
        .group_by(RunModel.id)
        .subquery("run_sets")
    )


def _scoped(
    stmt: Select[Any],
    ws: uuid.UUID,
    pid: uuid.UUID,
    scope: AggregateScope,
    *,
    batch: ColumnElement[Any],
    run: ColumnElement[Any],
) -> Select[Any]:
    """Add the group keys the scope asks for, by output name (never an input column's
    name: Postgres resolves an ambiguous GROUP BY name to the input column)."""
    keys: dict[str, ColumnElement[Any]] = {}
    if scope.grain != "compound":
        keys["batch_key"] = batch
    if scope.grain == "run":
        keys["run_key"] = run
    if scope.by_conditions:
        sets = _run_condition_sets(ws, pid)
        stmt = stmt.join(sets, sets.c.run_id == RunModel.id)
        keys["condition_set"] = sets.c.conditions
    return stmt.add_columns(*(expr.label(name) for name, expr in keys.items())).group_by(
        *keys.values()
    )


def _scope_filters(scope: AggregateScope) -> list[ColumnElement[bool]]:
    return [
        *([RunModel.status.in_(scope.statuses)] if scope.statuses is not None else []),
        *([any_id(RunModel.id, scope.run_ids)] if scope.run_ids is not None else []),
    ]


def _numeric_stmt(ws: uuid.UUID, pid: uuid.UUID, scope: AggregateScope) -> Select[Any]:
    """Non-dose-response readout values per (molecule, readout, layer) + scope keys.

    Sample wells and well-less rows only (``COMPOUND_RESULT``); outlier wells never
    count. Censored values are counted with their bounds;
    unless the scope keeps them, they stay out of best/low/mean/n/sd, and the
    median and geomean (positive values only, the others counted) are added as
    find_run_stats computes them, with the strict bounds that tell whether a
    bound is inclusive. The Activity scope's statement has none of these.
    """
    v = _rd.value_numeric
    counted = case((_UNQUALIFIED, v)) if scope.exclude_censored else v
    replicate_stats = (
        [
            func.percentile_cont(0.5).within_group(counted).label("median"),
            func.exp(func.avg(func.ln(case((and_(_UNQUALIFIED, v > 0), v))))).label("geomean"),
            func.count(v).filter(and_(_UNQUALIFIED, v <= 0)).label("nonpositive_count"),
            func.max(v).filter(_rd.value_qualifier == ">").label("gt_strict_bound"),
            func.min(v).filter(_rd.value_qualifier == "<").label("lt_strict_bound"),
        ]
        if scope.exclude_censored
        else []
    )
    keys: dict[str, ColumnElement[Any]] = {
        "molecule_id": _rd.molecule_id,
        "readout_definition_id": _rd.readout_definition_id,
        "readout_name": ReadoutDefinitionModel.name,
        "layer": _rd.normalization_applied,
    }
    stmt = (
        select(
            *(expr.label(name) for name, expr in keys.items()),
            func.max(counted).label("best"),
            func.min(counted).label("low"),
            func.avg(counted).label("mean"),
            func.count(counted).label("n"),
            func.stddev_samp(counted).label("sd"),
            func.count(v).filter(_GT).label("gt_count"),
            func.max(v).filter(_GT).label("gt_bound"),
            func.count(v).filter(_LT).label("lt_count"),
            func.min(v).filter(_LT).label("lt_bound"),
            *replicate_stats,
        )
        .select_from(_rd)
        .join(ReadoutDefinitionModel, _rd.readout_definition_id == ReadoutDefinitionModel.id)
        .join(RunModel, _rd.run_id == RunModel.id)
        .where(
            RunModel.protocol_id == pid,
            RunModel.workspace_id == ws,
            _rd.workspace_id == ws,
            ReadoutDefinitionModel.data_type != "dose_response",
            _rd.molecule_id.isnot(None),
            COMPOUND_RESULT,
            v.isnot(None),
            _rd.is_outlier == False,  # noqa: E712
            *_scope_filters(scope),
        )
        .group_by(*keys.values())
    )
    if scope.grain != "compound":
        # Only a well on a plate of the readout's own run lends its batch.
        stmt = stmt.outerjoin(
            join(WellModel, PlateModel, PlateModel.id == WellModel.plate_id),
            and_(WellModel.id == _rd.well_id, PlateModel.run_id == _rd.run_id),
        )
    batch = func.coalesce(_rd.batch_id, WellModel.batch_id)
    return _scoped(stmt, ws, pid, scope, batch=batch, run=_rd.run_id)


def _doses() -> Subquery:
    """Per curve, its lowest (``lo``) and highest (``hi``) positive dose — the bounds a
    censored potency is quoted at. Lateral: join it on true."""
    pt, dose = curve_doses(DoseResponseCurveModel)
    return (
        select(func.min(dose).label("lo"), func.max(dose).label("hi"))
        .select_from(pt)
        .where(dose > 0)
        .lateral("doses")
    )


def _dr_stmt(ws: uuid.UUID, pid: uuid.UUID, scope: AggregateScope) -> Select[Any]:
    """Dose-response curves per (molecule, readout-def) + scope keys.

    Grouped by readout-def, never curve_type (two DR readouts can share one).
    Active = not inactive and fitted value > 0 (a NULL class is not active);
    best and geo_mean read active curves only, and every curve is counted.
    When the scope excludes censored values, a curve's primary is read as every
    reader reads it (``reported_curve_value``): inactive or "> top dose", active at
    all doses or "< lowest dose", n.d., or exact. A bound is counted, kept out of
    best/geo_mean, and kept; an n.d. curve is only tested. Activity averages every
    fit stored before qualifiers, as before, and a newer one only when its primary
    reads exactly ("=" on a curve not active at all doses).
    """
    c = DoseResponseCurveModel
    active = and_(c.curve_class != "inactive", c.fitted_value > 0)
    fitted, at_bound, stored = primary_intercept(c)
    censored: list[ColumnElement[Any]] = []
    doses = None
    if scope.exclude_censored:
        doses = _doses()
        value, qualifier = reported_curve_value(
            c, fitted, at_bound, stored, lo=doses.c.lo, hi=doses.c.hi
        )
        active = and_(active, qualifier.is_(None), value.is_not(None))
        gt = case((qualifier == ">", value))
        lt = case((qualifier == "<", value))
        censored = [
            (func.count(gt) + func.count(lt)).label("n_censored"),
            func.max(gt).label("censored_bound"),
            func.min(lt).label("censored_below"),
        ]
    else:
        exact = and_(stored == "=", c.curve_class != CurveClass.ACTIVE_ALL_DOSES.value)
        active = and_(active, or_(stored.is_(None), exact))
    used = case((active, c.fitted_value))
    keys: dict[str, ColumnElement[Any]] = {
        "molecule_id": c.molecule_id,
        "readout_definition_id": c.readout_definition_id,
    }
    stmt = (
        select(
            *(expr.label(name) for name, expr in keys.items()),
            func.min(used).label("best"),
            func.exp(func.avg(func.ln(used))).label("geo_mean"),
            func.count().label("n_tested"),
            func.count().filter(c.curve_class == "inactive").label("n_inactive"),
            func.count().filter(active).label("n_used"),
            *censored,
        )
        .select_from(c)
        .join(RunModel, c.run_id == RunModel.id)
        .where(
            c.protocol_id == pid,
            c.workspace_id == ws,
            RunModel.workspace_id == ws,
            *_scope_filters(scope),
        )
        .group_by(*keys.values())
    )
    if doses is not None:
        stmt = stmt.outerjoin(doses, true())
    return _scoped(stmt, ws, pid, scope, batch=c.batch_id, run=c.run_id)


def _potency_rank() -> ColumnElement[int]:
    """Best curve first: one below the doses (active at all of them, or a primary stored
    "<"), then exact fits by fitted value, then "> top dose" and n.d. ones, whose fitted
    value is a midpoint, not a potency. Fits stored before qualifiers rank as exact."""
    c = DoseResponseCurveModel
    _, _, stored = primary_intercept(c)
    return case(
        (or_(c.curve_class == CurveClass.ACTIVE_ALL_DOSES.value, stored == "<"), 0),
        (stored.in_((">", "nd")), 2),
        else_=1,
    )


def _inclusive(bound: float | None, strict: float | None, *, above: bool) -> bool:
    """A ">="/"<=" bound unless a strict value sits on (or beyond) it."""
    if bound is None:
        return False
    return strict is None or (strict < bound if above else strict > bound)


def _numeric_row(r: Row[Any]) -> NumericReadoutRow:
    m = r._mapping
    return NumericReadoutRow(
        molecule_id=r.molecule_id,
        readout_name=r.readout_name,
        best=r.best,
        mean=r.mean,
        n=r.n,
        sd=r.sd,
        low=r.low,
        layer=r.layer,
        readout_definition_id=r.readout_definition_id,
        batch_id=m.get("batch_key"),
        run_id=m.get("run_key"),
        conditions=m.get("condition_set"),
        gt_count=r.gt_count,
        gt_bound=r.gt_bound,
        lt_count=r.lt_count,
        lt_bound=r.lt_bound,
        median=m.get("median"),
        geomean=m.get("geomean"),
        nonpositive_count=m.get("nonpositive_count", 0),
        gt_inclusive="gt_strict_bound" in m
        and _inclusive(r.gt_bound, m["gt_strict_bound"], above=True),
        lt_inclusive="lt_strict_bound" in m
        and _inclusive(r.lt_bound, m["lt_strict_bound"], above=False),
    )


def _dr_row(r: Row[Any]) -> DRAggRow:
    m = r._mapping
    return DRAggRow(
        molecule_id=r.molecule_id,
        readout_definition_id=r.readout_definition_id,
        best=r.best,
        geo_mean=r.geo_mean,
        batch_id=m.get("batch_key"),
        run_id=m.get("run_key"),
        conditions=m.get("condition_set"),
        n_tested=r.n_tested,
        n_inactive=r.n_inactive,
        n_used=r.n_used,
        n_censored=m.get("n_censored", 0),
        censored_bound=m.get("censored_bound"),
        censored_below=m.get("censored_below"),
    )


class SQLAlchemyProtocolActivityReader:
    """Infrastructure-layer read model for protocol activity queries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_activity_data(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        valid_statuses: tuple[str, ...],
    ) -> ProtocolActivityData:
        ws = workspace_id
        pid = protocol_id

        async with self._session_factory() as session:
            # ----------------------------------------------------------
            # Load protocol
            # ----------------------------------------------------------
            protocol_stmt = select(ProtocolModel).where(
                ProtocolModel.id == pid,
                ProtocolModel.workspace_id == ws,
            )
            protocol_model = (await session.execute(protocol_stmt)).scalar_one_or_none()

            if protocol_model is None:
                return ProtocolActivityData(protocol=None)

            protocol = ProtocolRow(
                id=protocol_model.id,
                readout_definitions=list(protocol_model.readout_definitions),
            )

            # ----------------------------------------------------------
            # Query 1: Molecule base — all molecules with readout data
            #          OR dose-response curves
            # ----------------------------------------------------------
            # Source A: molecules from readout data
            rd_mols = (
                select(
                    ReadoutDataModel.molecule_id,
                    func.count(distinct(ReadoutDataModel.run_id)).label("run_count"),
                    func.max(RunModel.run_date).label("last_tested"),
                )
                .select_from(ReadoutDataModel)
                .join(RunModel, ReadoutDataModel.run_id == RunModel.id)
                .where(
                    RunModel.protocol_id == pid,
                    RunModel.workspace_id == ws,
                    RunModel.status.in_(valid_statuses),
                    ReadoutDataModel.molecule_id.isnot(None),
                    COMPOUND_RESULT,
                )
                .group_by(ReadoutDataModel.molecule_id)
            )

            # Source B: molecules from dose-response curves only
            drc_mols = (
                select(
                    DoseResponseCurveModel.molecule_id,
                    func.count(distinct(DoseResponseCurveModel.run_id)).label("run_count"),
                    func.max(RunModel.run_date).label("last_tested"),
                )
                .join(RunModel, DoseResponseCurveModel.run_id == RunModel.id)
                .where(
                    DoseResponseCurveModel.protocol_id == pid,
                    RunModel.workspace_id == ws,
                    RunModel.status.in_(valid_statuses),
                )
                .group_by(DoseResponseCurveModel.molecule_id)
            )

            # Merge: take max run_count and latest date per molecule
            combined = union_all(rd_mols, drc_mols).subquery("combined")
            mol_stmt = (
                select(
                    combined.c.molecule_id,
                    MoleculeModel.name.label("molecule_name"),
                    MoleculeModel.registration_number,
                    MoleculeModel.smiles,
                    func.max(combined.c.run_count).label("run_count"),
                    func.max(combined.c.last_tested).label("last_tested"),
                )
                .join(MoleculeModel, combined.c.molecule_id == MoleculeModel.id)
                .group_by(
                    combined.c.molecule_id,
                    MoleculeModel.name,
                    MoleculeModel.registration_number,
                    MoleculeModel.smiles,
                )
            )
            raw_mol_rows = (await session.execute(mol_stmt)).all()

            molecule_rows = [
                MoleculeBaseRow(
                    molecule_id=r.molecule_id,
                    molecule_name=r.molecule_name,
                    registration_number=r.registration_number,
                    smiles=r.smiles,
                    run_count=r.run_count,
                    last_tested=r.last_tested,
                )
                for r in raw_mol_rows
            ]

            # Batch-load synonyms for all molecules
            mol_ids = [r.molecule_id for r in molecule_rows]
            synonym_map: dict[uuid.UUID, list[str]] = {}
            if mol_ids:
                syn_stmt = select(
                    MoleculeIdentifierModel.molecule_id,
                    MoleculeIdentifierModel.identifier,
                ).where(
                    MoleculeIdentifierModel.molecule_id.in_(mol_ids),
                    MoleculeIdentifierModel.identifier_type == "custom",
                )
                syn_rows = (await session.execute(syn_stmt)).all()
                for sr in syn_rows:
                    synonym_map.setdefault(sr.molecule_id, []).append(sr.identifier)

            if not molecule_rows:
                return ProtocolActivityData(
                    protocol=protocol,
                    molecule_rows=[],
                    synonym_map={},
                    numeric_rows=[],
                    dr_agg_rows=[],
                    best_params_rows=[],
                )

            # ----------------------------------------------------------
            # Query 2 + 3a: the shared aggregation. Numeric rows come one per
            # normalization layer (the use case picks each readout's layer)
            # and keep today's averaging of censored values; DR rows carry
            # geo mean + min over active curves per readout-def.
            # ----------------------------------------------------------
            activity_scope = AggregateScope(statuses=valid_statuses, exclude_censored=False)
            numeric_rows = [
                _numeric_row(r)
                for r in (await session.execute(_numeric_stmt(ws, pid, activity_scope))).all()
            ]
            dr_agg_rows = [
                _dr_row(r)
                for r in (await session.execute(_dr_stmt(ws, pid, activity_scope))).all()
            ]

            # ----------------------------------------------------------
            # Query 3b: Best curve params — MIN fitted_value per molecule
            # ----------------------------------------------------------
            ranked_sub = (
                select(
                    DoseResponseCurveModel.molecule_id,
                    DoseResponseCurveModel.readout_definition_id,
                    DoseResponseCurveModel.curve_class,
                    DoseResponseCurveModel.hill_slope,
                    DoseResponseCurveModel.top,
                    DoseResponseCurveModel.bottom,
                    DoseResponseCurveModel.fitted_value,
                    DoseResponseCurveModel.r_squared,
                    DoseResponseCurveModel.raw_data,
                    DoseResponseCurveModel.intercept_values,
                    BatchModel.batch_number,
                    func.row_number()
                    .over(
                        partition_by=[
                            DoseResponseCurveModel.molecule_id,
                            DoseResponseCurveModel.readout_definition_id,
                        ],
                        order_by=(_potency_rank(), DoseResponseCurveModel.fitted_value.asc()),
                    )
                    .label("rn"),
                )
                .join(RunModel, DoseResponseCurveModel.run_id == RunModel.id)
                .outerjoin(BatchModel, DoseResponseCurveModel.batch_id == BatchModel.id)
                .where(
                    DoseResponseCurveModel.protocol_id == pid,
                    RunModel.workspace_id == ws,
                    RunModel.status.in_(valid_statuses),
                    DoseResponseCurveModel.curve_class != "inactive",
                    DoseResponseCurveModel.fitted_value > 0,
                )
                .subquery()
            )
            best_params_stmt = select(ranked_sub).where(ranked_sub.c.rn == 1)
            raw_best_params_rows = (await session.execute(best_params_stmt)).all()

            best_params_rows = [
                BestParamsRow(
                    molecule_id=r.molecule_id,
                    readout_definition_id=r.readout_definition_id,
                    intercept_values=r.intercept_values,
                    curve_class=r.curve_class,
                    hill_slope=r.hill_slope,
                    top=r.top,
                    bottom=r.bottom,
                    fitted_value=r.fitted_value,
                    r_squared=r.r_squared,
                    raw_data=r.raw_data,
                    batch_number=r.batch_number,
                )
                for r in raw_best_params_rows
            ]

        return ProtocolActivityData(
            protocol=protocol,
            molecule_rows=molecule_rows,
            synonym_map=synonym_map,
            numeric_rows=numeric_rows,
            dr_agg_rows=dr_agg_rows,
            best_params_rows=best_params_rows,
        )

    async def get_aggregates(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        scope: AggregateScope,
    ) -> ActivityAggregates:
        async with self._session_factory() as session:
            numeric = (
                await session.execute(_numeric_stmt(workspace_id, protocol_id, scope))
            ).all()
            dr = (await session.execute(_dr_stmt(workspace_id, protocol_id, scope))).all()
        return ActivityAggregates(
            numeric_rows=[_numeric_row(r) for r in numeric],
            dr_agg_rows=[_dr_row(r) for r in dr],
        )
