"""SQLAlchemy repository for DoseResponseCurve entities.

DoseResponseCurve is not an AggregateRoot — standalone repo with manual CRUD.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select

from cellar.domain.screening_assay.curve_fitting import InterceptValue
from cellar.domain.screening_assay.dose_response_config import InterceptSpec
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import (
    CurveClass,
    CurveType,
    InterceptBasis,
    InterceptKind,
)
from cellar.domain.screening_assay.excluded_point_detail import ExcludedPointDetail
from cellar.domain.screening_assay.run_scope import RunScope
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
    ProtocolModel,
    RunModel,
    protocol_projects,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


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
        kind = InterceptKind.IC if fallback_curve_type == CurveType.IC50 else InterceptKind.EC
        return [
            InterceptValue(
                spec=InterceptSpec(kind=kind, level=50.0, basis=InterceptBasis.RELATIVE_PERCENT),
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


def _serialize_excluded_points(
    points: list[ExcludedPointDetail] | list[dict] | None,
) -> list[dict] | None:
    """Serialize the domain's excluded_points to JSONB.

    Accepts either typed ``ExcludedPointDetail`` instances or raw dicts.
    The raw-dict branch is temporary back-compat for legacy producers
    (notably ``curve_fitter.py``) that still emit dicts pre-Task 2.7;
    those callers will be refactored to typed VOs in a follow-up.
    """
    if not points:
        return None
    out: list[dict] = []
    for entry in points:
        if isinstance(entry, ExcludedPointDetail):
            out.append(entry.to_jsonb())
        else:
            # Legacy dict producer — pass through unchanged.
            out.append(entry)
    return out


def _hydrate_excluded_points(
    raw: list[dict] | None,
) -> list[ExcludedPointDetail] | None:
    """Hydrate JSONB excluded_points entries into typed ``ExcludedPointDetail``.

    Post-migration-041 the JSONB shape is uniform across legacy and Sprint-2
    entries (idx optional, audit metadata always present). If a malformed
    entry slips through, we tolerate it by skipping rather than failing the
    read — defensive against any pre-migration row that escaped backfill.
    """
    if not raw:
        return None
    out: list[ExcludedPointDetail] = []
    for entry in raw:
        try:
            out.append(ExcludedPointDetail.from_jsonb(entry))
        except (KeyError, ValueError, TypeError):
            # Should not occur on a migrated DB; if it does, dropping the
            # malformed entry is safer than crashing every query that
            # touches the curve.
            continue
    return out or None


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
        stmt = select(DoseResponseCurveModel).where(
            DoseResponseCurveModel.id == id,
            DoseResponseCurveModel.workspace_id == workspace_id,
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

    async def find_by_ids(
        self, workspace_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> list[DoseResponseCurve]:
        """Batch lookup by primary key, scoped to workspace."""
        if not ids:
            return []
        stmt = select(DoseResponseCurveModel).where(
            DoseResponseCurveModel.workspace_id == workspace_id,
            DoseResponseCurveModel.id.in_(ids),
        )
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def count_distinct_protocols_per_molecule(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        project_id: uuid.UUID | None = None,
    ) -> dict[uuid.UUID, int]:
        """Count distinct protocols each molecule has been tested in.

        A molecule is "tested in" a protocol when ≥1 DoseResponseCurve row
        exists for that molecule linked (via run) to the protocol.  When
        ``project_id`` is supplied, only protocols associated with that
        project via the ``protocol_projects`` join table are counted.

        Molecules not present in ``dose_response_curves`` are returned with
        count=0 so callers never need to handle missing keys.
        """
        if not molecule_ids:
            return {mol_id: 0 for mol_id in molecule_ids}

        stmt = (
            select(
                DoseResponseCurveModel.molecule_id,
                func.count(func.distinct(ProtocolModel.id)).label("protocol_count"),
            )
            .join(RunModel, RunModel.id == DoseResponseCurveModel.run_id)
            .join(ProtocolModel, ProtocolModel.id == RunModel.protocol_id)
            .where(
                DoseResponseCurveModel.workspace_id == workspace_id,
                DoseResponseCurveModel.molecule_id.in_(molecule_ids),
            )
        )

        if project_id is not None:
            stmt = stmt.join(
                protocol_projects,
                protocol_projects.c.protocol_id == ProtocolModel.id,
            ).where(protocol_projects.c.project_id == project_id)

        stmt = stmt.group_by(DoseResponseCurveModel.molecule_id)

        result = await self._uow.session.execute(stmt)
        rows = result.all()

        counts: dict[uuid.UUID, int] = {mol_id: 0 for mol_id in molecule_ids}
        for row in rows:
            counts[row.molecule_id] = row.protocol_count
        return counts

    async def find_best_curves_for_molecules(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        readout_definition_ids: list[uuid.UUID] | None = None,
    ) -> dict[uuid.UUID, dict[uuid.UUID, DoseResponseCurve]]:
        """Batch query: molecule_id -> readout_definition_id -> best curve (highest r_squared).

        Keyed by readout-def, not protocol — a protocol can declare N DR
        readouts (target IC50, counter-screen IC50, ...) so "best curve
        for this protocol" was ambiguous. "Best curve for this DR
        readout-def" is the precise question every caller actually wants.
        """
        if not molecule_ids:
            return {}

        # Subquery: best r_squared per (molecule_id, readout_definition_id)
        best_sq = (
            select(
                DoseResponseCurveModel.molecule_id,
                DoseResponseCurveModel.readout_definition_id,
                func.max(DoseResponseCurveModel.r_squared).label("best_r2"),
            )
            .where(
                DoseResponseCurveModel.workspace_id == workspace_id,
                DoseResponseCurveModel.molecule_id.in_(molecule_ids),
            )
            .group_by(
                DoseResponseCurveModel.molecule_id,
                DoseResponseCurveModel.readout_definition_id,
            )
        )

        if readout_definition_ids:
            best_sq = best_sq.where(
                DoseResponseCurveModel.readout_definition_id.in_(readout_definition_ids)
            )

        best_sq = best_sq.subquery()

        stmt = (
            select(DoseResponseCurveModel)
            .join(
                best_sq,
                (DoseResponseCurveModel.molecule_id == best_sq.c.molecule_id)
                & (DoseResponseCurveModel.readout_definition_id == best_sq.c.readout_definition_id)
                & (DoseResponseCurveModel.r_squared == best_sq.c.best_r2),
            )
            .where(DoseResponseCurveModel.workspace_id == workspace_id)
        )

        result = await self._uow.session.execute(stmt)
        curves = [self._to_domain(m) for m in result.scalars().all()]

        out: dict[uuid.UUID, dict[uuid.UUID, DoseResponseCurve]] = {}
        for curve in curves:
            out.setdefault(curve.molecule_id, {})[curve.readout_definition_id] = curve

        return out

    async def find_all_curves_for_molecules(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        readout_definition_ids: list[uuid.UUID] | None = None,
        run_scope: RunScope | None = None,
    ) -> dict[uuid.UUID, dict[uuid.UUID, list[DoseResponseCurve]]]:
        """Return ALL curves keyed by (mol, rd), sorted run_date desc.

        Joins to RunModel for run_date filtering. The shared aggregator
        decides which to keep (LATEST / GEOMETRIC_MEAN / etc.); this
        method only narrows the wire payload to in-scope runs.

        ``last_n`` is applied per-(mol, rd) AFTER grouping (not as a
        global SQL LIMIT) so a chemist asking "last 3 runs" gets the
        latest 3 PER COMPOUND, not the latest 3 globally.
        """
        if not molecule_ids:
            return {}

        stmt = (
            select(DoseResponseCurveModel)
            .join(RunModel, RunModel.id == DoseResponseCurveModel.run_id)
            .where(
                DoseResponseCurveModel.workspace_id == workspace_id,
                DoseResponseCurveModel.molecule_id.in_(molecule_ids),
            )
        )
        if readout_definition_ids:
            stmt = stmt.where(
                DoseResponseCurveModel.readout_definition_id.in_(readout_definition_ids)
            )

        if run_scope is not None and not run_scope.is_all():
            if run_scope.explicit_run_ids:
                stmt = stmt.where(RunModel.id.in_(run_scope.explicit_run_ids))
            if run_scope.since_date is not None:
                stmt = stmt.where(RunModel.run_date >= run_scope.since_date)
            if run_scope.from_date is not None and run_scope.to_date is not None:
                stmt = stmt.where(
                    RunModel.run_date.between(run_scope.from_date, run_scope.to_date)
                )

        stmt = stmt.order_by(RunModel.run_date.desc())

        result = await self._uow.session.execute(stmt)
        curves = [self._to_domain(m) for m in result.scalars().all()]

        out: dict[uuid.UUID, dict[uuid.UUID, list[DoseResponseCurve]]] = {}
        for curve in curves:
            out.setdefault(curve.molecule_id, {}).setdefault(
                curve.readout_definition_id, []
            ).append(curve)

        # last_n is per-(mol, rd), applied after grouping.
        if run_scope is not None and run_scope.last_n_count is not None:
            n = run_scope.last_n_count
            for mol_id in out:
                for rd_id in out[mol_id]:
                    out[mol_id][rd_id] = out[mol_id][rd_id][:n]

        return out

    async def save(self, entity: DoseResponseCurve) -> None:
        existing = await self._uow.session.get(DoseResponseCurveModel, entity.id)
        if existing is not None:
            if existing.workspace_id != entity.workspace_id:
                from cellar.domain.shared.errors import AuthorizationError

                raise AuthorizationError(
                    "Cannot update DoseResponseCurve from a different workspace"
                )
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
        model.readout_definition_id = entity.readout_definition_id
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
        model.excluded_points = _serialize_excluded_points(entity.excluded_points)
        model.fit_quality_warnings = entity.fit_quality_warnings
        model.intercept_values = _serialize_intercept_values(entity.intercept_values)
        model.dose_response_config_snapshot = entity.dose_response_config_snapshot

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
            readout_definition_id=model.readout_definition_id,
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
            excluded_points=_hydrate_excluded_points(model.excluded_points),
            fit_quality_warnings=model.fit_quality_warnings or [],
            intercept_values=_hydrate_intercept_values(
                model.intercept_values,
                fallback_curve_type=curve_type,
                fallback_value=model.fitted_value,
                fallback_ci_low=model.confidence_interval_low,
                fallback_ci_high=model.confidence_interval_high,
            ),
            dose_response_config_snapshot=model.dose_response_config_snapshot,
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
            readout_definition_id=entity.readout_definition_id,
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
            excluded_points=_serialize_excluded_points(entity.excluded_points),
            fit_quality_warnings=entity.fit_quality_warnings,
            intercept_values=_serialize_intercept_values(entity.intercept_values),
            dose_response_config_snapshot=entity.dose_response_config_snapshot,
        )
