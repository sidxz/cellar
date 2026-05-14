"""Activity-based search SQL builders.

Composes molecule filters from screening data — both dose-response curves
and individual readout points — with optional run-scoping (any, latest,
specific, date_range, past_n_days, all).
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.sql import ColumnElement

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
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

    ``run_scope`` (optional) restricts every condition to a subset of runs:
        - ``{"mode": "any"}`` (default): no constraint.
        - ``{"mode": "latest"}``: most recent run for this protocol.
        - ``{"mode": "specific", "run_id": ...}``: a single run.
        - ``{"mode": "date_range", "date_from": ..., "date_to": ...}``.
        - ``{"mode": "past_n_days", "days": N}``: rolling window.
        - ``{"mode": "all"}``: molecule satisfies in every run that has data
          for it (positive match AND no counterexample row).
    """
    protocol_id = criterion["protocol_id"]
    run_scope = criterion.get("run_scope")
    where_list = _normalize_where(criterion)

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
    return [inline]


def _activity_where_clause(
    cond: dict[str, Any],
    protocol_id: Any,
    workspace_id: uuid.UUID,
    run_scope: Any,
) -> ColumnElement:
    """Compose a single where-condition into a molecule-id subquery."""
    rd_id = cond.get("readout_definition_id")
    if not rd_id:
        msg = "where condition needs readout_definition_id"
        raise ValueError(msg)

    source = cond.get("source", "dr_curve")
    if source == "dr_curve":
        data_col = DoseResponseCurveModel.fitted_value
        molecule_col = DoseResponseCurveModel.molecule_id
        run_id_col = DoseResponseCurveModel.run_id
        base_filters: list[ColumnElement] = [
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

    operator = cond.get("operator", "lt")
    if operator == "between":
        if "min" not in cond or "max" not in cond:
            msg = "between operator requires both min and max"
            raise ValueError(msg)
        value_filter = data_col.between(cond["min"], cond["max"])
    else:
        op_name = _ACTIVITY_OP_MAP.get(operator)
        if not op_name:
            msg = f"Unknown activity operator: {operator}"
            raise ValueError(msg)
        if "value" not in cond:
            msg = f"activity operator {operator!r} requires value"
            raise ValueError(msg)
        value_filter = getattr(data_col, op_name)(cond["value"])

    # "all" semantics: molecule has at least one satisfying row AND no
    # non-satisfying row in scope. Implemented as IN(positive) AND NOT IN(negative).
    if isinstance(run_scope, dict) and run_scope.get("mode") == "all":
        positive = MoleculeModel.id.in_(sa.select(molecule_col).where(*base_filters, value_filter))
        no_violation = ~MoleculeModel.id.in_(
            sa.select(molecule_col).where(*base_filters, ~value_filter)
        )
        return sa.and_(positive, no_violation)

    return MoleculeModel.id.in_(sa.select(molecule_col).where(*base_filters, value_filter))


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
        RunModel.protocol_id == protocol_id,
    ]

    if isinstance(run_scope, dict):
        mode = run_scope.get("mode", "any")
        if mode == "specific":
            run_id = run_scope.get("run_id")
            if not run_id:
                msg = "run_scope mode='specific' requires run_id"
                raise ValueError(msg)
            conds.append(ReadoutDataModel.run_id == run_id)
        elif mode == "date_range":
            from datetime import date as _date

            df = run_scope.get("date_from")
            dt = run_scope.get("date_to")
            if df:
                conds.append(RunModel.run_date >= _date.fromisoformat(df))
            if dt:
                conds.append(RunModel.run_date <= _date.fromisoformat(dt))
        elif mode == "past_n_days":
            from datetime import date as _date, timedelta

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
        run_id = run_scope.get("run_id")
        if not run_id:
            msg = "run_scope mode='specific' requires run_id"
            raise ValueError(msg)
        return run_id_col == run_id

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
            msg = f"run_scope mode='past_n_days' requires integer days, got {run_scope.get('days')!r}"
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
