"""SQLAlchemy repository for DoseResponseCurve entities.

DoseResponseCurve is not an AggregateRoot — standalone repo with manual CRUD.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select

from chem_vault.domain.screening_assay.dose_response_curve import DoseResponseCurve
from chem_vault.domain.screening_assay.enums import CurveClass, CurveType
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyDoseResponseCurveRepository:
    """Persists DoseResponseCurve entities to PostgreSQL."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def find_by_id(self, id: uuid.UUID) -> DoseResponseCurve | None:
        model = await self._uow.session.get(DoseResponseCurveModel, id)
        return self._to_domain(model) if model else None

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> DoseResponseCurve | None:
        """Load by PK scoped to workspace."""
        stmt = (
            select(DoseResponseCurveModel)
            .where(
                DoseResponseCurveModel.id == id,
                DoseResponseCurveModel.workspace_id == workspace_id,
            )
        )
        result = await self._uow.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_run(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID
    ) -> list[DoseResponseCurve]:
        stmt = (
            select(DoseResponseCurveModel)
            .where(
                DoseResponseCurveModel.workspace_id == workspace_id,
                DoseResponseCurveModel.run_id == run_id,
            )
            .order_by(DoseResponseCurveModel.created_at)
        )
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_by_molecule(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[DoseResponseCurve]:
        """All dose-response curves for a molecule, ordered by r_squared desc."""
        stmt = (
            select(DoseResponseCurveModel)
            .where(
                DoseResponseCurveModel.workspace_id == workspace_id,
                DoseResponseCurveModel.molecule_id == molecule_id,
            )
            .order_by(DoseResponseCurveModel.r_squared.desc())
        )
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_best_curves_for_molecules(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        protocol_ids: list[uuid.UUID] | None = None,
    ) -> dict[uuid.UUID, dict[uuid.UUID, DoseResponseCurve]]:
        """Batch query: molecule_id -> protocol_id -> best curve (highest r_squared)."""
        if not molecule_ids:
            return {}

        # Subquery: best r_squared per (molecule_id, protocol_id)
        best_sq = (
            select(
                DoseResponseCurveModel.molecule_id,
                DoseResponseCurveModel.protocol_id,
                func.max(DoseResponseCurveModel.r_squared).label("best_r2"),
            )
            .where(
                DoseResponseCurveModel.workspace_id == workspace_id,
                DoseResponseCurveModel.molecule_id.in_(molecule_ids),
            )
            .group_by(
                DoseResponseCurveModel.molecule_id,
                DoseResponseCurveModel.protocol_id,
            )
        )

        if protocol_ids:
            best_sq = best_sq.where(DoseResponseCurveModel.protocol_id.in_(protocol_ids))

        best_sq = best_sq.subquery()

        stmt = (
            select(DoseResponseCurveModel)
            .join(
                best_sq,
                (DoseResponseCurveModel.molecule_id == best_sq.c.molecule_id)
                & (DoseResponseCurveModel.protocol_id == best_sq.c.protocol_id)
                & (DoseResponseCurveModel.r_squared == best_sq.c.best_r2),
            )
            .where(DoseResponseCurveModel.workspace_id == workspace_id)
        )

        result = await self._uow.session.execute(stmt)
        curves = [self._to_domain(m) for m in result.scalars().all()]

        out: dict[uuid.UUID, dict[uuid.UUID, DoseResponseCurve]] = {}
        for curve in curves:
            out.setdefault(curve.molecule_id, {})[curve.protocol_id] = curve

        return out

    async def save(self, entity: DoseResponseCurve) -> None:
        existing = await self._uow.session.get(DoseResponseCurveModel, entity.id)
        if existing is not None:
            if existing.workspace_id != entity.workspace_id:
                from chem_vault.domain.shared.errors import AuthorizationError
                raise AuthorizationError("Cannot update DoseResponseCurve from a different workspace")
            self._update_model(existing, entity)
        else:
            model = self._to_model(entity)
            self._uow.session.add(model)

    @staticmethod
    def _update_model(model: DoseResponseCurveModel, entity: DoseResponseCurve) -> None:
        model.molecule_id = entity.molecule_id
        model.batch_id = entity.batch_id
        model.protocol_id = entity.protocol_id
        model.run_id = entity.run_id
        model.curve_type = entity.curve_type.value
        model.fitted_value = entity.fitted_value
        model.hill_slope = entity.hill_slope
        model.top = entity.top
        model.bottom = entity.bottom
        model.r_squared = entity.r_squared
        model.confidence_interval_low = entity.confidence_interval_low
        model.confidence_interval_high = entity.confidence_interval_high
        model.num_points = entity.num_points
        model.curve_class = entity.curve_class.value if entity.curve_class else None
        model.raw_data = entity.raw_data
        model.excluded_points = entity.excluded_points

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = delete(DoseResponseCurveModel).where(
            DoseResponseCurveModel.workspace_id == workspace_id,
            DoseResponseCurveModel.id == id,
        )
        await self._uow.session.execute(stmt)

    async def delete_by_run(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> None:
        stmt = delete(DoseResponseCurveModel).where(
            DoseResponseCurveModel.workspace_id == workspace_id,
            DoseResponseCurveModel.run_id == run_id,
        )
        await self._uow.session.execute(stmt)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(model: DoseResponseCurveModel) -> DoseResponseCurve:
        return DoseResponseCurve(
            id=model.id,
            workspace_id=model.workspace_id,
            molecule_id=model.molecule_id,
            batch_id=model.batch_id,
            protocol_id=model.protocol_id,
            run_id=model.run_id,
            curve_type=CurveType(model.curve_type),
            fitted_value=model.fitted_value,
            hill_slope=model.hill_slope,
            top=model.top,
            bottom=model.bottom,
            r_squared=model.r_squared,
            confidence_interval_low=model.confidence_interval_low,
            confidence_interval_high=model.confidence_interval_high,
            num_points=model.num_points,
            curve_class=CurveClass(model.curve_class) if model.curve_class else None,
            raw_data=model.raw_data,
            excluded_points=model.excluded_points,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_model(entity: DoseResponseCurve) -> DoseResponseCurveModel:
        return DoseResponseCurveModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            molecule_id=entity.molecule_id,
            batch_id=entity.batch_id,
            protocol_id=entity.protocol_id,
            run_id=entity.run_id,
            curve_type=entity.curve_type.value,
            fitted_value=entity.fitted_value,
            hill_slope=entity.hill_slope,
            top=entity.top,
            bottom=entity.bottom,
            r_squared=entity.r_squared,
            confidence_interval_low=entity.confidence_interval_low,
            confidence_interval_high=entity.confidence_interval_high,
            num_points=entity.num_points,
            curve_class=entity.curve_class.value if entity.curve_class else None,
            raw_data=entity.raw_data,
            excluded_points=entity.excluded_points,
        )
