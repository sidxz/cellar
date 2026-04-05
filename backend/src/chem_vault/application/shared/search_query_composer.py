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
        else:
            msg = f"Unknown criterion type: {ctype}"
            raise ValueError(msg)

    if len(clauses) == 1:
        return clauses[0]

    logic = query.get("logic", "and")
    if logic == "or":
        return sa.or_(*clauses)
    return sa.and_(*clauses)


def _text_clause(criterion: dict[str, Any]) -> ColumnElement:
    field = criterion["field"]
    if field not in TEXT_FIELDS:
        msg = f"Unknown text field: {field}"
        raise ValueError(msg)

    column = TEXT_FIELDS[field]
    operator = criterion.get("operator", "contains")
    value = criterion["value"]

    if operator == "contains":
        return column.ilike(f"%{value}%")
    elif operator == "equals":
        return column == value
    elif operator == "starts_with":
        return column.ilike(f"{value}%")
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
