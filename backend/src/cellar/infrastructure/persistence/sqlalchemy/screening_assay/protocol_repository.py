"""SQLAlchemy repository for Protocol aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from cellar.application.screening._dose_response_config_serde import (
    deserialize_dose_response_config,
    serialize_dose_response_config,
)
from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.enums import (
    ConditionDataType,
    PosControlSignal,
    ProtocolStatus,
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
    ReadoutNormalization,
)
from cellar.domain.screening_assay.protocol import (
    ConditionDefinition,
    Protocol,
    ReadoutDefinition,
)
from cellar.domain.screening_assay.target import EffectiveTarget, TargetRef
from cellar.domain.shared.enums import ConcentrationUnit
from cellar.domain.shared.hit_criterion import HitCriterion
from cellar.domain.shared.ontology import OntologyTerm
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ConditionDefinitionModel,
    ProtocolModel,
    ReadoutDefinitionModel,
    RunModel,
    TargetModel,
    protocol_projects,
    protocol_targets,
    run_targets,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import (
    ProtocolTagLinkModel,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_filter import (
    tag_filter_subquery,
)


class SQLAlchemyProtocolRepository(SQLAlchemyRepository[Protocol, ProtocolModel]):
    model_class = ProtocolModel

    # ------------------------------------------------------------------
    # Custom query methods
    # ------------------------------------------------------------------

    async def find_active_by_lineage(
        self, workspace_id: uuid.UUID, parent_protocol_id: uuid.UUID
    ) -> Protocol | None:
        """Find the active protocol for a given lineage (parent)."""
        stmt = select(ProtocolModel).where(
            ProtocolModel.workspace_id == workspace_id,
            ProtocolModel.parent_protocol_id == parent_protocol_id,
            ProtocolModel.status == ProtocolStatus.ACTIVE.value,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain_tracked(model)

    async def find_by_name(self, workspace_id: uuid.UUID, name: str) -> Protocol | None:
        """Find a protocol by exact name within a workspace."""
        stmt = select(ProtocolModel).where(
            ProtocolModel.workspace_id == workspace_id,
            ProtocolModel.name == name,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain_tracked(model)

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
        tags: list[uuid.UUID] | None = None,
        tag_logic: str = "any",
    ) -> list[Protocol]:
        """List protocols in a workspace, ordered by id for stable cursor paging."""
        stmt = select(ProtocolModel).where(ProtocolModel.workspace_id == workspace_id)
        if tags:
            stmt = stmt.where(
                ProtocolModel.id.in_(
                    tag_filter_subquery(
                        ProtocolTagLinkModel, "protocol_id", tags, match_all=tag_logic == "all"
                    )
                )
            )
        stmt = stmt.order_by(ProtocolModel.id)
        if cursor_id is not None:
            stmt = stmt.where(ProtocolModel.id > cursor_id)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def find_by_ids(self, workspace_id: uuid.UUID, ids: list[uuid.UUID]) -> list[Protocol]:
        """Bulk-fetch protocols by a list of IDs within a workspace."""
        if not ids:
            return []
        stmt = select(ProtocolModel).where(
            ProtocolModel.workspace_id == workspace_id,
            ProtocolModel.id.in_(ids),
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        """Delete a protocol by ID (only for DRAFT protocols)."""
        model = await self._session.get(ProtocolModel, id)
        if model is not None and model.workspace_id == workspace_id:
            await self._session.delete(model)

    # ------------------------------------------------------------------
    # Project association methods
    # ------------------------------------------------------------------

    async def add_to_project(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, project_id: uuid.UUID
    ) -> None:
        """Link a protocol to a project (idempotent via ON CONFLICT DO NOTHING).

        Defense-in-depth: only inserts if BOTH the protocol AND the project
        belong to the workspace.
        """
        from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
            ProjectModel,
        )

        # Verify protocol belongs to workspace
        ownership_stmt = select(ProtocolModel.id).where(
            ProtocolModel.id == protocol_id,
            ProtocolModel.workspace_id == workspace_id,
        )
        ownership_result = await self._session.execute(ownership_stmt)
        if ownership_result.scalar_one_or_none() is None:
            return

        # Verify project belongs to workspace
        project_stmt = select(ProjectModel.id).where(
            ProjectModel.id == project_id,
            ProjectModel.workspace_id == workspace_id,
        )
        project_result = await self._session.execute(project_stmt)
        if project_result.scalar_one_or_none() is None:
            return

        stmt = (
            pg_insert(protocol_projects)
            .values(protocol_id=protocol_id, project_id=project_id)
            .on_conflict_do_nothing()
        )
        await self._session.execute(stmt)

    async def remove_from_project(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, project_id: uuid.UUID
    ) -> None:
        """Unlink a protocol from a project.

        Defense-in-depth: only deletes if the protocol belongs to the workspace.
        """
        stmt = protocol_projects.delete().where(
            protocol_projects.c.protocol_id == protocol_id,
            protocol_projects.c.project_id == project_id,
            protocol_projects.c.protocol_id.in_(
                select(ProtocolModel.id).where(ProtocolModel.workspace_id == workspace_id)
            ),
        )
        await self._session.execute(stmt)

    async def find_by_project(
        self,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
        tags: list[uuid.UUID] | None = None,
        tag_logic: str = "any",
    ) -> list[Protocol]:
        """Return protocols linked to a project, ordered by id for stable cursor paging."""
        subq = select(protocol_projects.c.protocol_id).where(
            protocol_projects.c.project_id == project_id
        )
        stmt = select(ProtocolModel).where(
            ProtocolModel.workspace_id == workspace_id,
            ProtocolModel.id.in_(subq),
        )
        if tags:
            stmt = stmt.where(
                ProtocolModel.id.in_(
                    tag_filter_subquery(
                        ProtocolTagLinkModel, "protocol_id", tags, match_all=tag_logic == "all"
                    )
                )
            )
        stmt = stmt.order_by(ProtocolModel.id)
        if cursor_id is not None:
            stmt = stmt.where(ProtocolModel.id > cursor_id)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def find_protocol_ids_in_projects(
        self, workspace_id: uuid.UUID, project_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        """IDs of protocols linked to any of the given projects (workspace-scoped)."""
        if not project_ids:
            return set()
        stmt = select(protocol_projects.c.protocol_id).where(
            protocol_projects.c.project_id.in_(project_ids),
            protocol_projects.c.protocol_id.in_(
                select(ProtocolModel.id).where(ProtocolModel.workspace_id == workspace_id)
            ),
        )
        result = await self._session.execute(stmt)
        return set(result.scalars().all())

    async def find_project_ids(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Return all project IDs linked to a given protocol, scoped to workspace."""
        from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
            ProjectModel,
        )

        stmt = (
            select(protocol_projects.c.project_id)
            .join(ProjectModel, protocol_projects.c.project_id == ProjectModel.id)
            .where(
                protocol_projects.c.protocol_id == protocol_id,
                ProjectModel.workspace_id == workspace_id,
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Target association methods
    # ------------------------------------------------------------------

    async def _owns(
        self, model: type, id_: uuid.UUID, workspace_id: uuid.UUID
    ) -> bool:
        result = await self._session.execute(
            select(model.id).where(model.id == id_, model.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none() is not None

    async def add_direct_target(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, target_id: uuid.UUID
    ) -> None:
        """Link a direct target to a protocol (idempotent via ON CONFLICT DO NOTHING).

        Defense-in-depth: only inserts if BOTH the protocol AND the target
        belong to the workspace.
        """
        if not await self._owns(ProtocolModel, protocol_id, workspace_id):
            return
        if not await self._owns(TargetModel, target_id, workspace_id):
            return
        await self._session.execute(
            pg_insert(protocol_targets)
            .values(protocol_id=protocol_id, target_id=target_id)
            .on_conflict_do_nothing()
        )

    async def remove_direct_target(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, target_id: uuid.UUID
    ) -> None:
        """Unlink a direct target. Defense-in-depth: workspace-scoped."""
        await self._session.execute(
            protocol_targets.delete().where(
                protocol_targets.c.protocol_id == protocol_id,
                protocol_targets.c.target_id == target_id,
                protocol_targets.c.protocol_id.in_(
                    select(ProtocolModel.id).where(ProtocolModel.workspace_id == workspace_id)
                ),
            )
        )

    async def find_direct_target_ids(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> list[uuid.UUID]:
        result = await self._session.execute(
            select(protocol_targets.c.target_id)
            .join(ProtocolModel, protocol_targets.c.protocol_id == ProtocolModel.id)
            .where(
                protocol_targets.c.protocol_id == protocol_id,
                ProtocolModel.workspace_id == workspace_id,
            )
        )
        return list(result.scalars().all())

    async def _direct_ids(self, protocol_id: uuid.UUID) -> set[uuid.UUID]:
        result = await self._session.execute(
            select(protocol_targets.c.target_id).where(
                protocol_targets.c.protocol_id == protocol_id
            )
        )
        return set(result.scalars().all())

    async def find_effective_targets(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> list[EffectiveTarget]:
        direct_ids = await self._direct_ids(protocol_id)

        run_count_rows = await self._session.execute(
            select(run_targets.c.target_id, func.count(run_targets.c.run_id))
            .select_from(run_targets.join(RunModel, run_targets.c.run_id == RunModel.id))
            .where(RunModel.protocol_id == protocol_id)
            .group_by(run_targets.c.target_id)
        )
        run_counts = {tid: count for tid, count in run_count_rows.all()}

        all_ids = direct_ids | set(run_counts)
        if not all_ids:
            return []

        target_rows = await self._session.execute(
            select(TargetModel).where(
                TargetModel.workspace_id == workspace_id,
                TargetModel.id.in_(all_ids),
            )
        )
        out = [
            EffectiveTarget(
                id=t.id,
                name=t.name,
                target_type=t.target_type,
                is_direct=t.id in direct_ids,
                run_count=run_counts.get(t.id, 0),
            )
            for t in target_rows.scalars().all()
        ]
        out.sort(key=lambda e: e.name.lower())
        return out

    async def find_effective_targets_for_protocols(
        self, workspace_id: uuid.UUID, protocol_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[TargetRef]]:
        if not protocol_ids:
            return {}

        # protocol_id -> set(target_id): direct
        direct_rows = await self._session.execute(
            select(protocol_targets.c.protocol_id, protocol_targets.c.target_id).where(
                protocol_targets.c.protocol_id.in_(protocol_ids)
            )
        )
        by_protocol: dict[uuid.UUID, set[uuid.UUID]] = {pid: set() for pid in protocol_ids}
        for pid, tid in direct_rows.all():
            by_protocol[pid].add(tid)

        # protocol_id -> set(target_id): inherited via runs
        inherited_rows = await self._session.execute(
            select(RunModel.protocol_id, run_targets.c.target_id)
            .select_from(run_targets.join(RunModel, run_targets.c.run_id == RunModel.id))
            .where(RunModel.protocol_id.in_(protocol_ids))
        )
        for pid, tid in inherited_rows.all():
            by_protocol.setdefault(pid, set()).add(tid)

        all_ids = {tid for ids in by_protocol.values() for tid in ids}
        if not all_ids:
            return {pid: [] for pid in protocol_ids}

        target_rows = await self._session.execute(
            select(TargetModel.id, TargetModel.name, TargetModel.target_type).where(
                TargetModel.workspace_id == workspace_id,
                TargetModel.id.in_(all_ids),
            )
        )
        ref_by_id = {
            tid: TargetRef(id=tid, name=name, target_type=tt)
            for tid, name, tt in target_rows.all()
        }
        return {
            pid: sorted(
                (ref_by_id[tid] for tid in ids if tid in ref_by_id),
                key=lambda r: r.name.lower(),
            )
            for pid, ids in by_protocol.items()
        }

    # ------------------------------------------------------------------
    # Mapping: SA model <-> domain aggregate
    # ------------------------------------------------------------------

    @staticmethod
    def _reconstruct_dose_response_config(
        data: dict | None,
    ) -> DoseResponseConfig | None:
        if data is None:
            return None
        return deserialize_dose_response_config(data)

    def _to_domain(self, model: ProtocolModel) -> Protocol:
        readout_defs = [
            ReadoutDefinition(
                id=rd.id,
                protocol_id=rd.protocol_id,
                name=rd.name,
                description=rd.description,
                data_type=ReadoutDataType(rd.data_type),
                unit=rd.unit,
                aggregation=ReadoutAggregation(rd.aggregation),
                precision=rd.precision,
                normalizations=frozenset(
                    ReadoutNormalization(v) for v in (rd.normalizations or [])
                ),
                is_calculated=rd.is_calculated,
                calculation_formula=rd.calculation_formula,
                display_order=rd.display_order,
                pick_list_values=rd.pick_list_values,
                dose_response_config=self._reconstruct_dose_response_config(
                    rd.dose_response_config
                ),
                created_at=rd.created_at,
                updated_at=rd.updated_at,
            )
            for rd in model.readout_definitions
        ]

        condition_defs = [
            ConditionDefinition(
                id=cd.id,
                protocol_id=cd.protocol_id,
                name=cd.name,
                data_type=ConditionDataType(cd.data_type),
                unit=cd.unit,
                pick_list_values=cd.pick_list_values,
                created_at=cd.created_at,
                updated_at=cd.updated_at,
            )
            for cd in model.condition_definitions
        ]

        # Reconstruct control_layouts: DB stores {format_str: uuid_str}
        control_layouts = None
        if model.control_layouts:
            control_layouts = {
                k: uuid.UUID(v) if isinstance(v, str) else v
                for k, v in model.control_layouts.items()
            }

        # Reconstruct ontology_annotations: DB stores {slot: [{term_id, label, ...}]}
        ontology_annotations = None
        if model.ontology_annotations:
            ontology_annotations = {
                slot: [
                    OntologyTerm(
                        term_id=t["term_id"],
                        label=t["label"],
                        ontology_source=t["ontology_source"],
                        uri=t.get("uri"),
                    )
                    for t in terms
                ]
                for slot, terms in model.ontology_annotations.items()
            }

        return Protocol(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            description=model.description,
            protocol_type=ProtocolType(model.protocol_type),
            category=model.category,
            protocol_version=model.protocol_version,
            parent_protocol_id=model.parent_protocol_id,
            status=ProtocolStatus(model.status),
            created_by=model.created_by,
            dose_unit=ConcentrationUnit(model.dose_unit),
            pos_control_signal=PosControlSignal(model.pos_control_signal),
            readout_definitions=readout_defs,
            condition_definitions=condition_defs,
            control_layouts=control_layouts,
            ontology_annotations=ontology_annotations,
            recommended_hit_criteria=[
                HitCriterion.from_dict(c) for c in (model.recommended_hit_criteria or [])
            ]
            or None,
            is_locked=model.is_locked,
            locked_by=model.locked_by,
            lock_reason=model.lock_reason,
            locked_at=model.locked_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    @staticmethod
    def _serialize_control_layouts(
        layouts: dict[str, uuid.UUID] | None,
    ) -> dict[str, str] | None:
        if not layouts:
            return None
        return {k: str(v) for k, v in layouts.items()}

    @staticmethod
    def _serialize_ontology_annotations(
        annotations: dict[str, list[OntologyTerm]] | None,
    ) -> dict | None:
        if not annotations:
            return None
        return {
            slot: [
                {
                    "term_id": t.term_id,
                    "label": t.label,
                    "ontology_source": t.ontology_source,
                    "uri": t.uri,
                }
                for t in terms
            ]
            for slot, terms in annotations.items()
        }

    def _to_model(self, aggregate: Protocol) -> ProtocolModel:
        model = ProtocolModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            name=aggregate.name,
            description=aggregate.description,
            protocol_type=aggregate.protocol_type.value,
            category=aggregate.category,
            protocol_version=aggregate.protocol_version,
            parent_protocol_id=aggregate.parent_protocol_id,
            status=aggregate.status.value,
            created_by=aggregate.created_by,
            dose_unit=aggregate.dose_unit.value,
            pos_control_signal=aggregate.pos_control_signal.value,
            version=aggregate.version,
            control_layouts=self._serialize_control_layouts(aggregate.control_layouts),
            ontology_annotations=self._serialize_ontology_annotations(
                aggregate.ontology_annotations
            ),
            recommended_hit_criteria=[c.to_dict() for c in aggregate.recommended_hit_criteria]
            if aggregate.recommended_hit_criteria
            else None,
            is_locked=aggregate.is_locked,
            locked_by=aggregate.locked_by,
            lock_reason=aggregate.lock_reason,
            locked_at=aggregate.locked_at,
        )
        model.readout_definitions = [
            self._readout_def_to_model(rd) for rd in aggregate.readout_definitions
        ]
        model.condition_definitions = [
            self._condition_def_to_model(cd) for cd in aggregate.condition_definitions
        ]
        return model

    def _update_model(self, model: ProtocolModel, aggregate: Protocol) -> None:
        model.name = aggregate.name
        model.description = aggregate.description
        model.protocol_type = aggregate.protocol_type.value
        model.category = aggregate.category
        model.protocol_version = aggregate.protocol_version
        model.parent_protocol_id = aggregate.parent_protocol_id
        model.status = aggregate.status.value
        model.dose_unit = aggregate.dose_unit.value
        model.pos_control_signal = aggregate.pos_control_signal.value
        model.control_layouts = self._serialize_control_layouts(aggregate.control_layouts)
        model.ontology_annotations = self._serialize_ontology_annotations(
            aggregate.ontology_annotations
        )
        model.recommended_hit_criteria = (
            [c.to_dict() for c in aggregate.recommended_hit_criteria]
            if aggregate.recommended_hit_criteria
            else None
        )
        model.is_locked = aggregate.is_locked
        model.locked_by = aggregate.locked_by
        model.lock_reason = aggregate.lock_reason
        model.locked_at = aggregate.locked_at

        # Replace owned entity collections
        model.readout_definitions = [
            self._readout_def_to_model(rd) for rd in aggregate.readout_definitions
        ]
        model.condition_definitions = [
            self._condition_def_to_model(cd) for cd in aggregate.condition_definitions
        ]

    # ------------------------------------------------------------------
    # Owned entity mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _readout_def_to_model(rd: ReadoutDefinition) -> ReadoutDefinitionModel:
        dose_response_dict = (
            serialize_dose_response_config(rd.dose_response_config)
            if rd.dose_response_config is not None
            else None
        )

        return ReadoutDefinitionModel(
            id=rd.id,
            protocol_id=rd.protocol_id,
            name=rd.name,
            description=rd.description,
            data_type=rd.data_type.value,
            unit=rd.unit,
            aggregation=rd.aggregation.value,
            precision=rd.precision,
            normalizations=sorted(n.value for n in rd.normalizations),
            is_calculated=rd.is_calculated,
            calculation_formula=rd.calculation_formula,
            display_order=rd.display_order,
            pick_list_values=(
                [v.to_dict() for v in rd.pick_list_values] if rd.pick_list_values else None
            ),
            dose_response_config=dose_response_dict,
        )

    @staticmethod
    def _condition_def_to_model(cd: ConditionDefinition) -> ConditionDefinitionModel:
        return ConditionDefinitionModel(
            id=cd.id,
            protocol_id=cd.protocol_id,
            name=cd.name,
            data_type=cd.data_type.value,
            unit=cd.unit,
            pick_list_values=cd.pick_list_values,
        )
