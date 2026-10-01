"""Simple per-field WHERE clause builders for molecule search.

Covers the criterion types whose SQL is a single column predicate or a
direct molecule-id IN-subquery: text, property, collection, project,
keyword_list, run_date, and custom_field. Also exports the shared
field-name -> SA column mappings.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from operator import eq, ge, gt, le, lt
from typing import Any

import sqlalchemy as sa
from sqlalchemy.sql import ColumnElement

from cellar.infrastructure.persistence.sqlalchemy._sql import escape_like
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeIdentifierModel,
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


def _text_match(column: Any, operator: str, value: str, what: str = "text") -> ColumnElement:
    if operator == "contains":
        return column.ilike(f"%{escape_like(value)}%", escape="\\")
    if operator == "equals":
        return column == value
    if operator == "starts_with":
        return column.ilike(f"{escape_like(value)}%", escape="\\")
    msg = f"Unknown {what} operator: {operator}"
    raise ValueError(msg)


def _text_clause(
    criterion: dict[str, Any], workspace_id: uuid.UUID | None = None
) -> ColumnElement:
    """Text match on one molecule field, or ``field: "any"`` = every text field
    plus the molecule's external identifiers (vendor / legacy / CDD ids), so a
    chemist can paste whatever id they have without knowing where it lives."""
    field = criterion["field"]
    operator = criterion.get("operator", "contains")
    value = criterion["value"]

    if field == "any":
        id_filters = [_text_match(MoleculeIdentifierModel.identifier, operator, value)]
        if workspace_id is not None:
            id_filters.append(MoleculeIdentifierModel.workspace_id == workspace_id)
        return sa.or_(
            *(_text_match(col, operator, value) for col in TEXT_FIELDS.values()),
            MoleculeModel.id.in_(
                sa.select(MoleculeIdentifierModel.molecule_id).where(*id_filters)
            ),
        )

    if field not in TEXT_FIELDS:
        msg = f"Unknown text field: {field}"
        raise ValueError(msg)
    return _text_match(TEXT_FIELDS[field], operator, value)


_COMPARISONS: dict[str, Callable[[Any, Any], ColumnElement]] = {
    "eq": eq,
    "lt": lt,
    "lte": le,
    "gt": gt,
    "gte": ge,
}


def numeric_comparison(column: Any, criterion: dict[str, Any], what: str) -> ColumnElement:
    """Apply a criterion's ``operator`` + ``value`` (or ``min``/``max``) to ``column``.

    ``between`` with only one bound is open-ended (a "max MW 500" row is the
    most common med-chem filter). A missing value raises ``ValueError`` (→ 422)
    instead of reaching SQLAlchemy, which rejects ``col >= None`` with a 500.
    """
    op = criterion.get("operator", "eq")
    if op == "between":
        lo, hi = criterion.get("min"), criterion.get("max")
        if lo is None and hi is None:
            msg = f"{what}: 'between' needs a min and/or max"
            raise ValueError(msg)
        if lo is None:
            return column <= hi
        if hi is None:
            return column >= lo
        return column.between(lo, hi)
    compare = _COMPARISONS.get(op)
    if compare is None:
        msg = f"Unknown {what} operator: {op}"
        raise ValueError(msg)
    value = criterion.get("value")
    if value is None:
        msg = f"{what}: operator {op!r} needs a value"
        raise ValueError(msg)
    return compare(column, value)


def _property_clause(criterion: dict[str, Any]) -> ColumnElement:
    field = criterion["field"]
    if field not in PROPERTY_FIELDS:
        msg = f"Unknown property field: {field}"
        raise ValueError(msg)
    return numeric_comparison(PROPERTY_FIELDS[field], criterion, "property")


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
    """Filter molecules by a pasted list of identifiers.

    Registration numbers and InChIKeys are upper-case by construction, names
    match case-insensitively — pasted lists rarely preserve case. External IDs
    and SMILES are resolved to ``uuid`` by the application layer first
    (``resolve_search_references``); an empty resolved list matches nothing.
    """
    values = criterion["values"]
    ref_type = criterion.get("ref_type", "registration_number")

    if ref_type == "uuid":
        return MoleculeModel.id.in_(values) if values else sa.false()
    if not values:
        msg = "keyword_list values must not be empty"
        raise ValueError(msg)
    if ref_type == "registration_number":
        return MoleculeModel.registration_number.in_([v.upper() for v in values])
    if ref_type == "inchi_key":
        return MoleculeModel.inchi_key.in_([v.upper() for v in values])
    if ref_type == "name":
        return sa.func.lower(MoleculeModel.name).in_([v.lower() for v in values])
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


_NUMBER_PATTERN = r"^\s*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*$"


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
        return _text_match(
            json_val,
            criterion.get("operator", "contains"),
            criterion["value"],
            "custom_field text",
        )
    if mode == "numeric":
        # Free-form JSON: one molecule storing "n/a" under the field must not
        # abort the whole search with a CAST error — non-numbers become NULL.
        numeric_val = sa.case(
            (json_val.regexp_match(_NUMBER_PATTERN), sa.cast(json_val, sa.Numeric)),
            else_=None,
        )
        return numeric_comparison(numeric_val, criterion, "custom_field")
    msg = f"Unknown custom_field mode: {mode}"
    raise ValueError(msg)
