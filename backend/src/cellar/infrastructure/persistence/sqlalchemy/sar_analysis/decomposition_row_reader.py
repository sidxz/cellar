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

    async def fetch_rows(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        offset: int,
        limit: int,
        sort: list[DecompositionRowSort],
        projection_id: UUID | None = None,
    ) -> list[DecompositionRow]:
        # Activity is a LEFT JOIN to the projection's sparse values; absent ⇒
        # null (uncolored / unsortable for that row), exactly like the client did.
        activity_col = SarActivityValueModel.scalar if projection_id is not None else null()

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
            ),
            run_id,
            workspace_id,
        )
        if projection_id is not None:
            stmt = stmt.outerjoin(
                SarActivityValueModel,
                (SarActivityValueModel.projection_id == projection_id)
                & (SarActivityValueModel.molecule_id == RGroupAssignmentModel.molecule_id),
            )

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
            )
            for row in result.all()
        ]

    async def count_rows(self, run_id: UUID, *, workspace_id: UUID) -> int:
        stmt = self._scoped_join(
            select(func.count()).select_from(RGroupAssignmentModel), run_id, workspace_id
        )
        return int((await self._uow.session.execute(stmt)).scalar_one())
