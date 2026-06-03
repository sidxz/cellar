"""SQLAlchemy repository for ReadoutData entities.

ReadoutData is not an AggregateRoot — standalone repo with manual CRUD.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select

from cellar.domain.screening_assay.enums import (
    ReadoutNormalization,
    unit_for_normalization,
)
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.shared.enums import Qualifier
from cellar.domain.shared.value_objects import QualifiedValue
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ReadoutDataModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyReadoutDataRepository:
    """Persists ReadoutData entities to PostgreSQL."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def _find_by_id_unscoped(self, id: uuid.UUID) -> ReadoutData | None:
        model = await self._uow.session.get(ReadoutDataModel, id)
        return self._to_domain(model) if model else None

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> ReadoutData | None:
        """Load by PK scoped to workspace."""
        stmt = select(ReadoutDataModel).where(
            ReadoutDataModel.id == id,
            ReadoutDataModel.workspace_id == workspace_id,
        )
        result = await self._uow.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_run(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> list[ReadoutData]:
        stmt = (
            select(ReadoutDataModel)
            .where(
                ReadoutDataModel.workspace_id == workspace_id,
                ReadoutDataModel.run_id == run_id,
            )
            .order_by(ReadoutDataModel.created_at)
        )
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_by_molecule(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[ReadoutData]:
        """All non-outlier readout data for a molecule, ordered by created_at desc."""
        stmt = (
            select(ReadoutDataModel)
            .where(
                ReadoutDataModel.workspace_id == workspace_id,
                ReadoutDataModel.molecule_id == molecule_id,
                ReadoutDataModel.is_outlier == False,  # noqa: E712
            )
            .order_by(ReadoutDataModel.created_at.desc())
        )
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_aggregated_by_molecules(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        specs: list[tuple[uuid.UUID, str | None]],
    ) -> dict[uuid.UUID, dict[tuple[uuid.UUID, str | None], "AggregatedReadout"]]:
        """Batch query: molecule_id -> (readout_def_id, normalization) -> aggregated value.

        ``specs`` selects which (readout_definition, normalization_applied) pairs
        to aggregate independently. ``None`` in the second slot means the raw
        layer (``normalization_applied IS NULL``); any string selects the
        matching computed normalization (e.g. ``"percent_inhibition"``,
        ``"z_score"``). Filtering by ``normalization_applied`` is required —
        without it raw and computed rows would be averaged together since both
        share the same ``readout_definition_id``.

        Aggregation method comes from ``readout_definition.aggregation``.
        """
        from cellar.domain.screening_assay.activity_types import AggregatedReadout
        from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
            ReadoutDefinitionModel,
        )

        if not molecule_ids or not specs:
            return {}

        rd_def_ids = list({rd_id for rd_id, _ in specs})
        wanted = {(rd_id, norm) for rd_id, norm in specs}

        stmt = (
            select(
                ReadoutDataModel.molecule_id,
                ReadoutDataModel.readout_definition_id,
                ReadoutDataModel.normalization_applied,
                ReadoutDefinitionModel.name.label("readout_name"),
                ReadoutDefinitionModel.aggregation,
                ReadoutDefinitionModel.unit,
                func.avg(ReadoutDataModel.value_numeric).label("avg_val"),
                func.min(ReadoutDataModel.value_numeric).label("min_val"),
                func.max(ReadoutDataModel.value_numeric).label("max_val"),
                func.count(ReadoutDataModel.value_numeric).label("count_val"),
            )
            .join(
                ReadoutDefinitionModel,
                ReadoutDataModel.readout_definition_id == ReadoutDefinitionModel.id,
            )
            .where(
                ReadoutDataModel.workspace_id == workspace_id,
                ReadoutDataModel.molecule_id.in_(molecule_ids),
                ReadoutDataModel.readout_definition_id.in_(rd_def_ids),
                ReadoutDataModel.is_outlier == False,  # noqa: E712
            )
            .group_by(
                ReadoutDataModel.molecule_id,
                ReadoutDataModel.readout_definition_id,
                ReadoutDataModel.normalization_applied,
                ReadoutDefinitionModel.name,
                ReadoutDefinitionModel.aggregation,
                ReadoutDefinitionModel.unit,
            )
        )

        result = await self._uow.session.execute(stmt)
        rows = result.all()

        out: dict[uuid.UUID, dict[tuple[uuid.UUID, str | None], AggregatedReadout]] = {}
        for row in rows:
            key = (row.readout_definition_id, row.normalization_applied)
            if key not in wanted:
                continue

            agg = row.aggregation or "mean"
            if agg == "min":
                val = row.min_val
            elif agg == "max":
                val = row.max_val
            else:  # mean, none, median (approx as mean)
                val = row.avg_val

            # Normalized rows (% inh / % act / % control) carry the formula's
            # output unit, not the raw readout's unit. The raw readout's unit
            # is meaningful only for the raw layer.
            unit = unit_for_normalization(row.normalization_applied, row.unit)

            entry = AggregatedReadout(
                readout_definition_id=row.readout_definition_id,
                readout_name=row.readout_name,
                value=val,
                qualifier=None,
                unit=unit,
                aggregation=agg,
                data_point_count=row.count_val,
            )
            out.setdefault(row.molecule_id, {})[key] = entry

        return out

    async def find_by_molecule_and_definition(
        self,
        workspace_id: uuid.UUID,
        molecule_id: uuid.UUID,
        readout_definition_id: uuid.UUID,
    ) -> list[ReadoutData]:
        """Non-outlier, non-computed readout data for a molecule+definition pair."""
        stmt = (
            select(ReadoutDataModel)
            .where(
                ReadoutDataModel.workspace_id == workspace_id,
                ReadoutDataModel.molecule_id == molecule_id,
                ReadoutDataModel.readout_definition_id == readout_definition_id,
                ReadoutDataModel.is_outlier.is_(False),
                ReadoutDataModel.is_computed.is_(False),
            )
            .order_by(ReadoutDataModel.created_at.desc())
        )
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_wellless_by_keys(
        self,
        *,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        molecule_id: uuid.UUID | None,
        batch_id: uuid.UUID | None,
        readout_definition_id: uuid.UUID,
    ) -> ReadoutData | None:
        """Find the single well-less, non-computed row matching the summary key.

        ``molecule_id`` and ``batch_id`` are nullable; ``None`` is matched with
        ``IS NULL`` (not ``= NULL``) so summary rows with no molecule/batch are
        located correctly.
        """
        stmt = select(ReadoutDataModel).where(
            ReadoutDataModel.workspace_id == workspace_id,
            ReadoutDataModel.run_id == run_id,
            ReadoutDataModel.well_id.is_(None),
            ReadoutDataModel.readout_definition_id == readout_definition_id,
            ReadoutDataModel.is_computed.is_(False),
            (
                ReadoutDataModel.molecule_id == molecule_id
                if molecule_id is not None
                else ReadoutDataModel.molecule_id.is_(None)
            ),
            (
                ReadoutDataModel.batch_id == batch_id
                if batch_id is not None
                else ReadoutDataModel.batch_id.is_(None)
            ),
        )
        result = await self._uow.session.execute(stmt)
        model = result.scalars().first()
        return self._to_domain(model) if model is not None else None

    async def find_grouped_by_condition(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        condition_name: str,
    ) -> list:
        """Aggregate readout values grouped by a named condition across runs.

        Returns rows with fields: condition_value, avg_value, min_value,
        max_value, data_point_count.
        """
        from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
            ReadoutDefinitionModel,
            RunModel,
        )

        stmt = (
            select(
                RunModel.conditions[condition_name].as_string().label("condition_value"),
                func.avg(ReadoutDataModel.value_numeric).label("avg_value"),
                func.min(ReadoutDataModel.value_numeric).label("min_value"),
                func.max(ReadoutDataModel.value_numeric).label("max_value"),
                func.count(ReadoutDataModel.value_numeric).label("data_point_count"),
            )
            .join(RunModel, ReadoutDataModel.run_id == RunModel.id)
            .join(
                ReadoutDefinitionModel,
                ReadoutDataModel.readout_definition_id == ReadoutDefinitionModel.id,
            )
            .where(
                ReadoutDataModel.workspace_id == workspace_id,
                RunModel.protocol_id == protocol_id,
                RunModel.conditions[condition_name].as_string() != None,  # noqa: E711
                ReadoutDataModel.is_outlier.is_(False),
                ReadoutDataModel.value_numeric != None,  # noqa: E711
            )
            .group_by(RunModel.conditions[condition_name].as_string())
            .order_by(RunModel.conditions[condition_name].as_string())
        )
        result = await self._uow.session.execute(stmt)
        return result.all()

    async def get_molecule_counts(
        self, workspace_id: uuid.UUID, run_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Return {run_id: distinct_molecule_count} for the given runs."""
        if not run_ids:
            return {}
        stmt = (
            select(
                ReadoutDataModel.run_id,
                func.count(func.distinct(ReadoutDataModel.molecule_id)),
            )
            .where(
                ReadoutDataModel.run_id.in_(run_ids),
                ReadoutDataModel.molecule_id.is_not(None),
            )
            .group_by(ReadoutDataModel.run_id)
        )
        rows = await self._uow.session.execute(stmt)
        return {row[0]: row[1] for row in rows.all()}

    async def delete_computed_for_run(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> int:
        """Delete all computed readout data rows for a run. Returns deleted count."""
        stmt = delete(ReadoutDataModel).where(
            ReadoutDataModel.workspace_id == workspace_id,
            ReadoutDataModel.run_id == run_id,
            ReadoutDataModel.is_computed.is_(True),
        )
        result = await self._uow.session.execute(stmt)
        return result.rowcount

    async def delete_for_run(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> int:
        """Delete ALL readout data rows for a run (raw + computed). Returns count."""
        stmt = delete(ReadoutDataModel).where(
            ReadoutDataModel.workspace_id == workspace_id,
            ReadoutDataModel.run_id == run_id,
        )
        result = await self._uow.session.execute(stmt)
        return result.rowcount

    async def save(self, entity: ReadoutData) -> None:
        existing = await self._uow.session.get(ReadoutDataModel, entity.id)
        if existing is None:
            model = self._to_model(entity)
            self._uow.session.add(model)
        else:
            if existing.workspace_id != entity.workspace_id:
                from cellar.domain.shared.errors import AuthorizationError

                raise AuthorizationError("Cannot update ReadoutData from a different workspace")
            self._update_model(existing, entity)

    async def save_bulk(self, entities: list[ReadoutData]) -> None:
        """Bulk insert readout data points.

        Optimised for the compute pipeline: collects all entities into a
        single ``add_all`` call and performs one flush at the end. Falls
        back to per-entity ``save`` for any entity whose row already exists
        (so retry semantics survive when callers don't pre-clean).
        """
        if not entities:
            return

        existing_ids = set()
        ids = [e.id for e in entities]
        if ids:
            stmt = select(ReadoutDataModel.id).where(ReadoutDataModel.id.in_(ids))
            result = await self._uow.session.execute(stmt)
            existing_ids = {row[0] for row in result.all()}

        to_insert: list[ReadoutDataModel] = []
        for entity in entities:
            if entity.id in existing_ids:
                await self.save(entity)
            else:
                to_insert.append(self._to_model(entity))

        if to_insert:
            self._uow.session.add_all(to_insert)
            await self._uow.session.flush()

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = delete(ReadoutDataModel).where(
            ReadoutDataModel.workspace_id == workspace_id,
            ReadoutDataModel.id == id,
        )
        await self._uow.session.execute(stmt)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(model: ReadoutDataModel) -> ReadoutData:
        value: QualifiedValue | None = None
        if model.value_numeric is not None:
            value = QualifiedValue(
                value=model.value_numeric,
                qualifier=(
                    Qualifier(model.value_qualifier) if model.value_qualifier else Qualifier.EQUAL
                ),
            )
        return ReadoutData(
            id=model.id,
            workspace_id=model.workspace_id,
            run_id=model.run_id,
            well_id=model.well_id,
            molecule_id=model.molecule_id,
            batch_id=model.batch_id,
            readout_definition_id=model.readout_definition_id,
            value=value,
            value_text=model.value_text,
            is_outlier=model.is_outlier,
            is_computed=model.is_computed,
            normalization_applied=(
                ReadoutNormalization(model.normalization_applied)
                if model.normalization_applied
                else None
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_model(entity: ReadoutData) -> ReadoutDataModel:
        return ReadoutDataModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            run_id=entity.run_id,
            well_id=entity.well_id,
            molecule_id=entity.molecule_id,
            batch_id=entity.batch_id,
            readout_definition_id=entity.readout_definition_id,
            value_numeric=entity.value.value if entity.value else None,
            value_qualifier=entity.value.qualifier.value if entity.value else None,
            value_text=entity.value_text,
            is_outlier=entity.is_outlier,
            is_computed=entity.is_computed,
            normalization_applied=(
                entity.normalization_applied.value
                if entity.normalization_applied is not None
                else None
            ),
        )

    @staticmethod
    def _update_model(model: ReadoutDataModel, entity: ReadoutData) -> None:
        model.run_id = entity.run_id
        model.well_id = entity.well_id
        model.molecule_id = entity.molecule_id
        model.batch_id = entity.batch_id
        model.readout_definition_id = entity.readout_definition_id
        model.value_numeric = entity.value.value if entity.value else None
        model.value_qualifier = entity.value.qualifier.value if entity.value else None
        model.value_text = entity.value_text
        model.is_outlier = entity.is_outlier
        model.is_computed = entity.is_computed
        model.normalization_applied = (
            entity.normalization_applied.value
            if entity.normalization_applied is not None
            else None
        )
