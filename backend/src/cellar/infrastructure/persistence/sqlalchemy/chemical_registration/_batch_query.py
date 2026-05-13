"""Batch-level and cross-protocol selectivity SQL builders.

Owns the batch field maps + the ``_batch_clause`` dispatcher (text /
numeric / date sub-types) and the ``_selectivity_clause`` ratio filter.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.sql import ColumnElement

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration._field_clauses import (
    escape_like,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
)

# ── Batch field maps ────────────────────────────────────────────────────────

BATCH_TEXT_FIELDS: dict[str, Any] = {
    "batch_number": BatchModel.batch_number,
    "source": BatchModel.source,
    "salt_name": BatchModel.salt_name,
    "vendor_catalog_number": BatchModel.vendor_catalog_number,
    "notebook_reference": BatchModel.notebook_reference,
}

BATCH_NUMERIC_FIELDS: dict[str, Any] = {
    "purity": BatchModel.purity,
    "amount_value": BatchModel.amount_value,
}


def _batch_clause(criterion: dict[str, Any], workspace_id: uuid.UUID) -> ColumnElement:
    """Filter molecules by batch-level fields.

    Supported sub-types:
    - ``field_type: "text"`` — text match on batch_number, source, etc.
    - ``field_type: "numeric"`` — numeric comparison on purity, amount.
    - ``field_type: "date"`` — date range on synthesis_date.
    """
    from datetime import date

    field_type = criterion.get("field_type", "text")
    ws_filter = [BatchModel.workspace_id == workspace_id]

    if field_type == "text":
        field_name = criterion["field"]
        if field_name not in BATCH_TEXT_FIELDS:
            msg = f"Unknown batch text field: {field_name}"
            raise ValueError(msg)

        column = BATCH_TEXT_FIELDS[field_name]
        operator = criterion.get("operator", "contains")
        value = criterion["value"]

        if operator == "contains":
            cond = column.ilike(f"%{escape_like(value)}%", escape="\\")
        elif operator == "equals":
            cond = column == value
        elif operator == "starts_with":
            cond = column.ilike(f"{escape_like(value)}%", escape="\\")
        else:
            msg = f"Unknown batch text operator: {operator}"
            raise ValueError(msg)

        return MoleculeModel.id.in_(sa.select(BatchModel.molecule_id).where(*ws_filter, cond))

    elif field_type == "numeric":
        field_name = criterion["field"]
        if field_name not in BATCH_NUMERIC_FIELDS:
            msg = f"Unknown batch numeric field: {field_name}"
            raise ValueError(msg)

        column = BATCH_NUMERIC_FIELDS[field_name]
        operator = criterion.get("operator", "eq")
        value = criterion.get("value")

        op_map = {
            "eq": "__eq__",
            "lt": "__lt__",
            "lte": "__le__",
            "gt": "__gt__",
            "gte": "__ge__",
        }

        if operator == "between":
            cond = column.between(criterion["min"], criterion["max"])
        elif operator in op_map:
            cond = getattr(column, op_map[operator])(value)
        else:
            msg = f"Unknown batch numeric operator: {operator}"
            raise ValueError(msg)

        return MoleculeModel.id.in_(sa.select(BatchModel.molecule_id).where(*ws_filter, cond))

    elif field_type == "date":
        date_from = criterion.get("date_from")
        date_to = criterion.get("date_to")

        conditions: list[ColumnElement] = list(ws_filter)
        if date_from:
            conditions.append(BatchModel.synthesis_date >= date.fromisoformat(date_from))
        if date_to:
            conditions.append(BatchModel.synthesis_date <= date.fromisoformat(date_to))

        if len(conditions) <= len(ws_filter):
            msg = "batch date criterion requires at least date_from or date_to"
            raise ValueError(msg)

        return MoleculeModel.id.in_(sa.select(BatchModel.molecule_id).where(*conditions))

    else:
        msg = f"Unknown batch field_type: {field_type}"
        raise ValueError(msg)


def _selectivity_clause(criterion: dict[str, Any], workspace_id: uuid.UUID) -> ColumnElement:
    """Filter molecules by cross-protocol selectivity ratio.

    Finds molecules where ``counter_fitted_value / target_fitted_value``
    meets the specified ratio threshold.  A high ratio means the compound
    is much more potent at the target than the counter-screen.

    Example criterion::

        {
            "type": "selectivity",
            "target_protocol_id": "<uuid>",
            "target_curve_type": "ic50",
            "counter_protocol_id": "<uuid>",
            "counter_curve_type": "ic50",
            "ratio_operator": "gte",
            "ratio_value": 100,
        }
    """
    target_pid = criterion["target_protocol_id"]
    target_ct = criterion["target_curve_type"]
    counter_pid = criterion["counter_protocol_id"]
    counter_ct = criterion["counter_curve_type"]
    ratio_op = criterion.get("ratio_operator", "gte")
    ratio_val = criterion["ratio_value"]

    op_map = {
        "eq": "__eq__",
        "lt": "__lt__",
        "lte": "__le__",
        "gt": "__gt__",
        "gte": "__ge__",
    }
    op_name = op_map.get(ratio_op)
    if not op_name:
        msg = f"Unknown selectivity ratio operator: {ratio_op}"
        raise ValueError(msg)

    t = DoseResponseCurveModel.__table__.alias("target_drc")
    c = DoseResponseCurveModel.__table__.alias("counter_drc")

    ratio_expr = sa.cast(c.c.fitted_value, sa.Numeric) / sa.func.nullif(
        sa.cast(t.c.fitted_value, sa.Numeric), 0
    )

    return MoleculeModel.id.in_(
        sa.select(t.c.molecule_id)
        .join(c, t.c.molecule_id == c.c.molecule_id)
        .where(
            t.c.workspace_id == workspace_id,
            t.c.protocol_id == target_pid,
            t.c.curve_type == target_ct,
            c.c.workspace_id == workspace_id,
            c.c.protocol_id == counter_pid,
            c.c.curve_type == counter_ct,
            getattr(ratio_expr, op_name)(ratio_val),
        )
    )
