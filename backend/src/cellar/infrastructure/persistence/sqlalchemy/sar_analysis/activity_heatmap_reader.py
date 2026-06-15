"""SQLAlchemy read-model for the activity heatmap.

GROUP BY (rgroups->>axis_y, rgroups->>axis_x) over assignment ⋈ activity_value ⋈
molecules, argmin(scalar) per cell. ``argmin`` is the *lower-is-better* cell
representative — correct because the FE only colors/expands dose-response potency
channels (concentrations, where lower = more potent). Each axis is capped to the
top-K substituents by member count; totals are reported separately so the UI can
label "top K of N" honestly. Molecules missing either axis substituent are not
placeable in a 2D cell and are excluded.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import distinct, func, select

from cellar.application.sar_analysis.activity_heatmap import (
    HEATMAP_AXIS_TOP_K,
    HeatmapCell,
    HeatmapResult,
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


class SQLAlchemyActivityHeatmapReader:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def fetch_heatmap(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        projection_id: UUID,
        axis_y: str,
        axis_x: str,
        top_k: int = HEATMAP_AXIS_TOP_K,
    ) -> HeatmapResult:
        session = self._uow.session
        y_expr = RGroupAssignmentModel.rgroups[axis_y].as_string()
        x_expr = RGroupAssignmentModel.rgroups[axis_x].as_string()
        label_expr = func.coalesce(MoleculeModel.registration_number, MoleculeModel.name)

        base = (
            select(
                RGroupAssignmentModel.molecule_id.label("molecule_id"),
                y_expr.label("y"),
                x_expr.label("x"),
                SarActivityValueModel.scalar.label("scalar"),
                label_expr.label("label"),
                SarActivityValueModel.snapshot.label("snapshot"),
            )
            .join(
                RGroupDecompositionRunModel,
                RGroupDecompositionRunModel.id == RGroupAssignmentModel.run_id,
            )
            .join(
                SarActivityValueModel,
                (SarActivityValueModel.projection_id == projection_id)
                & (SarActivityValueModel.molecule_id == RGroupAssignmentModel.molecule_id),
            )
            .join(MoleculeModel, MoleculeModel.id == RGroupAssignmentModel.molecule_id)
            .where(
                RGroupAssignmentModel.run_id == run_id,
                RGroupDecompositionRunModel.workspace_id == workspace_id,
                MoleculeModel.workspace_id == workspace_id,
                MoleculeModel.merged_into_id.is_(None),
                y_expr.isnot(None),
                x_expr.isnot(None),
            )
            .cte("base")
        )

        # Honest totals (distinct substituents per axis, before the cap).
        totals = (
            await session.execute(
                select(func.count(distinct(base.c.y)), func.count(distinct(base.c.x)))
            )
        ).one()
        y_total, x_total = int(totals[0]), int(totals[1])

        # Top-K substituents per axis by member count.
        # Materialize as .subquery() so the IN clause renders as a correlated
        # subquery rather than a bare CTE reference — avoids SQLAlchemy
        # binding errors when using CTE columns inside .in_().
        y_top_sub = (
            select(base.c.y.label("y"))
            .group_by(base.c.y)
            .order_by(func.count().desc(), base.c.y)
            .limit(top_k)
            .subquery("y_top")
        )
        x_top_sub = (
            select(base.c.x.label("x"))
            .group_by(base.c.x)
            .order_by(func.count().desc(), base.c.x)
            .limit(top_k)
            .subquery("x_top")
        )

        capped = (
            select(
                base.c.molecule_id,
                base.c.y,
                base.c.x,
                base.c.scalar,
                base.c.label,
                base.c.snapshot,
            )
            .where(
                base.c.y.in_(select(y_top_sub.c.y)),
                base.c.x.in_(select(x_top_sub.c.x)),
            )
            .cte("capped")
        )

        rn = func.row_number().over(
            partition_by=[capped.c.y, capped.c.x],
            order_by=[capped.c.scalar.asc(), capped.c.molecule_id],
        ).label("rn")
        cell_count = func.count().over(partition_by=[capped.c.y, capped.c.x]).label("cell_count")
        ranked = select(
            capped.c.molecule_id,
            capped.c.y,
            capped.c.x,
            capped.c.scalar,
            capped.c.label,
            capped.c.snapshot,
            rn,
            cell_count,
        ).cte("ranked")

        rows = (
            await session.execute(
                select(
                    ranked.c.y,
                    ranked.c.x,
                    ranked.c.cell_count,
                    ranked.c.scalar,
                    ranked.c.molecule_id,
                    ranked.c.label,
                    ranked.c.snapshot,
                ).where(ranked.c.rn == 1)
            )
        ).all()

        cells = [
            HeatmapCell(
                y=r.y,
                x=r.x,
                count=int(r.cell_count),
                best_scalar=float(r.scalar),
                best_molecule_id=r.molecule_id,
                best_molecule_label=r.label or "",
                best_snapshot=dict(r.snapshot or {}),
            )
            for r in rows
        ]
        y_values = sorted({c.y for c in cells})
        x_values = sorted({c.x for c in cells})
        return HeatmapResult(
            x_values=x_values,
            y_values=y_values,
            cells=cells,
            y_total=y_total,
            x_total=x_total,
            truncated=(y_total > top_k or x_total > top_k),
        )
