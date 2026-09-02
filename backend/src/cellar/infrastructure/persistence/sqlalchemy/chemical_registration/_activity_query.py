"""Activity-based search SQL builders.

Composes molecule filters from screening data — both dose-response curves
and individual readout points — with optional run-scoping (any, latest,
specific, date_range, past_n_days, all).
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import ColumnElement

from cellar.domain.shared.enums import ConcentrationUnit
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
    ProtocolModel,
    ReadoutDataModel,
    RunModel,
)

_ACTIVITY_OP_MAP: dict[str, str] = {
    "eq": "__eq__",
    "lt": "__lt__",
    "lte": "__le__",
    "gt": "__gt__",
    "gte": "__ge__",
    # "between" is handled separately (uses min+max instead of value).
}


def _activity_clause(criterion: dict[str, Any], workspace_id: uuid.UUID) -> ColumnElement:
    """Filter molecules by biological activity values.

    Each condition names a readout-def and a ``source`` discriminator
    (``"dr_curve"`` → dose_response_curves table, ``"readout_data"`` → the
    raw readout_data table). The readout-def is identity-bearing — on a
    multi-DR protocol where two DR readouts share a curve_type (target
    IC50 + counter-screen IC50), the readout-def is the only thing that
    tells them apart.

    Shapes accepted:
        - **Multi-where:** ``where: [{source, readout_definition_id,
          operator, value or min/max}, ...]`` — each condition becomes a
          subquery, all ANDed together. Empty list ⇒ presence-only filter.
        - **Single-where:** inline ``source`` + ``readout_definition_id``
          plus ``operator`` and ``value`` (or ``min``/``max`` for
          ``between``). Treated as a single-element where list.
        - **Presence-only:** neither shape provides a where condition.

    ``protocol_id`` may be absent/None ⇒ **any protocol**. Only the
    presence-only, ``curve_class`` and readout-def-less ``dr_curve``
    (potency in µM, normalized via each protocol's dose_unit) shapes are
    allowed there; ``readout_data`` and every ``run_scope`` other than
    ``any`` are per-protocol by nature and rejected.

    ``run_scope`` (optional) restricts every condition to a subset of runs:
        - ``{"mode": "any"}`` (default): no constraint.
        - ``{"mode": "latest"}``: most recent run for this protocol.
        - ``{"mode": "specific", "run_id": ...}``: a single run.
        - ``{"mode": "date_range", "date_from": ..., "date_to": ...}``.
        - ``{"mode": "past_n_days", "days": N}``: rolling window.
        - ``{"mode": "all"}``: molecule satisfies in every run that has data
          for it (positive match AND no counterexample row).
    """
    protocol_id = criterion.get("protocol_id") or None
    run_scope = criterion.get("run_scope")
    where_list = _normalize_where(criterion)

    scoped = isinstance(run_scope, dict) and run_scope.get("mode", "any") != "any"
    if protocol_id is None and scoped:
        msg = "run_scope needs a protocol_id; any-protocol activity only supports mode='any'"
        raise ValueError(msg)

    if not where_list:
        return _activity_presence_clause(workspace_id, protocol_id, run_scope)

    clauses = [
        _activity_where_clause(cond, protocol_id, workspace_id, run_scope) for cond in where_list
    ]
    if len(clauses) == 1:
        return clauses[0]
    return sa.and_(*clauses)


def _normalize_where(criterion: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a list of where-conditions, normalizing the inline single-where shape."""
    where = criterion.get("where")
    if isinstance(where, list):
        return [c for c in where if isinstance(c, dict)]
    if not criterion.get("readout_definition_id"):
        return []
    inline: dict[str, Any] = {
        "source": criterion.get("source", "dr_curve"),
        "readout_definition_id": criterion["readout_definition_id"],
        "operator": criterion.get("operator", "lt"),
    }
    if "value" in criterion:
        inline["value"] = criterion["value"]
    if "min" in criterion:
        inline["min"] = criterion["min"]
    if "max" in criterion:
        inline["max"] = criterion["max"]
    if criterion.get("intercept_key") is not None:
        inline["intercept_key"] = criterion["intercept_key"]
    return [inline]


def _activity_where_clause(
    cond: dict[str, Any],
    protocol_id: Any,
    workspace_id: uuid.UUID,
    run_scope: Any,
) -> ColumnElement:
    """Compose a single where-condition into a molecule-id subquery."""
    source = cond.get("source", "dr_curve")

    # Curve-class is a categorical filter against dose_response_curves.curve_class.
    # It spans *every* DR curve in scope (no readout-def constraint) — matches
    # any molecule that has at least one curve of the picked class in the
    # protocol/scope. Coarser than the dr_curve / readout_data filters.
    if source == "curve_class":
        classes = cond.get("curve_classes") or []
        if not isinstance(classes, list) or not classes:
            msg = "curve_class source requires non-empty curve_classes list"
            raise ValueError(msg)
        base_filters: list[ColumnElement] = [
            DoseResponseCurveModel.workspace_id == workspace_id,
            DoseResponseCurveModel.curve_class.in_(classes),
        ]
        if protocol_id is not None:
            base_filters.append(DoseResponseCurveModel.protocol_id == protocol_id)
        scope_filter = _run_scope_filter(
            run_scope, workspace_id, protocol_id, DoseResponseCurveModel.run_id
        )
        if scope_filter is not None:
            base_filters.append(scope_filter)
        return MoleculeModel.id.in_(
            sa.select(DoseResponseCurveModel.molecule_id).where(*base_filters)
        )

    rd_id = cond.get("readout_definition_id")
    if protocol_id is None:
        if source == "readout_data":
            msg = (
                "readout_data where conditions need a protocol_id (readout-defs are per-protocol)"
            )
            raise ValueError(msg)
        if source == "dr_curve" and not rd_id:
            return _potency_any_protocol_clause(cond, workspace_id)
    if not rd_id:
        msg = "where condition needs readout_definition_id"
        raise ValueError(msg)
    if protocol_id is None:
        msg = "where condition with readout_definition_id needs protocol_id"
        raise ValueError(msg)

    if source == "dr_curve":
        # Pick the column to filter on. The primary intercept is the headline
        # `fitted_value` (indexed, fast). Secondary intercepts (EC90 on an EC50-
        # primary fit, etc.) live in the `intercept_values` JSONB array — keyed
        # by (kind, level) per the spec at
        # docs/superpowers/specs/2026-05-13-dynamic-intercept-columns-design.md.
        ik = cond.get("intercept_key")
        data_col: Any
        if ik is None:
            data_col = DoseResponseCurveModel.fitted_value
        else:
            kind = ik.get("kind") if isinstance(ik, dict) else None
            level = ik.get("level") if isinstance(ik, dict) else None
            if kind not in ("ic", "ec") or not isinstance(level, (int, float)):
                msg = f"Invalid intercept_key on activity where: {ik!r}"
                raise ValueError(msg)
            data_col = _jsonb_intercept_value(kind, float(level))
        molecule_col = DoseResponseCurveModel.molecule_id
        run_id_col = DoseResponseCurveModel.run_id
        base_filters = [
            DoseResponseCurveModel.workspace_id == workspace_id,
            DoseResponseCurveModel.readout_definition_id == rd_id,
        ]
    elif source == "readout_data":
        data_col = ReadoutDataModel.value_numeric
        molecule_col = ReadoutDataModel.molecule_id
        run_id_col = ReadoutDataModel.run_id
        base_filters = [
            ReadoutDataModel.workspace_id == workspace_id,
            ReadoutDataModel.readout_definition_id == rd_id,
            ReadoutDataModel.is_outlier == False,  # noqa: E712
        ]
    else:
        msg = f"Unknown activity where source: {source!r}"
        raise ValueError(msg)

    scope_filter = _run_scope_filter(run_scope, workspace_id, protocol_id, run_id_col)
    if scope_filter is not None:
        base_filters.append(scope_filter)

    value_filter = _value_filter(data_col, cond)

    # "all" semantics: molecule has at least one satisfying row AND no
    # non-satisfying row in scope. Implemented as IN(positive) AND NOT IN(negative).
    if isinstance(run_scope, dict) and run_scope.get("mode") == "all":
        positive = MoleculeModel.id.in_(sa.select(molecule_col).where(*base_filters, value_filter))
        no_violation = ~MoleculeModel.id.in_(
            sa.select(molecule_col).where(*base_filters, ~value_filter)
        )
        return sa.and_(positive, no_violation)

    return MoleculeModel.id.in_(sa.select(molecule_col).where(*base_filters, value_filter))


def _jsonb_intercept_value(kind: str, level: float) -> ColumnElement:
    """Build a SQL expression that pulls the numeric value of a specific
    intercept (identified by (kind, level)) out of the curve's
    ``intercept_values`` JSONB array.

    Used for filtering on a secondary intercept (e.g. EC90 on an EC50-primary
    fit). Returns NULL when the curve has no matching intercept, which makes
    the comparison evaluate to NULL — those rows naturally drop out of the
    IN-subquery without needing an explicit IS NOT NULL guard.

    The expression is parameter-safe (kind/level are bind-params, not literals
    spliced into the path) so PostgreSQL plans the array scan against the
    column index.
    """
    # `column("value", JSONB())` types the table-valued result so the `[]`
    # navigator works on the unpacked element. Without an explicit type the
    # ColumnClause is unspec'd and `iv.c.value["spec"]` raises.
    iv_col = column("value", JSONB())
    iv = sa.func.jsonb_array_elements(DoseResponseCurveModel.intercept_values).table_valued(iv_col)
    return (
        sa.select(sa.cast(iv.c.value["value"].astext, sa.Float))
        .where(
            iv.c.value["spec"]["kind"].astext == kind,
            sa.cast(iv.c.value["spec"]["level"].astext, sa.Float) == level,
        )
        .limit(1)
        .scalar_subquery()
        .correlate(DoseResponseCurveModel)
    )


def _value_filter(data_col: Any, cond: dict[str, Any]) -> ColumnElement:
    """Apply the where-condition's operator (eq/lt/lte/gt/gte/between) to ``data_col``."""
    operator = cond.get("operator", "lt")
    if operator == "between":
        if "min" not in cond or "max" not in cond:
            msg = "between operator requires both min and max"
            raise ValueError(msg)
        return data_col.between(cond["min"], cond["max"])
    op_name = _ACTIVITY_OP_MAP.get(operator)
    if not op_name:
        msg = f"Unknown activity operator: {operator}"
        raise ValueError(msg)
    if "value" not in cond:
        msg = f"activity operator {operator!r} requires value"
        raise ValueError(msg)
    return getattr(data_col, op_name)(cond["value"])


def _fitted_value_micromolar() -> ColumnElement:
    """Primary fitted value of a curve expressed in µM.

    Curves store ``fitted_value`` in the owning protocol's ``dose_unit``.
    Molar units scale by a constant; mg/mL needs the molecule's molecular
    weight (µM = mg/mL × 1e6 / MW) and yields NULL when MW is unknown, so
    that curve simply cannot match a cutoff. The CASE is generated from
    ``ConcentrationUnit`` so a new unit cannot be silently mis-scaled.
    """
    whens = []
    for unit in ConcentrationUnit:
        factor = unit.micromolar_factor
        if factor is None:
            expr = (
                DoseResponseCurveModel.fitted_value * 1_000_000.0 / MoleculeModel.molecular_weight
            )
        else:
            expr = DoseResponseCurveModel.fitted_value * factor
        whens.append((ProtocolModel.dose_unit == unit.value, expr))
    return sa.case(*whens, else_=None)


def _potency_any_protocol_clause(cond: dict[str, Any], workspace_id: uuid.UUID) -> ColumnElement:
    """Molecules with at least one DR curve (any protocol, any readout-def)
    whose primary fitted value, normalized to µM, satisfies the condition."""
    sub = (
        sa.select(DoseResponseCurveModel.molecule_id)
        .join(ProtocolModel, DoseResponseCurveModel.protocol_id == ProtocolModel.id)
        .join(MoleculeModel, DoseResponseCurveModel.molecule_id == MoleculeModel.id)
        .where(
            DoseResponseCurveModel.workspace_id == workspace_id,
            _value_filter(_fitted_value_micromolar(), cond),
        )
    )
    return MoleculeModel.id.in_(sub)


def _activity_presence_clause(
    workspace_id: uuid.UUID,
    protocol_id: Any,
    run_scope: Any,
) -> ColumnElement:
    """Match molecules with any screening data for this protocol (and scope)."""
    # Use ReadoutData -> Run as the canonical screening-data join: every
    # data point ultimately attaches to a run, and run carries protocol.
    conds: list[ColumnElement] = [
        ReadoutDataModel.workspace_id == workspace_id,
        RunModel.workspace_id == workspace_id,
    ]
    if protocol_id is not None:
        conds.append(RunModel.protocol_id == protocol_id)

    if isinstance(run_scope, dict):
        mode = run_scope.get("mode", "any")
        if mode == "specific":
            run_ids = _specific_run_ids(run_scope)
            conds.append(ReadoutDataModel.run_id.in_(run_ids))
        elif mode == "date_range":
            from datetime import date as _date

            df = run_scope.get("date_from")
            dt = run_scope.get("date_to")
            if df:
                conds.append(RunModel.run_date >= _date.fromisoformat(df))
            if dt:
                conds.append(RunModel.run_date <= _date.fromisoformat(dt))
        elif mode == "past_n_days":
            from datetime import date as _date
            from datetime import timedelta

            try:
                days = int(run_scope.get("days", 30))
            except (TypeError, ValueError) as e:
                msg = "run_scope mode='past_n_days' requires integer days"
                raise ValueError(msg) from e
            conds.append(RunModel.run_date >= _date.today() - timedelta(days=max(days, 0)))
        elif mode == "latest":
            conds.append(
                ReadoutDataModel.run_id.in_(
                    sa.select(RunModel.id)
                    .where(
                        RunModel.workspace_id == workspace_id,
                        RunModel.protocol_id == protocol_id,
                    )
                    .order_by(RunModel.created_at.desc())
                    .limit(1)
                )
            )
        elif mode in ("any", "all"):
            pass  # presence + "all" both reduce to "any data point"
        else:
            msg = f"Unknown run_scope mode: {mode!r}"
            raise ValueError(msg)

    return MoleculeModel.id.in_(
        sa.select(ReadoutDataModel.molecule_id)
        .join(RunModel, ReadoutDataModel.run_id == RunModel.id)
        .where(*conds)
    )


def _run_scope_filter(
    run_scope: Any,
    workspace_id: uuid.UUID,
    protocol_id: Any,
    run_id_col: Any,
) -> ColumnElement | None:
    """Build a SQL filter constraining the activity subquery's run_id column.

    Returns ``None`` for ``any`` (or absent run_scope) — no constraint.
    Raises ``ValueError`` on unknown modes.
    """
    from datetime import date, timedelta

    if not isinstance(run_scope, dict):
        return None
    mode = run_scope.get("mode", "any")

    if mode == "any":
        return None

    if mode == "specific":
        run_ids = _specific_run_ids(run_scope)
        # Single id stays an `==` for plan stability; multi-id falls back to IN.
        if len(run_ids) == 1:
            return run_id_col == run_ids[0]
        return run_id_col.in_(run_ids)

    if mode == "date_range":
        conds: list[ColumnElement] = [
            RunModel.workspace_id == workspace_id,
            RunModel.protocol_id == protocol_id,
        ]
        df = run_scope.get("date_from")
        dt = run_scope.get("date_to")
        if df:
            conds.append(RunModel.run_date >= date.fromisoformat(df))
        if dt:
            conds.append(RunModel.run_date <= date.fromisoformat(dt))
        return run_id_col.in_(sa.select(RunModel.id).where(*conds))

    if mode == "past_n_days":
        try:
            days = int(run_scope.get("days", 30))
        except (TypeError, ValueError) as e:
            msg = (
                "run_scope mode='past_n_days' requires integer days, "
                f"got {run_scope.get('days')!r}"
            )
            raise ValueError(msg) from e
        cutoff = date.today() - timedelta(days=max(days, 0))
        return run_id_col.in_(
            sa.select(RunModel.id).where(
                RunModel.workspace_id == workspace_id,
                RunModel.protocol_id == protocol_id,
                RunModel.run_date >= cutoff,
            )
        )

    if mode == "latest":
        latest_run_sq = (
            sa.select(RunModel.id)
            .where(
                RunModel.workspace_id == workspace_id,
                RunModel.protocol_id == protocol_id,
            )
            .order_by(RunModel.created_at.desc())
            .limit(1)
        )
        return run_id_col.in_(latest_run_sq)

    if mode == "all":
        # Caller handles "all" via positive + counterexample subqueries —
        # no per-row run filter applied here.
        return None

    msg = f"Unknown run_scope mode: {mode!r}"
    raise ValueError(msg)


def _specific_run_ids(run_scope: dict[str, Any]) -> list[Any]:
    """Read the ``specific`` run-scope's run id list.

    Accepts both the multi-select wire shape (``run_ids: [..]``) emitted by
    the new search UI and the legacy single-id shape (``run_id: ...``) so
    saved searches and direct API callers keep working without migration.

    Raises ``ValueError`` when neither shape is provided.
    """
    raw = run_scope.get("run_ids")
    if isinstance(raw, list) and raw:
        return list(raw)
    single = run_scope.get("run_id")
    if single:
        return [single]
    msg = "run_scope mode='specific' requires run_id or run_ids"
    raise ValueError(msg)
