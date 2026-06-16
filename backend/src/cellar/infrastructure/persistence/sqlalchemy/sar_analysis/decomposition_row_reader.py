"""SQLAlchemy read-model for the decomposition ``/rows`` endpoint.

Joins assignment rows to molecules, scoped to the run's workspace and the
molecule reader's visibility (``merged_into_id IS NULL``). Sort accepts molecule
columns or an R-group label (``rgroups->>'Rn'``), always with a ``molecule_id``
tiebreaker for stable pagination.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import func, null, select

from cellar.application.sar_analysis.decomposition_rows import (
    DecompositionRow,
    DecompositionRowSort,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_models import (
    RGroupAssignmentModel,
    RGroupDecompositionRunModel,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_models import (  # noqa: E501
    SarActivityValueModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_MOLECULE_SORT_COLS: dict[str, Any] = {
    "registration_number": MoleculeModel.registration_number,
    "name": MoleculeModel.name,
    "molecular_weight": MoleculeModel.molecular_weight,
    "logp": MoleculeModel.logp,
    "tpsa": MoleculeModel.tpsa,
}
_RGROUP_LABEL = re.compile(r"^R\d+$")


def _sort_column(col: str):
    """Resolve a sort key to a column expression, or None if unrecognized."""
    if col in _MOLECULE_SORT_COLS:
        return _MOLECULE_SORT_COLS[col]
    if _RGROUP_LABEL.match(col):
        return RGroupAssignmentModel.rgroups[col].as_string()
    return None


_TEXT_FILTER_COLS: dict[str, Any] = {
    "registration_number": MoleculeModel.registration_number,
    "name": MoleculeModel.name,
}
_NUMERIC_FILTER_COLS: dict[str, Any] = {
    "molecular_weight": MoleculeModel.molecular_weight,
    "logp": MoleculeModel.logp,
    "tpsa": MoleculeModel.tpsa,
}


def _filter_column(col: str, *, projection_id: UUID | None):
    """Resolve a filter key to a column expression, or None if unknown / N/A."""
    if col in _NUMERIC_FILTER_COLS:
        return _NUMERIC_FILTER_COLS[col]
    if col in _TEXT_FILTER_COLS:
        return _TEXT_FILTER_COLS[col]
    if col == "activity":
        return SarActivityValueModel.scalar if projection_id is not None else None
    if _RGROUP_LABEL.match(col):
        return RGroupAssignmentModel.rgroups[col].as_string()
    return None


def _number_condition(column, op: str, value, value2):
    if op == "eq":
        return column == value
    if op == "neq":
        return column != value
    if op == "gt":
        return column > value
    if op == "gte":
        return column >= value
    if op == "lt":
        return column < value
    if op == "lte":
        return column <= value
    if op == "between" and value2 is not None:
        return column.between(value, value2)
    return None


def _text_condition(column, op: str, value: str):
    if op == "eq":
        return column == value
    if op == "neq":
        return column != value
    if op == "contains":
        return column.ilike(f"%{value}%")
    if op == "startsWith":
        return column.ilike(f"{value}%")
    if op == "endsWith":
        return column.ilike(f"%{value}")
    return None


def _apply_filter(stmt, filter: dict[str, Any] | None, *, projection_id: UUID | None):
    """Apply each recognized filter clause as a WHERE condition; skip unknowns
    (lenient, like the sort handling). Numeric clauses target physchem columns or
    the joined activity scalar; text clauses target reg#/name (ILIKE) or
    ``rgroups->>'Rn'``."""
    if not filter:
        return stmt
    for col, clause in filter.items():
        if not isinstance(clause, dict):
            continue
        column = _filter_column(col, projection_id=projection_id)
        if column is None:
            continue
        kind = clause.get("kind")
        op = clause.get("op")
        value = clause.get("value")
        if kind == "number" and isinstance(value, (int, float)):
            cond = _number_condition(column, op, value, clause.get("value2"))
        elif kind == "text" and isinstance(value, str):
            cond = _text_condition(column, op, value)
        else:
            cond = None
        if cond is not None:
            stmt = stmt.where(cond)
    return stmt


class SQLAlchemyDecompositionRowReader:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    def _scoped_join(self, stmt, run_id: UUID, workspace_id: UUID):
        return (
            stmt.join(
                RGroupDecompositionRunModel,
                RGroupDecompositionRunModel.id == RGroupAssignmentModel.run_id,
            )
            .join(MoleculeModel, MoleculeModel.id == RGroupAssignmentModel.molecule_id)
            .where(
                RGroupAssignmentModel.run_id == run_id,
                RGroupDecompositionRunModel.workspace_id == workspace_id,
                MoleculeModel.workspace_id == workspace_id,
                MoleculeModel.merged_into_id.is_(None),
            )
        )

    def _activity_join(self, stmt, projection_id: UUID | None):
        if projection_id is None:
            return stmt
        return stmt.outerjoin(
            SarActivityValueModel,
            (SarActivityValueModel.projection_id == projection_id)
            & (SarActivityValueModel.molecule_id == RGroupAssignmentModel.molecule_id),
        )

    async def fetch_rows(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        offset: int,
        limit: int,
        sort: list[DecompositionRowSort],
        projection_id: UUID | None = None,
        filter: dict[str, Any] | None = None,
    ) -> list[DecompositionRow]:
        # Activity is a LEFT JOIN to the projection's sparse values; absent ⇒
        # null (uncolored / unsortable for that row), exactly like the client did.
        # The snapshot rides alongside (the stored ActivityValue wire shape) so the
        # table's plot column + curve-expand work under pagination.
        activity_col = SarActivityValueModel.scalar if projection_id is not None else null()
        snapshot_col = SarActivityValueModel.snapshot if projection_id is not None else null()

        stmt = self._scoped_join(
            select(
                RGroupAssignmentModel.molecule_id,
                MoleculeModel.smiles,
                MoleculeModel.registration_number,
                MoleculeModel.name,
                RGroupAssignmentModel.rgroups,
                MoleculeModel.molecular_weight,
                MoleculeModel.logp,
                MoleculeModel.tpsa,
                activity_col.label("activity"),
                snapshot_col.label("activity_snapshot"),
            ),
            run_id,
            workspace_id,
        )
        stmt = self._activity_join(stmt, projection_id)
        stmt = _apply_filter(stmt, filter, projection_id=projection_id)

        order_by = []
        for spec in sort:
            if spec.col == "activity":
                col = SarActivityValueModel.scalar if projection_id is not None else None
            else:
                col = _sort_column(spec.col)
            if col is None:
                continue  # unknown / inapplicable sort key — ignored (lenient)
            ordered = col.desc() if spec.direction == "desc" else col.asc()
            order_by.append(ordered.nulls_last())
        order_by.append(RGroupAssignmentModel.molecule_id)  # stable tiebreaker

        stmt = stmt.order_by(*order_by).offset(offset).limit(limit)
        result = await self._uow.session.execute(stmt)
        return [
            DecompositionRow(
                molecule_id=row[0],
                smiles=row[1],
                registration_number=row[2],
                name=row[3],
                rgroups=dict(row[4]),
                molecular_weight=row[5],
                logp=row[6],
                tpsa=row[7],
                activity=row[8],
                activity_snapshot=dict(row[9]) if row[9] is not None else None,
            )
            for row in result.all()
        ]

    async def count_rows(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        projection_id: UUID | None = None,
        filter: dict[str, Any] | None = None,
    ) -> int:
        stmt = self._scoped_join(
            select(func.count()).select_from(RGroupAssignmentModel), run_id, workspace_id
        )
        stmt = self._activity_join(stmt, projection_id)
        stmt = _apply_filter(stmt, filter, projection_id=projection_id)
        return int((await self._uow.session.execute(stmt)).scalar_one())

    async def fetch_matched_ids(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        projection_id: UUID | None = None,
        filter: dict[str, Any] | None = None,
    ) -> list[UUID]:
        # Identical scoped/activity joins + filter as count_rows, but project the
        # molecule_id instead of counting — so the resolved set equals exactly the
        # filtered total the table shows. One row per molecule per run.
        stmt = self._scoped_join(select(RGroupAssignmentModel.molecule_id), run_id, workspace_id)
        stmt = self._activity_join(stmt, projection_id)
        stmt = _apply_filter(stmt, filter, projection_id=projection_id)
        result = await self._uow.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def activity_reference(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        projection_id: UUID | None,
        filter: dict[str, Any] | None = None,
    ) -> float | None:
        """The most-potent (min) activity scalar across the filtered matched set,
        anchoring the table's potency ramp consistently across pages. None when no
        projection or no values."""
        if projection_id is None:
            return None
        stmt = self._scoped_join(
            select(func.min(SarActivityValueModel.scalar)).select_from(RGroupAssignmentModel),
            run_id,
            workspace_id,
        )
        stmt = self._activity_join(stmt, projection_id)
        stmt = _apply_filter(stmt, filter, projection_id=projection_id)
        value = (await self._uow.session.execute(stmt)).scalar_one_or_none()
        return float(value) if value is not None else None
