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

from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.research_organization.criteria_walker import find_first
from cellar.domain.sar_analysis.search_modes import MODE_DEFAULTS, SearchMode
from cellar.domain.sar_analysis.similarity_metric import (
    SimilarityMetric,
    Tanimoto,
    Tversky,
    serialize_metric,
)
from cellar.infrastructure.persistence.sqlalchemy._sql import any_id
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_mapping import (
    model_to_molecule,
)
from cellar.infrastructure.rdkit.fingerprints.registry import FingerprintRegistry
from cellar.infrastructure.rdkit.query_normalizer import aromatize_substructure_query

from .search_query_composer import (
    _compute_query_bytes,
)

log = structlog.get_logger(__name__)

_SORT_FIELDS: dict[str, Any] = {
    "name": MoleculeModel.name,
    "registration_number": MoleculeModel.registration_number,
    "created_at": MoleculeModel.created_at,
    "lifecycle_stage": MoleculeModel.lifecycle_stage,
    "molecular_formula": MoleculeModel.molecular_formula,
    "molecular_weight": MoleculeModel.molecular_weight,
    "exact_mass": MoleculeModel.exact_mass,
    "logp": MoleculeModel.logp,
    "tpsa": MoleculeModel.tpsa,
    "hbd": MoleculeModel.hbd,
    "hba": MoleculeModel.hba,
    "rotatable_bonds": MoleculeModel.rotatable_bonds,
    "aromatic_rings": MoleculeModel.aromatic_rings,
    "ring_count": MoleculeModel.ring_count,
    "heavy_atom_count": MoleculeModel.heavy_atom_count,
    "ro5_violations": MoleculeModel.ro5_violations,
    "logd": MoleculeModel.logd,
    "pka": MoleculeModel.pka,
    "logs": MoleculeModel.logs,
}
SQL_SORT_FIELDS = frozenset(_SORT_FIELDS) | {"similarity"}


class SQLAlchemyMoleculeReader:
    """Read-side adapter for compound search queries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def search_substructure(
        self,
        workspace_id: uuid.UUID,
        query: str,
        *,
        kind: str | None = None,
    ) -> list[Molecule]:
        """Substructure search via the RDKit cartridge.

        ``kind`` selects the cartridge function:
          - ``"smiles"`` → ``mol_from_smiles`` on the query side; cartridge
            handles aromaticity perception on both sides.
          - ``"smarts"`` → ``qmol_from_smarts`` with the query passed
            through literally (chemist may have used "any bond" / atom
            lists / other SMARTS primitives whose semantics would be lost
            by an SMILES roundtrip).
          - ``None`` (legacy) → SMARTS path with defensive aromatization
            so Ketcher's Kekulé exports still match aromatic storage.
        """
        async with self._session_factory() as session:
            if kind == "smiles":
                stmt = (
                    select(MoleculeModel)
                    .where(
                        MoleculeModel.workspace_id == workspace_id,
                        MoleculeModel.merged_into_id.is_(None),
                        MoleculeModel.smiles.is_not(None),
                        text("mol_from_smiles(smiles) @> mol_from_smiles(:q)"),
                    )
                    .params(q=query)
                )
            else:
                bound_query = query if kind == "smarts" else aromatize_substructure_query(query)
                stmt = (
                    select(MoleculeModel)
                    .where(
                        MoleculeModel.workspace_id == workspace_id,
                        MoleculeModel.merged_into_id.is_(None),
                        MoleculeModel.smiles.is_not(None),
                        text("mol_from_smiles(smiles) @> qmol_from_smarts(:q)"),
                    )
                    .params(q=bound_query)
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
        effective_threshold = float(threshold if threshold is not None else defaults.threshold)
        if not (0.0 <= effective_threshold <= 1.0):
            raise ValueError(f"threshold must be in [0,1], got {effective_threshold}")

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
                        f"tanimoto_sml({column}, bfp_from_binary_text(:q_bytes)) AS similarity"
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

            return [(model_to_molecule(row[0]), float(row[1])) for row in rows]

    async def search_by_query(
        self,
        workspace_id: uuid.UUID,
        query: dict[str, Any],
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
        project_ids: list[uuid.UUID] | None = None,
    ) -> list[Molecule]:
        """One page of matches in id order, after ``cursor_id``.

        Sorted and similarity-ranked result sets page through
        :meth:`ranked_ids_by_query` instead.
        """
        async with self._session_factory() as session:
            await _set_similarity_threshold(session, query)
            stmt = _build_base_stmt(workspace_id, query, project_ids=project_ids).order_by(
                MoleculeModel.id
            )
            if cursor_id is not None:
                stmt = stmt.where(MoleculeModel.id > cursor_id)
            if limit is not None:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [model_to_molecule(m) for m in result.scalars()]

    async def ranked_ids_by_query(
        self,
        workspace_id: uuid.UUID,
        query: dict[str, Any],
        *,
        project_ids: list[uuid.UUID] | None = None,
        sort_by: str | None = None,
        sort_dir: str | None = None,
    ) -> list[tuple[uuid.UUID, float | None]]:
        """Every matching id in result order, with its similarity score.

        ``sort_by`` is a molecule column (``_SORT_FIELDS``) or ``similarity``;
        None orders by similarity (most similar first) when the query has a
        similarity criterion, else by id. Nulls sort last; ties break on id.
        Ids only — callers page through the list and fetch the page's rows.
        """
        if sort_by is not None and sort_by not in SQL_SORT_FIELDS:
            raise ValueError(f"Unknown sort field: {sort_by!r}")
        sim = _find_first_similarity_criterion(query.get("criteria", []))
        if sort_by == "similarity" and sim is None:
            raise ValueError("sort by similarity needs a similarity criterion")
        async with self._session_factory() as session:
            await _set_similarity_threshold(session, query)
            if sim is not None:
                stmt = _build_base_stmt_with_score(
                    workspace_id, query, sim, project_ids=project_ids, columns=(MoleculeModel.id,)
                )
                score = text("similarity")
            else:
                stmt = _build_base_stmt(
                    workspace_id, query, project_ids=project_ids, columns=(MoleculeModel.id,)
                )
                score = None
            descending = sort_dir == "desc"
            if sort_by in _SORT_FIELDS:
                col = _SORT_FIELDS[sort_by]
                stmt = stmt.order_by(
                    col.desc().nulls_last() if descending else col.asc().nulls_last(),
                    MoleculeModel.id,
                )
            elif score is not None and (sort_by == "similarity" or sort_by is None):
                most_similar_first = sort_by is None or sort_dir != "asc"
                stmt = stmt.order_by(
                    text("similarity DESC" if most_similar_first else "similarity ASC"),
                    MoleculeModel.id,
                )
            else:
                stmt = stmt.order_by(MoleculeModel.id)
            rows = (await session.execute(stmt)).all()
        if score is None:
            return [(row[0], None) for row in rows]
        return [(row[0], float(row[1])) for row in rows]

    async def find_by_ids_ordered(
        self, workspace_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> list[Molecule]:
        """The molecules in ``ids`` order; ids not in the workspace are dropped."""
        if not ids:
            return []
        async with self._session_factory() as session:
            result = await session.execute(
                select(MoleculeModel).where(
                    MoleculeModel.workspace_id == workspace_id, any_id(MoleculeModel.id, ids)
                )
            )
            by_id = {m.id: model_to_molecule(m) for m in result.scalars()}
        return [by_id[i] for i in ids if i in by_id]

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
    columns: tuple[Any, ...] = (MoleculeModel,),
):
    """Build the base SELECT/WHERE for search_by_query and count_by_query."""
    from .search_query_composer import (
        _project_clause,
        compose_criteria,
    )

    where_clause = compose_criteria(query, workspace_id=workspace_id)

    stmt = select(*columns).where(
        MoleculeModel.workspace_id == workspace_id,
        MoleculeModel.merged_into_id.is_(None),
    )

    has_structure = any(c.get("type") == "structure" for c in query.get("criteria", []))
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


def _is_tanimoto_similarity(criterion: dict[str, Any]) -> bool:
    """Predicate: leaf is a similarity structure clause using the Tanimoto metric."""
    if criterion.get("type") != "structure":
        return False
    kind = criterion.get("kind") or criterion.get("search_type")
    if kind != "similarity":
        return False
    metric_payload = criterion.get("metric")
    if metric_payload and metric_payload.get("kind") == "tversky":
        return False
    # mode default is Tversky, so an absent metric in fragment_in_target mode is not Tanimoto
    return not (metric_payload is None and criterion.get("mode") == "fragment_in_target")


def _find_first_tanimoto_threshold(criteria: list[dict[str, Any]]) -> float | None:
    """First Tanimoto-similarity threshold in the tree, or None.

    Returns ``None`` for Tversky clauses (whether via explicit metric or via
    the ``fragment_in_target`` mode default).
    """
    hit = find_first(criteria, _is_tanimoto_similarity)
    if hit is None:
        return None
    t = hit.get("threshold")
    if t is None:
        mode = hit.get("mode")
        if mode is None:
            return None
        t = MODE_DEFAULTS[SearchMode(mode)].threshold
    return float(t)


def _find_first_similarity_criterion(
    criteria: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """First similarity-structure criterion in the tree, or None."""
    return find_first(
        criteria,
        lambda c: (
            c.get("type") == "structure"
            and (c.get("kind") or c.get("search_type")) == "similarity"
        ),
    )


def _build_score_clause(criterion: dict[str, Any]):
    """Build a ``text()`` score expression (aliased ``similarity``) for a similarity criterion.

    Returns a SQLAlchemy ``text()`` element with bound params already attached,
    ready to be added to a ``select()`` projection.  Mirrors the logic in
    ``search_similarity`` / ``_similarity_clause`` so the score column always
    matches what the WHERE clause computes.
    """
    from .search_query_composer import (
        _resolve_algorithm_and_metric,
    )

    smiles = criterion["smiles"]
    algorithm_name, metric, _threshold = _resolve_algorithm_and_metric(criterion)

    registry = FingerprintRegistry.default()
    algo = registry.get(algorithm_name)
    column = algo.column_name
    fn = algo.cartridge_query_fn
    radius_arg = ", 2" if fn == "featmorganbv_fp" else ""

    q_bytes = _compute_query_bytes(algorithm_name, smiles)

    if q_bytes is not None:
        # Morgan path: Python-computed bytes, same format as the stored column.
        if isinstance(metric, Tanimoto):
            score_sql = (
                f"tanimoto_sml({column}, bfp_from_binary_text(:sim_score_bytes)) AS similarity"
            )
        elif isinstance(metric, Tversky):
            score_sql = (
                f"tversky_sml({column}, bfp_from_binary_text(:sim_score_bytes), "
                f"{metric.alpha}, {metric.beta}) AS similarity"
            )
        else:
            raise ValueError(f"Unknown metric: {metric!r}")
        return text(score_sql).bindparams(
            sa.bindparam("sim_score_bytes", value=q_bytes, type_=sa.LargeBinary)
        )
    else:
        # FCFP path: cartridge function handles both write and read side.
        if isinstance(metric, Tanimoto):
            score_sql = (
                f"tanimoto_sml({column}, "
                f"{fn}(mol_from_smiles(CAST(:sim_score_q AS cstring)){radius_arg}))"
                " AS similarity"
            )
        elif isinstance(metric, Tversky):
            score_sql = (
                f"tversky_sml({column}, "
                f"{fn}(mol_from_smiles(CAST(:sim_score_q AS cstring)){radius_arg}), "
                f"{metric.alpha}, {metric.beta}) AS similarity"
            )
        else:
            raise ValueError(f"Unknown metric: {metric!r}")
        return text(score_sql).bindparams(sim_score_q=smiles)


def _build_base_stmt_with_score(
    workspace_id: uuid.UUID,
    query: dict[str, Any],
    sim_criterion: dict[str, Any],
    *,
    project_ids: list[uuid.UUID] | None = None,
    columns: tuple[Any, ...] = (MoleculeModel,),
):
    """Like ``_build_base_stmt`` but adds a similarity score projection column."""
    from .search_query_composer import (
        _project_clause,
        compose_criteria,
    )

    score_clause = _build_score_clause(sim_criterion)
    where_clause = compose_criteria(query, workspace_id=workspace_id)

    stmt = select(*columns, score_clause).where(
        MoleculeModel.workspace_id == workspace_id,
        MoleculeModel.merged_into_id.is_(None),
    )

    # Similarity queries always need a non-null smiles
    stmt = stmt.where(MoleculeModel.smiles.is_not(None))

    if where_clause is not None:
        stmt = stmt.where(where_clause)

    if project_ids is not None:
        stmt = stmt.where(_project_clause({"project_ids": list(project_ids)}, workspace_id))

    return stmt
