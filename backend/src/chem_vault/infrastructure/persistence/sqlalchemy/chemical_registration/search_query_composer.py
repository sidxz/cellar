"""SearchQueryComposer -- translates query dicts into SQLAlchemy WHERE clauses.

Used by ExecuteSearch to compose dynamic compound queries from saved search
criteria (text, property, structure).
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.sql import ColumnElement

from chem_vault.domain.sar_analysis.search_modes import MODE_DEFAULTS, SearchMode
from chem_vault.domain.sar_analysis.similarity_metric import Tanimoto, Tversky
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from chem_vault.infrastructure.rdkit.fingerprints.registry import FingerprintRegistry
from chem_vault.infrastructure.rdkit.fingerprints.morgan import MorganAlgorithm
from chem_vault.infrastructure.rdkit.query_normalizer import aromatize_substructure_query

# Module-level singleton; tests can monkey-patch _default_registry if needed.
_default_registry = FingerprintRegistry.default()
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
    ReadoutDataModel,
    RunModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CollectionModel,
    CollectionMoleculeModel,
    ProjectModel,
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


def compose_criteria(
    query: dict[str, Any], *, workspace_id: uuid.UUID
) -> ColumnElement | None:
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


def escape_like(value: str) -> str:
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


def _structure_clause(criterion: dict[str, Any]) -> ColumnElement:
    # Accept new "kind" discriminator or legacy "search_type" alias.
    kind = criterion.get("kind") or criterion.get("search_type")

    if kind == "exact":
        inchi_key = criterion["inchi_key"]
        return MoleculeModel.inchi_key == inchi_key

    if kind == "substructure":
        return _substructure_clause(criterion)

    if kind == "similarity":
        return _similarity_clause(criterion)

    msg = f"Unknown structure kind: {kind!r}"
    raise ValueError(msg)


def _substructure_clause(criterion: dict[str, Any]) -> ColumnElement:
    query_text = criterion.get("smiles_or_smarts") or criterion.get("smarts")
    if not query_text:
        raise ValueError("substructure requires smiles_or_smarts (or legacy smarts)")
    generalized = bool(criterion.get("generalized", False))
    query_kind = criterion.get("query_kind")  # "smiles" | "smarts" | None

    # Cartridge functions qmol_from_smarts/mol_from_smiles take cstring, but
    # SQLAlchemy bindparams infer Python str -> VARCHAR. Explicit SQL CAST
    # to cstring is the only path that works under all driver scenarios.
    # The generalized (xqmol) path is structurally a SMILES path — the
    # cartridge's mol_to_xqmol works on a `mol`, not a `qmol`. Treat
    # untagged criteria with generalized=True as if they were tagged
    # SMILES (preserves the pre-query_kind contract for saved searches).
    effective_kind = query_kind
    if effective_kind is None and generalized:
        effective_kind = "smiles"

    if effective_kind == "smiles":
        # Cartridge's mol_from_smiles handles aromaticity perception on
        # both sides, no Python-side normalization needed.
        bound_query = query_text
        if generalized:
            sql = (
                "mol_from_smiles(smiles) @>> "
                "mol_to_xqmol(mol_from_smiles(CAST(:q AS cstring)))"
            )
        else:
            sql = "mol_from_smiles(smiles) @> mol_from_smiles(CAST(:q AS cstring))"
    elif effective_kind == "smarts":
        # Trust the chemist's pattern literally. Atom lists, "any bond"
        # notation, and other SMARTS primitives would be silently
        # collapsed by an SMILES roundtrip.
        bound_query = query_text
        sql = "mol_from_smiles(smiles) @> qmol_from_smarts(CAST(:q AS cstring))"
    else:
        # Legacy untagged input (saved searches predating query_kind, or
        # third-party API callers) without generalized. Defensive
        # aromatization handles the dominant failure mode — Ketcher's
        # Kekulé SMARTS export [#6]1-[#6]=[#6]-[#6]=[#6]-[#6]=1 returning
        # zero hits against aromatic-perceived storage.
        bound_query = aromatize_substructure_query(query_text)
        sql = "mol_from_smiles(smiles) @> qmol_from_smarts(CAST(:q AS cstring))"
    return text(sql).bindparams(q=bound_query)


def _parse_metric(payload: dict[str, Any]) -> object:
    kind = payload.get("kind", "tanimoto")
    if kind == "tanimoto":
        return Tanimoto()
    if kind == "tversky":
        return Tversky(alpha=float(payload["alpha"]), beta=float(payload["beta"]))
    raise ValueError(f"Unknown metric kind: {kind!r}")


def _resolve_algorithm_and_metric(
    criterion: dict[str, Any],
) -> tuple[str, object, float]:
    """Resolve (algorithm_name, metric_obj, threshold) from a similarity criterion.

    Priority: explicit algorithm/metric/threshold override mode defaults.
    Mode shortcut resolves defaults; explicit fields always win.
    Legacy path (neither mode nor algorithm) falls back to morgan+tanimoto.
    """
    algorithm: str | None = criterion.get("algorithm")
    metric_payload: dict | None = criterion.get("metric")
    threshold: float | None = criterion.get("threshold")

    mode_value = criterion.get("mode")
    if mode_value is not None:
        mode = SearchMode(mode_value)
        defaults = MODE_DEFAULTS[mode]
        algorithm = algorithm or defaults.algorithm
        threshold = threshold if threshold is not None else defaults.threshold
        if metric_payload is None:
            metric = defaults.metric
        else:
            metric = _parse_metric(metric_payload)
    elif algorithm is not None:
        # Explicit algorithm — metric and threshold are required.
        if metric_payload is None:
            raise ValueError("similarity without mode requires explicit metric")
        if threshold is None:
            raise ValueError("similarity without mode requires explicit threshold")
        metric = _parse_metric(metric_payload)
    else:
        # Legacy fallback: no mode, no algorithm — use morgan/tanimoto defaults.
        algorithm = "morgan"
        metric = Tanimoto()
        threshold = threshold if threshold is not None else 0.7

    if not (0.0 <= float(threshold) <= 1.0):
        raise ValueError(f"threshold must be in [0,1], got {threshold}")

    return algorithm, metric, float(threshold)


def _compute_query_bytes(algorithm_name: str, smiles: str) -> bytes | None:
    """Compute Python-side fingerprint bytes for ``algorithm_name`` from ``smiles``.

    Returns bytes for ``"morgan"`` (the only algorithm whose stored column was
    written by Python, not the cartridge, so both sides must use the same format).
    Returns ``None`` for ``"fcfp"`` — the cartridge trigger uses
    ``featmorganbv_fp`` on both write and read sides, so bytes are compatible.

    Raises ``ValueError`` if ``smiles`` cannot be parsed.
    """
    if algorithm_name != "morgan":
        return None
    from rdkit.Chem import MolFromSmiles  # local import to keep module fast to import

    mol = MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Cannot parse SMILES for similarity query: {smiles!r}")
    return MorganAlgorithm().compute_bytes(mol)


def _similarity_clause(criterion: dict[str, Any]) -> ColumnElement:
    smiles = criterion["smiles"]
    algorithm_name, metric, threshold = _resolve_algorithm_and_metric(criterion)
    algo = _default_registry.get(algorithm_name)
    column = algo.column_name
    fn = algo.cartridge_query_fn
    radius_arg = ", 2" if fn == "featmorganbv_fp" else ""

    q_bytes = _compute_query_bytes(algorithm_name, smiles)

    if q_bytes is not None:
        # Morgan: Python-computed bytes must be passed via bfp_from_binary_text
        # so the query vector is in the same format as the stored morgan_bfp column.
        if isinstance(metric, Tanimoto):
            sql = f"{column} % bfp_from_binary_text(:sim_q_bytes)"
        elif isinstance(metric, Tversky):
            sql = (
                f"tversky_sml({column}, bfp_from_binary_text(:sim_q_bytes), "
                f"{metric.alpha}, {metric.beta}) >= {threshold}"
            )
        else:
            raise ValueError(f"Unknown metric: {metric!r}")
        return text(sql).bindparams(
            sa.bindparam("sim_q_bytes", value=q_bytes, type_=sa.LargeBinary)
        )
    else:
        # FCFP: cartridge function is consistent on both sides. mol_from_smiles
        # takes cstring; CAST(:sim_q AS cstring) handles the type coercion that
        # would otherwise fail under SQLAlchemy's String->VARCHAR inference.
        if isinstance(metric, Tanimoto):
            sql = (
                f"{column} % {fn}(mol_from_smiles(CAST(:sim_q AS cstring))"
                f"{radius_arg})"
            )
        elif isinstance(metric, Tversky):
            sql = (
                f"tversky_sml({column}, "
                f"{fn}(mol_from_smiles(CAST(:sim_q AS cstring)){radius_arg}), "
                f"{metric.alpha}, {metric.beta}) >= {threshold}"
            )
        else:
            raise ValueError(f"Unknown metric: {metric!r}")
        return text(sql).bindparams(sim_q=smiles)


_ACTIVITY_OP_MAP: dict[str, str] = {
    "eq": "__eq__",
    "lt": "__lt__",
    "lte": "__le__",
    "gt": "__gt__",
    "gte": "__ge__",
    # "between" is handled separately (uses min+max instead of value).
}


def _activity_clause(
    criterion: dict[str, Any], workspace_id: uuid.UUID
) -> ColumnElement:
    """Filter molecules by biological activity values.

    Shapes accepted:
        - **Multi-where:** ``where: [{curve_type|readout_definition_id, operator,
          value or min/max}, ...]`` — each condition becomes a subquery, all
          ANDed together. Empty list ⇒ presence-only filter.
        - **Legacy single-where:** inline ``curve_type|readout_definition_id``
          plus ``operator`` and ``value`` (or ``min``/``max`` for ``between``).
          Treated as a single-element where list.
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
        _activity_where_clause(cond, protocol_id, workspace_id, run_scope)
        for cond in where_list
    ]
    if len(clauses) == 1:
        return clauses[0]
    return sa.and_(*clauses)


def _normalize_where(criterion: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a list of where-conditions, normalizing the legacy single-where shape."""
    where = criterion.get("where")
    if isinstance(where, list):
        return [c for c in where if isinstance(c, dict)]
    has_curve = bool(criterion.get("curve_type"))
    has_readout = bool(criterion.get("readout_definition_id"))
    if not has_curve and not has_readout:
        return []
    legacy: dict[str, Any] = {
        "operator": criterion.get("operator", "lt"),
    }
    if has_curve:
        legacy["curve_type"] = criterion["curve_type"]
    if has_readout:
        legacy["readout_definition_id"] = criterion["readout_definition_id"]
    if "value" in criterion:
        legacy["value"] = criterion["value"]
    if "min" in criterion:
        legacy["min"] = criterion["min"]
    if "max" in criterion:
        legacy["max"] = criterion["max"]
    return [legacy]


def _activity_where_clause(
    cond: dict[str, Any],
    protocol_id: Any,
    workspace_id: uuid.UUID,
    run_scope: Any,
) -> ColumnElement:
    """Compose a single where-condition into a molecule-id subquery."""
    has_curve = bool(cond.get("curve_type"))
    has_readout = bool(cond.get("readout_definition_id"))
    if not has_curve and not has_readout:
        msg = "where condition needs curve_type or readout_definition_id"
        raise ValueError(msg)

    if has_curve:
        data_col = DoseResponseCurveModel.fitted_value
        molecule_col = DoseResponseCurveModel.molecule_id
        run_id_col = DoseResponseCurveModel.run_id
        base_filters: list[ColumnElement] = [
            DoseResponseCurveModel.workspace_id == workspace_id,
            DoseResponseCurveModel.protocol_id == protocol_id,
            DoseResponseCurveModel.curve_type == cond["curve_type"],
        ]
    else:
        data_col = ReadoutDataModel.value_numeric
        molecule_col = ReadoutDataModel.molecule_id
        run_id_col = ReadoutDataModel.run_id
        base_filters = [
            ReadoutDataModel.workspace_id == workspace_id,
            ReadoutDataModel.readout_definition_id == cond["readout_definition_id"],
            ReadoutDataModel.is_outlier == False,  # noqa: E712
        ]

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
        positive = MoleculeModel.id.in_(
            sa.select(molecule_col).where(*base_filters, value_filter)
        )
        no_violation = ~MoleculeModel.id.in_(
            sa.select(molecule_col).where(*base_filters, ~value_filter)
        )
        return sa.and_(positive, no_violation)

    return MoleculeModel.id.in_(
        sa.select(molecule_col).where(*base_filters, value_filter)
    )


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


def _run_date_clause(
    criterion: dict[str, Any], workspace_id: uuid.UUID
) -> ColumnElement:
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


def _batch_clause(
    criterion: dict[str, Any], workspace_id: uuid.UUID
) -> ColumnElement:
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

        return MoleculeModel.id.in_(
            sa.select(BatchModel.molecule_id).where(*ws_filter, cond)
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
            sa.select(BatchModel.molecule_id).where(*ws_filter, cond)
        )

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

        return MoleculeModel.id.in_(
            sa.select(BatchModel.molecule_id).where(*conditions)
        )

    else:
        msg = f"Unknown batch field_type: {field_type}"
        raise ValueError(msg)


def _selectivity_clause(
    criterion: dict[str, Any], workspace_id: uuid.UUID
) -> ColumnElement:
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


# ── Custom field search (JSONB) ────────────────────────────────────────────


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
