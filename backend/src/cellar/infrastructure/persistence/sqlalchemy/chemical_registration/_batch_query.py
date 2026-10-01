"""Batch-level and cross-protocol selectivity SQL builders.

Owns the batch field maps + the ``_batch_clause`` dispatcher (text /
numeric / date sub-types) and the ``_selectivity_clause`` ratio filter.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import aliased
from sqlalchemy.sql import ColumnElement

from cellar.infrastructure.persistence.sqlalchemy._sql import escape_like
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration._activity_query import (
    reportable_curve_value,
    to_micromolar,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration._field_clauses import (
    numeric_comparison,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
    ProtocolModel,
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
        value = criterion.get("value")
        if not value:
            msg = "batch text criterion needs a value"
            raise ValueError(msg)

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
        cond = numeric_comparison(BATCH_NUMERIC_FIELDS[field_name], criterion, "batch")
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

    Finds molecules where ``counter_potency / target_potency`` meets the
    specified ratio threshold.  A high ratio means the compound is much more
    potent at the target than the counter-screen.

    Each side names a DR readout-def — a readout-def is the column ("Target
    IC50", "Counter IC50", "Cytotoxicity LD50"). Protocol and curve_type are
    implied by it; sorting/joining by ``(protocol, curve_type)`` was
    ambiguous on multi-DR protocols (two DRs sharing a curve_type were
    indistinguishable).

    Both potencies are normalized to µM through their own protocol's
    ``dose_unit`` before dividing — a target in nM against a counter-screen
    in µM is otherwise off by 1000×. Inactive curves report ND (no potency),
    so they never form a ratio.

    Example criterion::

        {
            "type": "selectivity",
            "target_readout_definition_id": "<uuid>",
            "counter_readout_definition_id": "<uuid>",
            "ratio_operator": "gte",
            "ratio_value": 100,
        }
    """
    target_rd = criterion["target_readout_definition_id"]
    counter_rd = criterion["counter_readout_definition_id"]
    ratio_op = criterion.get("ratio_operator", "gte")
    if ratio_op == "between":
        msg = "Unknown selectivity ratio operator: between"
        raise ValueError(msg)
    if criterion.get("ratio_value") is None:
        msg = "selectivity criterion needs a ratio_value"
        raise ValueError(msg)

    t = aliased(DoseResponseCurveModel, name="target_drc")
    c = aliased(DoseResponseCurveModel, name="counter_drc")
    tp = aliased(ProtocolModel, name="target_protocol")
    cp = aliased(ProtocolModel, name="counter_protocol")
    mol = aliased(MoleculeModel, name="selectivity_molecule")

    def potency_um(curve: Any, protocol: Any) -> ColumnElement:
        return to_micromolar(
            reportable_curve_value(curve.fitted_value, curve.curve_class),
            dose_unit=protocol.dose_unit,
            molecular_weight=mol.molecular_weight,
        )

    ratio_expr = potency_um(c, cp) / sa.func.nullif(potency_um(t, tp), 0)
    ratio_cond = numeric_comparison(
        ratio_expr,
        {"operator": ratio_op, "value": criterion["ratio_value"]},
        "selectivity ratio",
    )

    return MoleculeModel.id.in_(
        sa.select(t.molecule_id)
        .join(c, t.molecule_id == c.molecule_id)
        .join(tp, t.protocol_id == tp.id)
        .join(cp, c.protocol_id == cp.id)
        .join(mol, t.molecule_id == mol.id)
        .where(
            t.workspace_id == workspace_id,
            t.readout_definition_id == target_rd,
            c.workspace_id == workspace_id,
            c.readout_definition_id == counter_rd,
            ratio_cond,
        )
    )
