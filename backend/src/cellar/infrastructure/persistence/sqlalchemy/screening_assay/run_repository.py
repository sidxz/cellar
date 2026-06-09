"""SQLAlchemy repository for Run aggregates."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from cellar.domain.screening_assay.enums import (
    PlateFormat,
    RunRelationshipType,
    RunStatus,
    WellType,
)
from cellar.domain.screening_assay.repository import CollectionLinkResult, TargetLinkResult
from cellar.domain.screening_assay.run import Plate, Run, Well
from cellar.domain.screening_assay.target import TargetRef
from cellar.domain.shared.hit_criterion import HitCriterion
from cellar.domain.shared.value_objects import Barcode
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CollectionModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    PlateModel,
    RunModel,
    TargetModel,
    WellModel,
    run_collections,
    run_targets,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import RunTagLinkModel
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_filter import tag_filter_subquery


class SQLAlchemyRunRepository(SQLAlchemyRepository[Run, RunModel]):
    model_class = RunModel

    # ------------------------------------------------------------------
    # Custom query methods
    # ------------------------------------------------------------------

    async def find_by_ids(
        self, workspace_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Run]:
        """Bulk-fetch runs by id, scoped to workspace.

        Returns ``{run.id: run, ...}`` so the search-grid aggregator can join
        each fetched ``DoseResponseCurve`` back to its owning Run aggregate
        without an N+1. Missing ids are silently dropped.
        """
        if not ids:
            return {}
        stmt = select(RunModel).where(
            RunModel.workspace_id == workspace_id,
            RunModel.id.in_(ids),
        )
        result = await self._session.execute(stmt)
        return {m.id: self._to_domain_tracked(m) for m in result.scalars().all()}

    async def find_by_protocol(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        *,
        tags: list[uuid.UUID] | None = None,
        tag_logic: str = "any",
    ) -> list[Run]:
        """List all runs for a protocol in a workspace, newest first."""
        stmt = select(RunModel).where(
            RunModel.workspace_id == workspace_id,
            RunModel.protocol_id == protocol_id,
        )
        if tags:
            stmt = stmt.where(
                RunModel.id.in_(
                    tag_filter_subquery(
                        RunTagLinkModel, "run_id", tags, match_all=tag_logic == "all"
                    )
                )
            )
        stmt = stmt.order_by(RunModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def aggregate_stats_by_protocol(
        self, workspace_id: uuid.UUID
    ) -> dict[uuid.UUID, tuple[int, date | None]]:
        """One row per protocol — total run count and most recent run_date.

        Used by the rich protocol picker. Single round-trip to avoid the
        N+1 explosion of stats endpoints when the picker opens.
        """
        stmt = (
            select(
                RunModel.protocol_id,
                func.count(RunModel.id),
                func.max(RunModel.run_date),
            )
            .where(RunModel.workspace_id == workspace_id)
            .group_by(RunModel.protocol_id)
        )
        result = await self._session.execute(stmt)
        return {row[0]: (int(row[1]), row[2]) for row in result.all()}

    async def find_children(self, workspace_id: uuid.UUID, parent_run_id: uuid.UUID) -> list[Run]:
        """Find all child runs of a parent run."""
        stmt = (
            select(RunModel)
            .where(
                RunModel.workspace_id == workspace_id,
                RunModel.parent_run_id == parent_run_id,
            )
            .order_by(RunModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def delete(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> None:
        """Delete a run by id, scoped to workspace. CASCADE handles plates+wells."""
        from sqlalchemy import delete as sa_delete

        stmt = sa_delete(RunModel).where(
            RunModel.id == run_id,
            RunModel.workspace_id == workspace_id,
        )
        await self._session.execute(stmt)

    async def is_locked(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> bool:
        """Efficient lock check — selects only the is_locked column."""
        stmt = select(RunModel.is_locked).where(
            RunModel.workspace_id == workspace_id,
            RunModel.id == run_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return False
        return bool(row)

    # ------------------------------------------------------------------
    # Target association methods (_owns lives on the shared base repository)
    # ------------------------------------------------------------------

    async def find_lock_state(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> bool | None:
        """Column-only guard query. None = run missing / cross-workspace.

        Unlike ``is_locked()`` this distinguishes not-found from unlocked,
        and avoids hydrating the plates -> wells selectin chain.
        """
        result = await self._session.execute(
            select(RunModel.is_locked).where(
                RunModel.id == run_id,
                RunModel.workspace_id == workspace_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return bool(row)

    async def add_target(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID, target_id: uuid.UUID
    ) -> TargetLinkResult:
        """Link a target to a run (idempotent). Workspace-checked on both sides.

        The distinct not-found outcomes let callers surface a 404 instead of
        a silent success.
        """
        if not await self._owns(RunModel, run_id, workspace_id):
            return TargetLinkResult.OWNER_NOT_FOUND
        if not await self._owns(TargetModel, target_id, workspace_id):
            return TargetLinkResult.TARGET_NOT_FOUND
        result = await self._session.execute(
            pg_insert(run_targets)
            .values(run_id=run_id, target_id=target_id)
            .on_conflict_do_nothing()
        )
        if result.rowcount:
            return TargetLinkResult.ADDED
        return TargetLinkResult.ALREADY_LINKED

    async def remove_target(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID, target_id: uuid.UUID
    ) -> bool:
        """Unlink a run target. Returns True if a link row was removed."""
        result = await self._session.execute(
            run_targets.delete().where(
                run_targets.c.run_id == run_id,
                run_targets.c.target_id == target_id,
                run_targets.c.run_id.in_(
                    select(RunModel.id).where(RunModel.workspace_id == workspace_id)
                ),
            )
        )
        return bool(result.rowcount)

    async def find_target_refs_for_runs(
        self, workspace_id: uuid.UUID, run_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[TargetRef]]:
        if not run_ids:
            return {}
        result = await self._session.execute(
            select(
                run_targets.c.run_id,
                TargetModel.id,
                TargetModel.name,
                TargetModel.target_type,
            )
            .select_from(
                run_targets.join(TargetModel, run_targets.c.target_id == TargetModel.id)
                # Workspace-scoped on the owner side too — tenant isolation
                # must not rest solely on the TargetModel filter.
                .join(RunModel, run_targets.c.run_id == RunModel.id)
            )
            .where(
                run_targets.c.run_id.in_(run_ids),
                RunModel.workspace_id == workspace_id,
                TargetModel.workspace_id == workspace_id,
            )
            .order_by(TargetModel.name)
        )
        out: dict[uuid.UUID, list[TargetRef]] = {rid: [] for rid in run_ids}
        for run_id, tid, name, tt in result.all():
            out.setdefault(run_id, []).append(TargetRef(id=tid, name=name, target_type=tt))
        return out

    # ------------------------------------------------------------------
    # Collection association methods (mirrors run_targets above)
    # ------------------------------------------------------------------

    async def add_collection(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID, collection_id: uuid.UUID
    ) -> CollectionLinkResult:
        """Link a collection to a run (idempotent). Workspace-checked on both sides.

        The distinct not-found outcomes let callers surface a 404 instead of a
        silent success.
        """
        if not await self._owns(RunModel, run_id, workspace_id):
            return CollectionLinkResult.OWNER_NOT_FOUND
        if not await self._owns(CollectionModel, collection_id, workspace_id):
            return CollectionLinkResult.COLLECTION_NOT_FOUND
        result = await self._session.execute(
            pg_insert(run_collections)
            .values(run_id=run_id, collection_id=collection_id)
            .on_conflict_do_nothing()
        )
        if result.rowcount:
            return CollectionLinkResult.ADDED
        return CollectionLinkResult.ALREADY_LINKED

    async def remove_collection(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID, collection_id: uuid.UUID
    ) -> bool:
        """Detach a collection from a run. Returns True if a link row was removed."""
        if not await self._owns(RunModel, run_id, workspace_id):
            return False
        result = await self._session.execute(
            delete(run_collections).where(
                run_collections.c.run_id == run_id,
                run_collections.c.collection_id == collection_id,
            )
        )
        return bool(result.rowcount)

    # ------------------------------------------------------------------
    # Mapping: SA model <-> domain aggregate
    # ------------------------------------------------------------------

    def _to_domain(self, model: RunModel) -> Run:
        # Build plates with nested wells
        plates: list[Plate] = []
        all_wells: list[Well] = []

        for pm in model.plates:
            plate = Plate(
                id=pm.id,
                run_id=pm.run_id,
                plate_number=pm.plate_number,
                barcode=Barcode(value=pm.barcode) if pm.barcode else None,
                format=PlateFormat(pm.format) if pm.format else None,
                plate_map=pm.plate_map,
                parent_plate_id=pm.parent_plate_id,
                template_id=pm.template_id,
                created_at=pm.created_at,
                updated_at=pm.updated_at,
            )
            plates.append(plate)

            for wm in pm.wells:
                well = Well(
                    id=wm.id,
                    plate_id=wm.plate_id,
                    row=wm.row,
                    column=wm.column,
                    well_type=WellType(wm.well_type),
                    batch_id=wm.batch_id,
                    dose=wm.dose,
                    created_at=wm.created_at,
                    updated_at=wm.updated_at,
                )
                all_wells.append(well)

        return Run(
            id=model.id,
            workspace_id=model.workspace_id,
            protocol_id=model.protocol_id,
            run_date=model.run_date,
            operator=model.operator,
            performed_at_org_id=model.performed_at_org_id,
            status=RunStatus(model.status),
            parent_run_id=model.parent_run_id,
            run_relationship_type=(
                RunRelationshipType(model.run_relationship_type)
                if model.run_relationship_type
                else None
            ),
            plate_format=PlateFormat(model.plate_format) if model.plate_format else None,
            plate_template_id=model.plate_template_id,
            conditions=model.conditions,
            qc_metrics=model.qc_metrics,
            is_locked=model.is_locked,
            locked_at=model.locked_at,
            locked_by=model.locked_by,
            lock_reason=model.lock_reason,
            notes=model.notes,
            eln_entry_id=model.eln_entry_id,
            # Preserve the unset (None) vs "show all, recorded" ([]) distinction —
            # do NOT collapse with `or []` the way the protocol's recommendation does.
            hit_criteria=(
                [HitCriterion.from_dict(c) for c in model.hit_criteria]
                if model.hit_criteria is not None
                else None
            ),
            hit_criteria_set_by=model.hit_criteria_set_by,
            hit_criteria_set_at=model.hit_criteria_set_at,
            plates=plates,
            wells=all_wells,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: Run) -> RunModel:
        model = RunModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            protocol_id=aggregate.protocol_id,
            run_date=aggregate.run_date,
            operator=aggregate.operator,
            performed_at_org_id=aggregate.performed_at_org_id,
            status=aggregate.status.value,
            parent_run_id=aggregate.parent_run_id,
            run_relationship_type=(
                aggregate.run_relationship_type.value if aggregate.run_relationship_type else None
            ),
            plate_format=aggregate.plate_format.value if aggregate.plate_format else None,
            plate_template_id=aggregate.plate_template_id,
            conditions=aggregate.conditions,
            qc_metrics=aggregate.qc_metrics,
            is_locked=aggregate.is_locked,
            locked_at=aggregate.locked_at,
            locked_by=aggregate.locked_by,
            lock_reason=aggregate.lock_reason,
            notes=aggregate.notes,
            eln_entry_id=aggregate.eln_entry_id,
            hit_criteria=(
                [c.to_dict() for c in aggregate.hit_criteria]
                if aggregate.hit_criteria is not None
                else None
            ),
            hit_criteria_set_by=aggregate.hit_criteria_set_by,
            hit_criteria_set_at=aggregate.hit_criteria_set_at,
            version=aggregate.version,
        )

        # Build well lookup by plate_id
        wells_by_plate: dict[uuid.UUID, list[Well]] = {}
        for w in aggregate.wells:
            wells_by_plate.setdefault(w.plate_id, []).append(w)

        model.plates = [
            self._plate_to_model(p, wells_by_plate.get(p.id, [])) for p in aggregate.plates
        ]
        return model

    def _update_model(self, model: RunModel, aggregate: Run) -> None:
        model.status = aggregate.status.value
        model.run_date = aggregate.run_date
        model.operator = aggregate.operator
        model.performed_at_org_id = aggregate.performed_at_org_id
        model.parent_run_id = aggregate.parent_run_id
        model.run_relationship_type = (
            aggregate.run_relationship_type.value if aggregate.run_relationship_type else None
        )
        model.plate_format = aggregate.plate_format.value if aggregate.plate_format else None
        model.plate_template_id = aggregate.plate_template_id
        model.conditions = aggregate.conditions
        model.qc_metrics = aggregate.qc_metrics
        model.is_locked = aggregate.is_locked
        model.locked_at = aggregate.locked_at
        model.locked_by = aggregate.locked_by
        model.lock_reason = aggregate.lock_reason
        model.notes = aggregate.notes
        model.eln_entry_id = aggregate.eln_entry_id
        model.hit_criteria = (
            [c.to_dict() for c in aggregate.hit_criteria]
            if aggregate.hit_criteria is not None
            else None
        )
        model.hit_criteria_set_by = aggregate.hit_criteria_set_by
        model.hit_criteria_set_at = aggregate.hit_criteria_set_at

        # Rebuild plate/well collections
        wells_by_plate: dict[uuid.UUID, list[Well]] = {}
        for w in aggregate.wells:
            wells_by_plate.setdefault(w.plate_id, []).append(w)

        model.plates = [
            self._plate_to_model(p, wells_by_plate.get(p.id, [])) for p in aggregate.plates
        ]

    # ------------------------------------------------------------------
    # Owned entity mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _plate_to_model(plate: Plate, wells: list[Well]) -> PlateModel:
        pm = PlateModel(
            id=plate.id,
            run_id=plate.run_id,
            plate_number=plate.plate_number,
            barcode=plate.barcode.value if plate.barcode else None,
            format=plate.format.value if plate.format else None,
            plate_map=plate.plate_map,
            parent_plate_id=plate.parent_plate_id,
            template_id=plate.template_id,
        )
        pm.wells = [SQLAlchemyRunRepository._well_to_model(w) for w in wells]
        return pm

    @staticmethod
    def _well_to_model(well: Well) -> WellModel:
        return WellModel(
            id=well.id,
            plate_id=well.plate_id,
            row=well.row,
            column=well.column,
            well_type=well.well_type.value,
            batch_id=well.batch_id,
            dose=well.dose,
        )
