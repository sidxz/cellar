"""SQLAlchemy repository for DoseResponseCurve entities.

DoseResponseCurve is not an AggregateRoot — standalone repo with manual CRUD.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select

from chem_vault.domain.screening_assay.curve_fitting import InterceptValue
from chem_vault.domain.screening_assay.dose_response_config import InterceptSpec
from chem_vault.domain.screening_assay.dose_response_curve import DoseResponseCurve
from chem_vault.domain.screening_assay.enums import (
    CurveClass,
    CurveType,
    InterceptBasis,
    InterceptKind,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def _serialize_intercept_values(
    values: list[InterceptValue],
) -> list[dict] | None:
    """Serialize a list of InterceptValue VOs to JSONB-friendly dicts.

    Returns ``None`` when empty so the column stays NULL on legacy curves
    that haven't been refit since the multi-intercept feature shipped.
    """
    if not values:
        return None
    return [
        {
            "spec": {
                "kind": v.spec.kind.value,
                "level": v.spec.level,
                "basis": v.spec.basis.value,
                "label": v.spec.label,
            },
            "value": v.value,
            "ci_low": v.confidence_interval_low,
            "ci_high": v.confidence_interval_high,
            "at_bound": v.at_bound,
        }
        for v in values
    ]


def _hydrate_intercept_values(
    raw: list[dict] | None,
    *,
    fallback_curve_type: CurveType,
    fallback_value: float,
    fallback_ci_low: float | None,
    fallback_ci_high: float | None,
) -> list[InterceptValue]:
    """Hydrate the JSONB list. When NULL, synthesize a single-element list
    from the legacy ``(curve_type, fitted_value, ci_low, ci_high)`` so old
    curves render as one-intercept curves without a data backfill."""
    if raw is None:
        kind = (
            InterceptKind.IC
            if fallback_curve_type == CurveType.IC50
            else InterceptKind.EC
        )
        return [
            InterceptValue(
                spec=InterceptSpec(
                    kind=kind, level=50.0, basis=InterceptBasis.RELATIVE_PERCENT
                ),
                value=fallback_value,
                confidence_interval_low=fallback_ci_low,
                confidence_interval_high=fallback_ci_high,
                at_bound=False,
            )
        ]
    return [
        InterceptValue(
            spec=InterceptSpec(
                kind=InterceptKind(d["spec"]["kind"]),
                level=float(d["spec"]["level"]),
                basis=InterceptBasis(d["spec"]["basis"]),
                label=d["spec"].get("label"),
            ),
            value=float(d["value"]),
            confidence_interval_low=d.get("ci_low"),
            confidence_interval_high=d.get("ci_high"),
            at_bound=bool(d.get("at_bound", False)),
        )
        for d in raw
    ]


class SQLAlchemyDoseResponseCurveRepository:
    """Persists DoseResponseCurve entities to PostgreSQL."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def _find_by_id_unscoped(self, id: uuid.UUID) -> DoseResponseCurve | None:
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
        model.fit_quality_warnings = entity.fit_quality_warnings
        model.intercept_values = _serialize_intercept_values(entity.intercept_values)

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
        curve_type = CurveType(model.curve_type)
        return DoseResponseCurve(
            id=model.id,
            workspace_id=model.workspace_id,
            molecule_id=model.molecule_id,
            batch_id=model.batch_id,
            protocol_id=model.protocol_id,
            run_id=model.run_id,
            curve_type=curve_type,
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
            fit_quality_warnings=model.fit_quality_warnings or [],
            intercept_values=_hydrate_intercept_values(
                model.intercept_values,
                fallback_curve_type=curve_type,
                fallback_value=model.fitted_value,
                fallback_ci_low=model.confidence_interval_low,
                fallback_ci_high=model.confidence_interval_high,
            ),
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
            fit_quality_warnings=entity.fit_quality_warnings,
            intercept_values=_serialize_intercept_values(entity.intercept_values),
        )
