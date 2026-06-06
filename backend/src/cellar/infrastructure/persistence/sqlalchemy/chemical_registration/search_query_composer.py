"""SearchQueryComposer -- translates query dicts into SQLAlchemy WHERE clauses.

Used by ExecuteSearch to compose dynamic compound queries from saved search
criteria (text, property, structure, activity, etc.).

This module is the public dispatcher: ``compose_criteria`` is the entry point,
and ``_group_clause`` recursively composes nested boolean groups. Per-criterion
clause builders live in sibling private modules and are re-exported here to
preserve their long-standing import paths:

- :mod:`._field_clauses` — text, property, collection, project, keyword_list,
  run_date, custom_field, plus the field-name maps.
- :mod:`._structure_query` — exact, substructure, similarity (cartridge SQL).
- :mod:`._activity_query` — activity filters with run-scope handling.
- :mod:`._batch_query` — batch-level fields and cross-protocol selectivity.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.sql import ColumnElement

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration._activity_query import (
    _activity_clause,
    _activity_presence_clause,
    _activity_where_clause,
    _normalize_where,
    _run_scope_filter,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration._batch_query import (
    BATCH_NUMERIC_FIELDS,
    BATCH_TEXT_FIELDS,
    _batch_clause,
    _selectivity_clause,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration._field_clauses import (
    PROPERTY_FIELDS,
    TEXT_FIELDS,
    _collection_clause,
    _custom_field_clause,
    _keyword_list_clause,
    _project_clause,
    _property_clause,
    _run_date_clause,
    _tag_clause,
    _text_clause,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration._structure_query import (
    _compute_query_bytes,
    _default_registry,
    _parse_metric,
    _resolve_algorithm_and_metric,
    _scaffold_clause,
    _similarity_clause,
    _structure_clause,
    _substructure_clause,
)

__all__ = [
    "BATCH_NUMERIC_FIELDS",
    "BATCH_TEXT_FIELDS",
    "PROPERTY_FIELDS",
    # Field maps (used by tests and adjacent code)
    "TEXT_FIELDS",
    "_activity_clause",
    "_activity_presence_clause",
    "_activity_where_clause",
    "_batch_clause",
    "_collection_clause",
    # Private helpers re-exported for use by molecule_reader.py and tests
    "_compute_query_bytes",
    "_custom_field_clause",
    "_default_registry",
    "_group_clause",
    "_keyword_list_clause",
    "_normalize_where",
    "_parse_metric",
    "_project_clause",
    "_property_clause",
    "_resolve_algorithm_and_metric",
    "_run_date_clause",
    "_run_scope_filter",
    "_scaffold_clause",
    "_selectivity_clause",
    "_similarity_clause",
    "_structure_clause",
    "_substructure_clause",
    "_tag_clause",
    "_text_clause",
    # Public API
    "compose_criteria",
]


def compose_criteria(query: dict[str, Any], *, workspace_id: uuid.UUID) -> ColumnElement | None:
    """Translate a query dict into a SQLAlchemy WHERE clause.

    Returns ``None`` if no criteria are present.
    Raises ``ValueError`` for invalid field names or operators.

    Args:
        workspace_id: Passed to cross-table subqueries for tenant isolation.
    """
    criteria = query.get("criteria", [])
    if not criteria:
        return None

    clauses: list[ColumnElement] = []
    for criterion in criteria:
        ctype = criterion["type"]
        if ctype == "text":
            clause = _text_clause(criterion)
        elif ctype == "property":
            clause = _property_clause(criterion)
        elif ctype == "structure":
            clause = _structure_clause(criterion)
        elif ctype == "scaffold":
            clause = _scaffold_clause(criterion)
        elif ctype == "activity":
            clause = _activity_clause(criterion, workspace_id)
        elif ctype == "collection":
            clause = _collection_clause(criterion, workspace_id)
        elif ctype == "project":
            clause = _project_clause(criterion, workspace_id)
        elif ctype == "keyword_list":
            clause = _keyword_list_clause(criterion)
        elif ctype == "run_date":
            clause = _run_date_clause(criterion, workspace_id)
        elif ctype == "batch":
            clause = _batch_clause(criterion, workspace_id)
        elif ctype == "selectivity":
            clause = _selectivity_clause(criterion, workspace_id)
        elif ctype == "group":
            clause = _group_clause(criterion, workspace_id)
        elif ctype == "custom_field":
            clause = _custom_field_clause(criterion)
        elif ctype == "tag":
            clause = _tag_clause(criterion)
        else:
            msg = f"Unknown criterion type: {ctype}"
            raise ValueError(msg)

        if criterion.get("negate", False):
            clause = ~clause

        clauses.append(clause)

    if len(clauses) == 1:
        return clauses[0]

    logic = query.get("logic", "and")
    if logic == "or":
        return sa.or_(*clauses)
    return sa.and_(*clauses)


# ── Group (nested boolean) ─────────────────────────────────────────────────

_MAX_GROUP_DEPTH = 4


def _group_clause(
    criterion: dict[str, Any], workspace_id: uuid.UUID, *, _depth: int = 0
) -> ColumnElement:
    """Recursively compose a nested boolean group.

    Example criterion::

        {
            "type": "group",
            "logic": "or",
            "criteria": [
                {"type": "activity", "protocol_id": "...", ...},
                {"type": "activity", "protocol_id": "...", ...}
            ]
        }
    """
    if _depth >= _MAX_GROUP_DEPTH:
        msg = f"Nested groups exceed max depth of {_MAX_GROUP_DEPTH}"
        raise ValueError(msg)

    inner_criteria = criterion.get("criteria", [])
    if not inner_criteria:
        msg = "Group criterion must contain at least one sub-criterion"
        raise ValueError(msg)

    clauses: list[ColumnElement] = []
    for sub in inner_criteria:
        ctype = sub["type"]
        if ctype == "group":
            clause = _group_clause(sub, workspace_id, _depth=_depth + 1)
        elif ctype == "text":
            clause = _text_clause(sub)
        elif ctype == "property":
            clause = _property_clause(sub)
        elif ctype == "structure":
            clause = _structure_clause(sub)
        elif ctype == "scaffold":
            clause = _scaffold_clause(sub)
        elif ctype == "activity":
            clause = _activity_clause(sub, workspace_id)
        elif ctype == "collection":
            clause = _collection_clause(sub, workspace_id)
        elif ctype == "project":
            clause = _project_clause(sub, workspace_id)
        elif ctype == "keyword_list":
            clause = _keyword_list_clause(sub)
        elif ctype == "run_date":
            clause = _run_date_clause(sub, workspace_id)
        elif ctype == "batch":
            clause = _batch_clause(sub, workspace_id)
        elif ctype == "selectivity":
            clause = _selectivity_clause(sub, workspace_id)
        elif ctype == "custom_field":
            clause = _custom_field_clause(sub)
        elif ctype == "tag":
            clause = _tag_clause(sub)
        else:
            msg = f"Unknown criterion type in group: {ctype}"
            raise ValueError(msg)

        if sub.get("negate", False):
            clause = ~clause
        clauses.append(clause)

    if len(clauses) == 1:
        return clauses[0]

    logic = criterion.get("logic", "and")
    if logic == "or":
        return sa.or_(*clauses)
    return sa.and_(*clauses)
