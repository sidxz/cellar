"""SQLAlchemy implementation of ``MoleculeReader`` (CQRS read side).

Owns short-lived sessions; not bound to the use case's UoW. Tracking is
intentionally skipped — search results are projection-only.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_mapping import (
    model_to_molecule,
)


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
                    text("mol_from_smiles(smiles) @> mol_from_smarts(:smarts)"),
                )
                .params(smarts=smarts)
            )
            result = await session.execute(stmt)
            return [model_to_molecule(m) for m in result.scalars()]

    async def search_similarity(
        self, workspace_id: uuid.UUID, smiles: str, threshold: float = 0.7
    ) -> list[tuple[Molecule, float]]:
        """Similarity search using pre-computed ``morgan_bfp`` with GiST index."""
        safe_threshold = float(threshold)
        if not (0.0 <= safe_threshold <= 1.0):
            raise ValueError(
                f"Tanimoto threshold must be between 0 and 1, got {safe_threshold}"
            )

        async with self._session_factory() as session:
            await session.execute(
                text(f"SET rdkit.tanimoto_threshold = {safe_threshold}")
            )
            stmt = (
                select(
                    MoleculeModel,
                    text(
                        "tanimoto_sml(morgan_bfp, morganbv_fp(mol_from_smiles(:q))) AS similarity"
                    ),
                )
                .where(
                    MoleculeModel.workspace_id == workspace_id,
                    MoleculeModel.merged_into_id.is_(None),
                    text("morgan_bfp % morganbv_fp(mol_from_smiles(:q))"),
                )
                .params(q=smiles)
                .order_by(text("similarity DESC"))
                .limit(100)
            )
            result = await session.execute(stmt)
            return [
                (model_to_molecule(row[0]), float(row[1]))
                for row in result.all()
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
    for criterion in query.get("criteria", []):
        if (
            criterion.get("type") == "structure"
            and criterion.get("search_type") == "similarity"
        ):
            safe_threshold = float(criterion.get("threshold", 0.7))
            if not (0.0 <= safe_threshold <= 1.0):
                raise ValueError(
                    f"Tanimoto threshold must be between 0 and 1, got {safe_threshold}"
                )
            await session.execute(
                text(f"SET rdkit.tanimoto_threshold = {safe_threshold}")
            )
            break


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
