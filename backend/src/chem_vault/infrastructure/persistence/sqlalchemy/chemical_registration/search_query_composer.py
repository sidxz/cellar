"""SearchQueryComposer -- translates query dicts into SQLAlchemy WHERE clauses.

Used by ExecuteSearch to compose dynamic compound queries from saved search
criteria (text, property, structure).
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.sql import ColumnElement

from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
    ReadoutDataModel,
    RunModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CollectionMoleculeModel,
    molecule_projects,
)

# Mappings of query field names -> SA column references
TEXT_FIELDS: dict[str, Any] = {
    "name": MoleculeModel.name,
    "registration_number": MoleculeModel.registration_number,
    "molecular_formula": MoleculeModel.molecular_formula,
    "inchi_key": MoleculeModel.inchi_key,
}

PROPERTY_FIELDS: dict[str, Any] = {
    "molecular_weight": MoleculeModel.molecular_weight,
    "logp": MoleculeModel.logp,
    "tpsa": MoleculeModel.tpsa,
    "hbd": MoleculeModel.hbd,
    "hba": MoleculeModel.hba,
    "rotatable_bonds": MoleculeModel.rotatable_bonds,
    "heavy_atom_count": MoleculeModel.heavy_atom_count,
    "aromatic_rings": MoleculeModel.aromatic_rings,
    "ring_count": MoleculeModel.ring_count,
    "ro5_violations": MoleculeModel.ro5_violations,
}


def compose_criteria(query: dict[str, Any]) -> ColumnElement | None:
    """Translate a query dict into a SQLAlchemy WHERE clause.

    Returns ``None`` if no criteria are present.
    Raises ``ValueError`` for invalid field names or operators.
    """
    criteria = query.get("criteria", [])
    if not criteria:
        return None

    clauses: list[ColumnElement] = []
    for criterion in criteria:
        ctype = criterion["type"]
        if ctype == "text":
            clauses.append(_text_clause(criterion))
        elif ctype == "property":
            clauses.append(_property_clause(criterion))
        elif ctype == "structure":
            clauses.append(_structure_clause(criterion))
        elif ctype == "activity":
            clauses.append(_activity_clause(criterion))
        elif ctype == "collection":
            clauses.append(_collection_clause(criterion))
        elif ctype == "project":
            clauses.append(_project_clause(criterion))
        elif ctype == "keyword_list":
            clauses.append(_keyword_list_clause(criterion))
        elif ctype == "run_date":
            clauses.append(_run_date_clause(criterion))
        elif ctype == "batch":
            clauses.append(_batch_clause(criterion))
        else:
            msg = f"Unknown criterion type: {ctype}"
            raise ValueError(msg)

    if len(clauses) == 1:
        return clauses[0]

    logic = query.get("logic", "and")
    if logic == "or":
        return sa.or_(*clauses)
    return sa.and_(*clauses)


def _escape_like(value: str) -> str:
    """Escape SQL LIKE metacharacters so they match literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _text_clause(criterion: dict[str, Any]) -> ColumnElement:
    field = criterion["field"]
    if field not in TEXT_FIELDS:
        msg = f"Unknown text field: {field}"
        raise ValueError(msg)

    column = TEXT_FIELDS[field]
    operator = criterion.get("operator", "contains")
    value = criterion["value"]

    if operator == "contains":
        return column.ilike(f"%{_escape_like(value)}%", escape="\\")
    elif operator == "equals":
        return column == value
    elif operator == "starts_with":
        return column.ilike(f"{_escape_like(value)}%", escape="\\")
    else:
        msg = f"Unknown text operator: {operator}"
        raise ValueError(msg)


def _property_clause(criterion: dict[str, Any]) -> ColumnElement:
    field = criterion["field"]
    if field not in PROPERTY_FIELDS:
        msg = f"Unknown property field: {field}"
        raise ValueError(msg)

    column = PROPERTY_FIELDS[field]
    operator = criterion.get("operator", "eq")
    value = criterion.get("value")

    if operator == "eq":
        return column == value
    elif operator == "lt":
        return column < value
    elif operator == "lte":
        return column <= value
    elif operator == "gt":
        return column > value
    elif operator == "gte":
        return column >= value
    elif operator == "between":
        return column.between(criterion["min"], criterion["max"])
    else:
        msg = f"Unknown property operator: {operator}"
        raise ValueError(msg)


def _structure_clause(criterion: dict[str, Any]) -> ColumnElement:
    search_type = criterion["search_type"]

    if search_type == "substructure":
        smarts = criterion["smarts"]
        return text("mol_from_smiles(smiles) @> mol_from_smarts(:smarts)").bindparams(
            sa.bindparam("smarts", value=smarts, type_=sa.String)
        )
    elif search_type == "similarity":
        smiles = criterion["smiles"]
        return text("morgan_bfp % morganbv_fp(mol_from_smiles(:sim_q))").bindparams(
            sa.bindparam("sim_q", value=smiles, type_=sa.String)
        )
    elif search_type == "exact":
        inchi_key = criterion["inchi_key"]
        return MoleculeModel.inchi_key == inchi_key
    else:
        msg = f"Unknown structure search_type: {search_type}"
        raise ValueError(msg)


def _activity_clause(criterion: dict[str, Any]) -> ColumnElement:
    """Filter molecules by biological activity values."""
    protocol_id = criterion["protocol_id"]
    operator = criterion.get("operator", "lt")
    value = criterion["value"]

    op_map = {
        "eq": "__eq__",
        "lt": "__lt__",
        "lte": "__le__",
        "gt": "__gt__",
        "gte": "__ge__",
    }
    op_name = op_map.get(operator)
    if not op_name:
        msg = f"Unknown activity operator: {operator}"
        raise ValueError(msg)

    # Dose-response curve filtering
    if "curve_type" in criterion:
        col = DoseResponseCurveModel.fitted_value
        return MoleculeModel.id.in_(
            sa.select(DoseResponseCurveModel.molecule_id).where(
                DoseResponseCurveModel.protocol_id == protocol_id,
                DoseResponseCurveModel.curve_type == criterion["curve_type"],
                getattr(col, op_name)(value),
            )
        )

    # Raw readout filtering
    readout_def_id = criterion["readout_definition_id"]
    col = ReadoutDataModel.value_numeric
    return MoleculeModel.id.in_(
        sa.select(ReadoutDataModel.molecule_id).where(
            ReadoutDataModel.readout_definition_id == readout_def_id,
            ReadoutDataModel.is_outlier == False,  # noqa: E712
            getattr(col, op_name)(value),
        )
    )


def _collection_clause(criterion: dict[str, Any]) -> ColumnElement:
    """Filter molecules to those in a specific collection."""
    collection_id = criterion["collection_id"]
    return MoleculeModel.id.in_(
        sa.select(CollectionMoleculeModel.molecule_id).where(
            CollectionMoleculeModel.collection_id == collection_id,
        )
    )


def _project_clause(criterion: dict[str, Any]) -> ColumnElement:
    """Filter molecules by project membership.

    - No project_ids selected: return unscoped molecules only.
    - project_ids provided: return unscoped + molecules in the specified projects.
    """
    project_ids = criterion.get("project_ids", [])
    if not project_ids:
        # No projects selected — return unscoped molecules only
        return ~MoleculeModel.id.in_(
            sa.select(molecule_projects.c.molecule_id)
        )
    # Return unscoped + molecules in the specified projects
    return sa.or_(
        ~MoleculeModel.id.in_(
            sa.select(molecule_projects.c.molecule_id)
        ),
        MoleculeModel.id.in_(
            sa.select(molecule_projects.c.molecule_id).where(
                molecule_projects.c.project_id.in_(project_ids)
            )
        ),
    )


def _keyword_list_clause(criterion: dict[str, Any]) -> ColumnElement:
    """Filter molecules by a list of identifiers."""
    values = criterion["values"]
    ref_type = criterion.get("ref_type", "registration_number")

    if not values:
        msg = "keyword_list values must not be empty"
        raise ValueError(msg)

    if ref_type == "uuid":
        return MoleculeModel.id.in_(values)
    elif ref_type == "registration_number":
        return MoleculeModel.registration_number.in_(values)
    elif ref_type == "inchi_key":
        return MoleculeModel.inchi_key.in_(values)
    elif ref_type == "name":
        return MoleculeModel.name.in_(values)
    else:
        msg = f"keyword_list ref_type '{ref_type}' requires pre-resolution to UUIDs"
        raise ValueError(msg)


def _run_date_clause(criterion: dict[str, Any]) -> ColumnElement:
    """Filter molecules to those with data in a date range."""
    from datetime import date

    date_from = criterion.get("date_from")
    date_to = criterion.get("date_to")

    conditions: list[ColumnElement] = []
    if date_from:
        conditions.append(RunModel.run_date >= date.fromisoformat(date_from))
    if date_to:
        conditions.append(RunModel.run_date <= date.fromisoformat(date_to))

    return MoleculeModel.id.in_(
        sa.select(ReadoutDataModel.molecule_id)
        .join(RunModel, ReadoutDataModel.run_id == RunModel.id)
        .where(*conditions)
    )


# ── Batch field maps ────────────────────────────────────────────────────────

BATCH_TEXT_FIELDS: dict[str, Any] = {
    "batch_number": BatchModel.batch_number,
    "source": BatchModel.source,
    "salt_form": BatchModel.salt_form,
    "vendor_catalog_number": BatchModel.vendor_catalog_number,
    "notebook_reference": BatchModel.notebook_reference,
}

BATCH_NUMERIC_FIELDS: dict[str, Any] = {
    "purity": BatchModel.purity,
    "amount_value": BatchModel.amount_value,
}


def _batch_clause(criterion: dict[str, Any]) -> ColumnElement:
    """Filter molecules by batch-level fields.

    Supported sub-types:
    - ``field_type: "text"`` — text match on batch_number, source, etc.
    - ``field_type: "numeric"`` — numeric comparison on purity, amount.
    - ``field_type: "date"`` — date range on synthesis_date.
    """
    from datetime import date

    field_type = criterion.get("field_type", "text")

    if field_type == "text":
        field_name = criterion["field"]
        if field_name not in BATCH_TEXT_FIELDS:
            msg = f"Unknown batch text field: {field_name}"
            raise ValueError(msg)

        column = BATCH_TEXT_FIELDS[field_name]
        operator = criterion.get("operator", "contains")
        value = criterion["value"]

        if operator == "contains":
            cond = column.ilike(f"%{_escape_like(value)}%", escape="\\")
        elif operator == "equals":
            cond = column == value
        elif operator == "starts_with":
            cond = column.ilike(f"{_escape_like(value)}%", escape="\\")
        else:
            msg = f"Unknown batch text operator: {operator}"
            raise ValueError(msg)

        return MoleculeModel.id.in_(
            sa.select(BatchModel.molecule_id).where(cond)
        )

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

        return MoleculeModel.id.in_(
            sa.select(BatchModel.molecule_id).where(cond)
        )

    elif field_type == "date":
        date_from = criterion.get("date_from")
        date_to = criterion.get("date_to")

        conditions: list[ColumnElement] = []
        if date_from:
            conditions.append(BatchModel.synthesis_date >= date.fromisoformat(date_from))
        if date_to:
            conditions.append(BatchModel.synthesis_date <= date.fromisoformat(date_to))

        if not conditions:
            msg = "batch date criterion requires at least date_from or date_to"
            raise ValueError(msg)

        return MoleculeModel.id.in_(
            sa.select(BatchModel.molecule_id).where(*conditions)
        )

    else:
        msg = f"Unknown batch field_type: {field_type}"
        raise ValueError(msg)
