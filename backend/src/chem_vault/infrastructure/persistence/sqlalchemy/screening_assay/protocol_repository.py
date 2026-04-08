"""SQLAlchemy repository for Protocol aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from chem_vault.domain.screening_assay.enums import (
    ConditionDataType,
    ProtocolStatus,
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
    ReadoutNormalization,
)
from chem_vault.domain.screening_assay.protocol import (
    ConditionDefinition,
    Protocol,
    ReadoutDefinition,
)
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ConditionDefinitionModel,
    ProtocolModel,
    ReadoutDefinitionModel,
    protocol_projects,
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
        domain = self._to_domain(model)
        self._uow.track(domain)
        return domain

    async def find_by_name(
        self, workspace_id: uuid.UUID, name: str
    ) -> Protocol | None:
        """Find a protocol by exact name within a workspace."""
        stmt = select(ProtocolModel).where(
            ProtocolModel.workspace_id == workspace_id,
            ProtocolModel.name == name,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        domain = self._to_domain(model)
        self._uow.track(domain)
        return domain

    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[Protocol]:
        """List all protocols in a workspace, newest first."""
        stmt = (
            select(ProtocolModel)
            .where(ProtocolModel.workspace_id == workspace_id)
            .order_by(ProtocolModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        protocols = []
        for model in result.scalars().all():
            domain = self._to_domain(model)
            self._uow.track(domain)
            protocols.append(domain)
        return protocols

    async def find_by_ids(
        self, workspace_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> list[Protocol]:
        """Bulk-fetch protocols by a list of IDs within a workspace."""
        if not ids:
            return []
        stmt = select(ProtocolModel).where(
            ProtocolModel.workspace_id == workspace_id,
            ProtocolModel.id.in_(ids),
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

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

        Defense-in-depth: only inserts if the protocol belongs to the workspace.
        """
        # Verify protocol belongs to workspace before inserting
        ownership_stmt = select(ProtocolModel.id).where(
            ProtocolModel.id == protocol_id,
            ProtocolModel.workspace_id == workspace_id,
        )
        ownership_result = await self._session.execute(ownership_stmt)
        if ownership_result.scalar_one_or_none() is None:
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
                select(ProtocolModel.id).where(
                    ProtocolModel.workspace_id == workspace_id
                )
            ),
        )
        await self._session.execute(stmt)

    async def find_by_project(
        self, workspace_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[Protocol]:
        """Return all protocols linked to a project, newest first."""
        subq = select(protocol_projects.c.protocol_id).where(
            protocol_projects.c.project_id == project_id
        )
        stmt = (
            select(ProtocolModel)
            .where(
                ProtocolModel.workspace_id == workspace_id,
                ProtocolModel.id.in_(subq),
            )
            .order_by(ProtocolModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        protocols = []
        for model in result.scalars().all():
            domain = self._to_domain(model)
            self._uow.track(domain)
            protocols.append(domain)
        return protocols

    async def find_project_ids(self, workspace_id: uuid.UUID, protocol_id: uuid.UUID) -> list[uuid.UUID]:
        """Return all project IDs linked to a given protocol, scoped to workspace."""
        from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.models import (
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
    # Mapping: SA model <-> domain aggregate
    # ------------------------------------------------------------------

    def _to_domain(self, model: ProtocolModel) -> Protocol:
        readout_defs = [
            ReadoutDefinition(
                id=rd.id,
                protocol_id=rd.protocol_id,
                name=rd.name,
                data_type=ReadoutDataType(rd.data_type),
                unit=rd.unit,
                aggregation=ReadoutAggregation(rd.aggregation),
                precision=rd.precision,
                normalization=ReadoutNormalization(rd.normalization),
                is_calculated=rd.is_calculated,
                calculation_formula=rd.calculation_formula,
                display_order=rd.display_order,
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

        return Protocol(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            description=model.description,
            protocol_type=ProtocolType(model.protocol_type),
            target_id=model.target_id,
            category=model.category,
            protocol_version=model.protocol_version,
            parent_protocol_id=model.parent_protocol_id,
            status=ProtocolStatus(model.status),
            created_by=model.created_by,
            readout_definitions=readout_defs,
            condition_definitions=condition_defs,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: Protocol) -> ProtocolModel:
        model = ProtocolModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            name=aggregate.name,
            description=aggregate.description,
            protocol_type=aggregate.protocol_type.value,
            target_id=aggregate.target_id,
            category=aggregate.category,
            protocol_version=aggregate.protocol_version,
            parent_protocol_id=aggregate.parent_protocol_id,
            status=aggregate.status.value,
            created_by=aggregate.created_by,
            version=aggregate.version,
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
        model.target_id = aggregate.target_id
        model.category = aggregate.category
        model.protocol_version = aggregate.protocol_version
        model.parent_protocol_id = aggregate.parent_protocol_id
        model.status = aggregate.status.value

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
        return ReadoutDefinitionModel(
            id=rd.id,
            protocol_id=rd.protocol_id,
            name=rd.name,
            data_type=rd.data_type.value,
            unit=rd.unit,
            aggregation=rd.aggregation.value,
            precision=rd.precision,
            normalization=rd.normalization.value,
            is_calculated=rd.is_calculated,
            calculation_formula=rd.calculation_formula,
            display_order=rd.display_order,
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
