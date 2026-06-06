"""Simple per-field WHERE clause builders for molecule search.

Covers the criterion types whose SQL is a single column predicate or a
direct molecule-id IN-subquery: text, property, collection, project,
keyword_list, run_date, and custom_field. Also exports the shared
field-name -> SA column mappings.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.sql import ColumnElement

from cellar.infrastructure.persistence.sqlalchemy._sql import escape_like
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CollectionModel,
    CollectionMoleculeModel,
    ProjectModel,
    molecule_projects,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ReadoutDataModel,
    RunModel,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import (
    MoleculeTagLinkModel,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_filter import (
    tag_filter_subquery,
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


def _text_clause(criterion: dict[str, Any]) -> ColumnElement:
    field = criterion["field"]
    if field not in TEXT_FIELDS:
        msg = f"Unknown text field: {field}"
        raise ValueError(msg)

    column = TEXT_FIELDS[field]
    operator = criterion.get("operator", "contains")
    value = criterion["value"]

    if operator == "contains":
        return column.ilike(f"%{escape_like(value)}%", escape="\\")
    elif operator == "equals":
        return column == value
    elif operator == "starts_with":
        return column.ilike(f"{escape_like(value)}%", escape="\\")
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


def _collection_clause(criterion: dict[str, Any], workspace_id: uuid.UUID) -> ColumnElement:
    """Filter molecules to those in a specific collection, scoped to workspace."""
    collection_id = criterion["collection_id"]
    return MoleculeModel.id.in_(
        sa.select(CollectionMoleculeModel.molecule_id)
        .join(CollectionModel, CollectionMoleculeModel.collection_id == CollectionModel.id)
        .where(
            CollectionMoleculeModel.collection_id == collection_id,
            CollectionModel.workspace_id == workspace_id,
        )
    )


def _tag_clause(criterion: dict[str, Any]) -> ColumnElement:
    """Filter molecules to those carrying the given tag ids (any/all).

    Workspace scoping is already enforced by the outer molecule query (and a
    molecule can only link to tags in its own workspace), so no extra join.
    """
    raw_ids = criterion["tag_ids"]
    if not raw_ids:
        msg = "tag criterion requires at least one tag_id"
        raise ValueError(msg)
    tag_ids = [uuid.UUID(str(t)) for t in raw_ids]
    match_all = criterion.get("tag_logic", "any") == "all"
    return MoleculeModel.id.in_(
        tag_filter_subquery(MoleculeTagLinkModel, "molecule_id", tag_ids, match_all=match_all)
    )


def _project_clause(criterion: dict[str, Any], workspace_id: uuid.UUID) -> ColumnElement:
    """Filter molecules by project membership, scoped to workspace.

    - No project_ids selected: return unscoped molecules only.
    - project_ids provided: return unscoped + molecules in the specified projects.

    Defense-in-depth: project_ids are validated against the workspace via a
    join to the projects table.
    """
    project_ids = criterion.get("project_ids", [])
    # Subquery: valid project IDs in this workspace
    ws_project_ids = sa.select(ProjectModel.id).where(
        ProjectModel.workspace_id == workspace_id,
    )
    # Molecules that belong to any project within this workspace
    molecules_in_ws_projects = sa.select(molecule_projects.c.molecule_id).where(
        molecule_projects.c.project_id.in_(ws_project_ids),
    )
    if not project_ids:
        # No projects selected — return unscoped molecules only
        return ~MoleculeModel.id.in_(molecules_in_ws_projects)
    # Return unscoped + molecules in the specified projects (validated against workspace)
    return sa.or_(
        ~MoleculeModel.id.in_(molecules_in_ws_projects),
        MoleculeModel.id.in_(
            sa.select(molecule_projects.c.molecule_id).where(
                molecule_projects.c.project_id.in_(project_ids),
                molecule_projects.c.project_id.in_(ws_project_ids),
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


def _run_date_clause(criterion: dict[str, Any], workspace_id: uuid.UUID) -> ColumnElement:
    """Filter molecules to those with data in a date range."""
    from datetime import date

    date_from = criterion.get("date_from")
    date_to = criterion.get("date_to")

    conditions: list[ColumnElement] = [
        ReadoutDataModel.workspace_id == workspace_id,
        RunModel.workspace_id == workspace_id,
    ]
    if date_from:
        conditions.append(RunModel.run_date >= date.fromisoformat(date_from))
    if date_to:
        conditions.append(RunModel.run_date <= date.fromisoformat(date_to))

    return MoleculeModel.id.in_(
        sa.select(ReadoutDataModel.molecule_id)
        .join(RunModel, ReadoutDataModel.run_id == RunModel.id)
        .where(*conditions)
    )


def _custom_field_clause(criterion: dict[str, Any]) -> ColumnElement:
    """Filter molecules by custom_fields JSONB values.

    Supports text and numeric modes::

        {"type": "custom_field", "field": "solubility", "mode": "numeric",
         "operator": "gt", "value": 0.5}

        {"type": "custom_field", "field": "project_code", "mode": "text",
         "operator": "contains", "value": "ABC"}
    """
    field_name = criterion["field"]
    mode = criterion.get("mode", "text")

    # Extract the JSONB field as text: custom_fields->>'field_name'
    json_val = MoleculeModel.custom_fields[field_name].as_string()

    if mode == "text":
        operator = criterion.get("operator", "contains")
        value = criterion["value"]

        if operator == "contains":
            return json_val.ilike(f"%{escape_like(value)}%", escape="\\")
        elif operator == "equals":
            return json_val == value
        elif operator == "starts_with":
            return json_val.ilike(f"{escape_like(value)}%", escape="\\")
        else:
            msg = f"Unknown custom_field text operator: {operator}"
            raise ValueError(msg)

    elif mode == "numeric":
        operator = criterion.get("operator", "eq")
        value = criterion.get("value")

        # Cast JSONB text to numeric for comparison
        numeric_val = sa.cast(json_val, sa.Numeric)

        op_map = {
            "eq": "__eq__",
            "lt": "__lt__",
            "lte": "__le__",
            "gt": "__gt__",
            "gte": "__ge__",
        }

        if operator == "between":
            return numeric_val.between(criterion["min"], criterion["max"])

        op_name = op_map.get(operator)
        if not op_name:
            msg = f"Unknown custom_field numeric operator: {operator}"
            raise ValueError(msg)
        return getattr(numeric_val, op_name)(value)

    else:
        msg = f"Unknown custom_field mode: {mode}"
        raise ValueError(msg)
