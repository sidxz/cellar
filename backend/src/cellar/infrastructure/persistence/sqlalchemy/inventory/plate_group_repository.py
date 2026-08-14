"""SQLAlchemy repository for PlateGroup aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from cellar.domain.inventory.plate_group import PlateGroup
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    PlateGroupModel,
    RegisteredPlateModel,
)


class SQLAlchemyPlateGroupRepository(SQLAlchemyRepository[PlateGroup, PlateGroupModel]):
    model_class = PlateGroupModel

    # ------------------------------------------------------------------
    # Custom queries
    # ------------------------------------------------------------------

    async def find_by_workspace(
        self, workspace_id: uuid.UUID, *, owner_org_id: uuid.UUID | None = None
    ) -> list[PlateGroup]:
        stmt = select(PlateGroupModel).where(PlateGroupModel.workspace_id == workspace_id)
        if owner_org_id is not None:
            stmt = stmt.where(PlateGroupModel.owner_org_id == owner_org_id)
        stmt = stmt.order_by(PlateGroupModel.name)
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def find_children(
        self, workspace_id: uuid.UUID, parent_group_id: uuid.UUID
    ) -> list[PlateGroup]:
        stmt = (
            select(PlateGroupModel)
            .where(
                PlateGroupModel.workspace_id == workspace_id,
                PlateGroupModel.parent_group_id == parent_group_id,
            )
            .order_by(PlateGroupModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def find_by_name(
        self,
        workspace_id: uuid.UUID,
        owner_org_id: uuid.UUID,
        parent_group_id: uuid.UUID | None,
        name: str,
    ) -> PlateGroup | None:
        stmt = select(PlateGroupModel).where(
            PlateGroupModel.workspace_id == workspace_id,
            PlateGroupModel.owner_org_id == owner_org_id,
            PlateGroupModel.parent_group_id.is_(None)
            if parent_group_id is None
            else PlateGroupModel.parent_group_id == parent_group_id,
            PlateGroupModel.name == name,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain_tracked(model)

    async def count_plates_by_group(
        self, workspace_id: uuid.UUID, owner_org_id: uuid.UUID | None = None
    ) -> dict[uuid.UUID, int]:
        stmt = (
            select(RegisteredPlateModel.group_id, func.count())
            .where(
                RegisteredPlateModel.workspace_id == workspace_id,
                RegisteredPlateModel.group_id.is_not(None),
            )
            .group_by(RegisteredPlateModel.group_id)
        )
        if owner_org_id is not None:
            stmt = stmt.where(RegisteredPlateModel.owner_org_id == owner_org_id)
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        model = await self._session.get(PlateGroupModel, id)
        if model is not None and model.workspace_id == workspace_id:
            await self._session.delete(model)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def _to_domain(self, model: PlateGroupModel) -> PlateGroup:
        return PlateGroup(
            id=model.id,
            workspace_id=model.workspace_id,
            owner_org_id=model.owner_org_id,
            name=model.name,
            parent_group_id=model.parent_group_id,
            group_type=model.group_type,
            description=model.description,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: PlateGroup) -> PlateGroupModel:
        return PlateGroupModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            owner_org_id=aggregate.owner_org_id,
            name=aggregate.name,
            parent_group_id=aggregate.parent_group_id,
            group_type=aggregate.group_type,
            description=aggregate.description,
            created_by=aggregate.created_by,
            version=aggregate.version,
        )

    def _update_model(self, model: PlateGroupModel, aggregate: PlateGroup) -> None:
        model.owner_org_id = aggregate.owner_org_id
        model.name = aggregate.name
        model.parent_group_id = aggregate.parent_group_id
        model.group_type = aggregate.group_type
        model.description = aggregate.description
