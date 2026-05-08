"""SQLAlchemy implementation of ``MoleculeReader`` (CQRS read side).

Owns short-lived sessions; not bound to the use case's UoW. Tracking is
intentionally skipped — search results are projection-only.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.sar_analysis.search_modes import MODE_DEFAULTS, SearchMode
from chem_vault.domain.sar_analysis.similarity_metric import (
    SimilarityMetric,
    Tanimoto,
    Tversky,
    serialize_metric,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_mapping import (
    model_to_molecule,
)
from chem_vault.infrastructure.rdkit.fingerprints.registry import FingerprintRegistry
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import (
    _compute_query_bytes,
)

log = structlog.get_logger(__name__)

_SORT_FIELDS: dict[str, Any] = {
    "name": MoleculeModel.name,
    "registration_number": MoleculeModel.registration_number,
    "molecular_weight": MoleculeModel.molecular_weight,
    "logp": MoleculeModel.logp,
    "tpsa": MoleculeModel.tpsa,
    "hbd": MoleculeModel.hbd,
    "hba": MoleculeModel.hba,
    "created_at": MoleculeModel.created_at,
}


class SQLAlchemyMoleculeReader:
    """Read-side adapter for compound search queries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def search_substructure(
        self, workspace_id: uuid.UUID, smarts: str
    ) -> list[Molecule]:
        """Substructure search using RDKit cartridge ``mol @> mol_from_smarts``."""
        async with self._session_factory() as session:
            stmt = (
                select(MoleculeModel)
                .where(
                    MoleculeModel.workspace_id == workspace_id,
                    MoleculeModel.merged_into_id.is_(None),
                    MoleculeModel.smiles.is_not(None),
                    text("mol_from_smiles(smiles) @> qmol_from_smarts(:smarts)"),
                )
                .params(smarts=smarts)
            )
            result = await session.execute(stmt)
            return [model_to_molecule(m) for m in result.scalars()]

    async def search_similarity(
        self,
        workspace_id: uuid.UUID,
        smiles: str,
        *,
        mode: SearchMode = SearchMode.SIMILAR,
        threshold: float | None = None,
        algorithm: str | None = None,
        metric: SimilarityMetric | None = None,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> list[tuple[Molecule, float]]:
        """Similarity search with mode-driven defaults + algorithm/metric overrides."""
        defaults = MODE_DEFAULTS[mode]
        algorithm_name = algorithm or defaults.algorithm
        effective_metric = metric if metric is not None else defaults.metric
        effective_threshold = float(
            threshold if threshold is not None else defaults.threshold
        )
        if not (0.0 <= effective_threshold <= 1.0):
            raise ValueError(
                f"threshold must be in [0,1], got {effective_threshold}"
            )

        registry = FingerprintRegistry.default()
        algo = registry.get(algorithm_name)
        column = algo.column_name
        fn = algo.cartridge_query_fn
        radius_arg = ", 2" if fn == "featmorganbv_fp" else ""

        # For Morgan, pre-compute the query fingerprint in Python so the bytes
        # are in the same format as the stored morgan_bfp column (written by the
        # Python-side stereo-aware generator, not the cartridge). FCFP is
        # unaffected — both write (DB trigger) and read use the same cartridge fn.
        q_bytes = _compute_query_bytes(algorithm_name, smiles)

        async with self._session_factory() as session:
            if q_bytes is not None:
                # Morgan path: use bfp_from_binary_text with Python bytes.
                if isinstance(effective_metric, Tanimoto):
                    await session.execute(
                        text(f"SET rdkit.tanimoto_threshold = {effective_threshold}")
                    )
                    score_sql = (
                        f"tanimoto_sml({column}, bfp_from_binary_text(:q_bytes))"
                        " AS similarity"
                    )
                    where_sql = f"{column} % bfp_from_binary_text(:q_bytes)"
                elif isinstance(effective_metric, Tversky):
                    score_sql = (
                        f"tversky_sml({column}, bfp_from_binary_text(:q_bytes), "
                        f"{effective_metric.alpha}, {effective_metric.beta}) AS similarity"
                    )
                    where_sql = (
                        f"tversky_sml({column}, bfp_from_binary_text(:q_bytes), "
                        f"{effective_metric.alpha}, {effective_metric.beta})"
                        f" >= {effective_threshold}"
                    )
                else:
                    raise ValueError(f"Unknown metric: {effective_metric!r}")

                stmt = (
                    select(MoleculeModel, text(score_sql))
                    .where(
                        MoleculeModel.workspace_id == workspace_id,
                        MoleculeModel.merged_into_id.is_(None),
                        text(where_sql),
                    )
                    .params(q_bytes=q_bytes)
                    .order_by(text("similarity DESC"))
                )
            else:
                # FCFP path: cartridge function is format-compatible on both ends.
                if isinstance(effective_metric, Tanimoto):
                    await session.execute(
                        text(f"SET rdkit.tanimoto_threshold = {effective_threshold}")
                    )
                    score_sql = (
                        f"tanimoto_sml({column}, {fn}(mol_from_smiles(:q){radius_arg}))"
                        " AS similarity"
                    )
                    where_sql = f"{column} % {fn}(mol_from_smiles(:q){radius_arg})"
                elif isinstance(effective_metric, Tversky):
                    score_sql = (
                        f"tversky_sml({column}, {fn}(mol_from_smiles(:q){radius_arg}), "
                        f"{effective_metric.alpha}, {effective_metric.beta}) AS similarity"
                    )
                    where_sql = (
                        f"tversky_sml({column}, {fn}(mol_from_smiles(:q){radius_arg}), "
                        f"{effective_metric.alpha}, {effective_metric.beta})"
                        f" >= {effective_threshold}"
                    )
                else:
                    raise ValueError(f"Unknown metric: {effective_metric!r}")

                stmt = (
                    select(MoleculeModel, text(score_sql))
                    .where(
                        MoleculeModel.workspace_id == workspace_id,
                        MoleculeModel.merged_into_id.is_(None),
                        text(where_sql),
                    )
                    .params(q=smiles)
                    .order_by(text("similarity DESC"))
                )

            if cursor_id is not None:
                stmt = stmt.where(MoleculeModel.id > cursor_id)
            if limit is not None:
                stmt = stmt.limit(limit)

            start = time.perf_counter()
            result = await session.execute(stmt)
            rows = result.all()
            elapsed_ms = (time.perf_counter() - start) * 1000.0

            log.debug(
                "similarity_query",
                algorithm=algorithm_name,
                metric=serialize_metric(effective_metric),
                threshold=effective_threshold,
                results_returned=len(rows),
                elapsed_ms=round(elapsed_ms, 2),
            )

            return [
                (model_to_molecule(row[0]), float(row[1]))
                for row in rows
            ]

    async def search_by_query(
        self,
        workspace_id: uuid.UUID,
        query: dict[str, Any],
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
        project_ids: list[uuid.UUID] | None = None,
        sort_by: str | None = None,
        sort_dir: str | None = None,
    ) -> list[Molecule]:
        """Compound search using a structured query dict.

        Supports configurable sorting via ``sort_by`` / ``sort_dir``. Uses
        keyset pagination: cursor encodes ``(sort_value, id)`` when sorting
        by a field other than ``id``. Special sort
        ``drc:{protocol_id}:{curve_type}`` orders by the best (lowest)
        ``fitted_value`` from DoseResponseCurve for that protocol+type;
        compounds without data sort last (NULLS LAST).
        """
        async with self._session_factory() as session:
            await _set_similarity_threshold(session, query)
            stmt = _build_base_stmt(workspace_id, query, project_ids=project_ids)

            descending = sort_dir == "desc"
            drc_sort = _parse_drc_sort(sort_by)

            if drc_sort is not None:
                protocol_id, curve_type = drc_sort
                stmt = _apply_drc_sort(
                    stmt, workspace_id, protocol_id, curve_type, descending
                )
            else:
                sort_col = _SORT_FIELDS.get(sort_by) if sort_by else None
                if sort_col is not None:
                    if descending:
                        stmt = stmt.order_by(sort_col.desc().nulls_last(), MoleculeModel.id)
                    else:
                        stmt = stmt.order_by(sort_col.asc().nulls_last(), MoleculeModel.id)
                else:
                    stmt = stmt.order_by(MoleculeModel.id)

            if cursor_id is not None:
                stmt = stmt.where(MoleculeModel.id > cursor_id)
            if limit is not None:
                stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            return [model_to_molecule(m) for m in result.scalars()]

    async def count_by_query(
        self,
        workspace_id: uuid.UUID,
        query: dict[str, Any],
        *,
        project_ids: list[uuid.UUID] | None = None,
    ) -> int:
        """Total count of molecules matching the query (no pagination)."""
        async with self._session_factory() as session:
            await _set_similarity_threshold(session, query)
            base = _build_base_stmt(workspace_id, query, project_ids=project_ids)
            count_stmt = select(func.count()).select_from(base.subquery())
            result = await session.execute(count_stmt)
            return result.scalar_one()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_base_stmt(
    workspace_id: uuid.UUID,
    query: dict[str, Any],
    *,
    project_ids: list[uuid.UUID] | None = None,
):
    """Build the base SELECT/WHERE for search_by_query and count_by_query."""
    from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import (
        _project_clause,
        compose_criteria,
    )

    where_clause = compose_criteria(query, workspace_id=workspace_id)

    stmt = select(MoleculeModel).where(
        MoleculeModel.workspace_id == workspace_id,
        MoleculeModel.merged_into_id.is_(None),
    )

    has_structure = any(
        c.get("type") == "structure" for c in query.get("criteria", [])
    )
    if has_structure:
        stmt = stmt.where(MoleculeModel.smiles.is_not(None))

    if where_clause is not None:
        stmt = stmt.where(where_clause)

    if project_ids is not None:
        stmt = stmt.where(_project_clause({"project_ids": list(project_ids)}, workspace_id))

    return stmt


async def _set_similarity_threshold(session: AsyncSession, query: dict[str, Any]) -> None:
    """Set ``rdkit.tanimoto_threshold`` once, based on the first Tanimoto similarity
    clause encountered (recursively walks groups). No-op for Tversky-only clauses
    (those use function-form WHERE filters that don't consult the GUC).
    """
    threshold = _find_first_tanimoto_threshold(query.get("criteria", []))
    if threshold is None:
        return
    if not (0.0 <= threshold <= 1.0):
        raise ValueError(f"Tanimoto threshold must be in [0,1], got {threshold}")
    await session.execute(text(f"SET rdkit.tanimoto_threshold = {threshold}"))


def _find_first_tanimoto_threshold(criteria: list[dict[str, Any]]) -> float | None:
    """Walk criteria (and nested groups) and return the first Tanimoto similarity
    threshold encountered, or None if no Tanimoto similarity clause exists.

    Returns ``None`` for Tversky clauses (whether via explicit metric or via the
    fragment_in_target mode default).
    """
    for criterion in criteria:
        ctype = criterion.get("type")
        if ctype == "structure":
            kind = criterion.get("kind") or criterion.get("search_type")
            if kind != "similarity":
                continue

            # Explicit metric wins.
            metric_payload = criterion.get("metric")
            if metric_payload and metric_payload.get("kind") == "tversky":
                continue

            # If no explicit metric, mode determines metric type.
            if metric_payload is None:
                mode = criterion.get("mode")
                if mode == "fragment_in_target":
                    continue  # mode default is Tversky

            t = criterion.get("threshold")
            if t is None:
                mode = criterion.get("mode")
                if mode is not None:
                    from chem_vault.domain.sar_analysis.search_modes import (
                        MODE_DEFAULTS,
                        SearchMode,
                    )
                    t = MODE_DEFAULTS[SearchMode(mode)].threshold
                else:
                    continue
            return float(t)

        if ctype == "group":
            nested = _find_first_tanimoto_threshold(criterion.get("criteria", []))
            if nested is not None:
                return nested

    return None


def _parse_drc_sort(sort_by: str | None) -> tuple[uuid.UUID, str] | None:
    """Parse ``drc:{protocol_id}:{curve_type}`` into components."""
    if not sort_by or not sort_by.startswith("drc:"):
        return None
    parts = sort_by.split(":", 2)
    if len(parts) != 3:
        return None
    try:
        protocol_id = uuid.UUID(parts[1])
    except ValueError:
        return None
    curve_type = parts[2]
    if not curve_type:
        return None
    return protocol_id, curve_type


def _apply_drc_sort(
    stmt: sa.Select,
    workspace_id: uuid.UUID,
    protocol_id: uuid.UUID,
    curve_type: str,
    descending: bool,
) -> sa.Select:
    """LEFT JOIN a best-value subquery and order by it."""
    from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
        DoseResponseCurveModel,
    )

    best_value_sq = (
        select(
            DoseResponseCurveModel.molecule_id.label("molecule_id"),
            func.min(DoseResponseCurveModel.fitted_value).label("best_value"),
        )
        .where(
            DoseResponseCurveModel.workspace_id == workspace_id,
            DoseResponseCurveModel.protocol_id == protocol_id,
            DoseResponseCurveModel.curve_type == curve_type,
        )
        .group_by(DoseResponseCurveModel.molecule_id)
        .subquery("drc_best")
    )

    stmt = stmt.outerjoin(
        best_value_sq,
        MoleculeModel.id == best_value_sq.c.molecule_id,
    )

    best_col = best_value_sq.c.best_value
    if descending:
        stmt = stmt.order_by(best_col.desc().nulls_last(), MoleculeModel.id)
    else:
        stmt = stmt.order_by(best_col.asc().nulls_last(), MoleculeModel.id)

    return stmt
