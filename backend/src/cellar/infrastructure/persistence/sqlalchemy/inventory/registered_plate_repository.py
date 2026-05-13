"""SQLAlchemy repository for RegisteredPlate aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from cellar.domain.inventory.enums import PlateStatus, PlateType
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.shared.enums import PlateFormat
from cellar.domain.shared.value_objects import Barcode
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import (
    escape_like,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    RegisteredPlateModel,
)


class SQLAlchemyRegisteredPlateRepository(
    SQLAlchemyRepository[RegisteredPlate, RegisteredPlateModel]
):
    model_class = RegisteredPlateModel

    # ------------------------------------------------------------------
    # Custom queries
    # ------------------------------------------------------------------

    async def find_by_barcode(
        self, workspace_id: uuid.UUID, barcode: str
    ) -> RegisteredPlate | None:
        stmt = select(RegisteredPlateModel).where(
            RegisteredPlateModel.workspace_id == workspace_id,
            RegisteredPlateModel.barcode == barcode,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        domain = self._to_domain(model)
        self._uow.track(domain)
        return domain

    async def find_by_location(
        self, workspace_id: uuid.UUID, storage_location_id: uuid.UUID
    ) -> list[RegisteredPlate]:
        stmt = (
            select(RegisteredPlateModel)
            .where(
                RegisteredPlateModel.workspace_id == workspace_id,
                RegisteredPlateModel.storage_location_id == storage_location_id,
            )
            .order_by(RegisteredPlateModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def find_children(
        self, workspace_id: uuid.UUID, parent_plate_id: uuid.UUID
    ) -> list[RegisteredPlate]:
        stmt = (
            select(RegisteredPlateModel)
            .where(
                RegisteredPlateModel.workspace_id == workspace_id,
                RegisteredPlateModel.parent_plate_id == parent_plate_id,
            )
            .order_by(RegisteredPlateModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def find_by_project(
        self, workspace_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[RegisteredPlate]:
        stmt = (
            select(RegisteredPlateModel)
            .where(
                RegisteredPlateModel.workspace_id == workspace_id,
                RegisteredPlateModel.project_id == project_id,
            )
            .order_by(RegisteredPlateModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def search(
        self,
        workspace_id: uuid.UUID,
        *,
        barcode: str | None = None,
        plate_label: str | None = None,
        plate_type: str | None = None,
        status: str | None = None,
        format: str | None = None,
        storage_location_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> list[RegisteredPlate]:
        stmt = select(RegisteredPlateModel).where(
            RegisteredPlateModel.workspace_id == workspace_id
        )
        if barcode is not None:
            stmt = stmt.where(
                RegisteredPlateModel.barcode.ilike(f"%{escape_like(barcode)}%", escape="\\")
            )
        if plate_label is not None:
            stmt = stmt.where(
                RegisteredPlateModel.plate_label.ilike(
                    f"%{escape_like(plate_label)}%", escape="\\"
                )
            )
        if plate_type is not None:
            stmt = stmt.where(RegisteredPlateModel.plate_type == plate_type)
        if status is not None:
            stmt = stmt.where(RegisteredPlateModel.status == status)
        if format is not None:
            stmt = stmt.where(RegisteredPlateModel.format == format)
        if storage_location_id is not None:
            stmt = stmt.where(RegisteredPlateModel.storage_location_id == storage_location_id)
        if project_id is not None:
            stmt = stmt.where(RegisteredPlateModel.project_id == project_id)
        stmt = stmt.order_by(RegisteredPlateModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        model = await self._session.get(RegisteredPlateModel, id)
        if model is not None and model.workspace_id == workspace_id:
            await self._session.delete(model)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def _to_domain(self, model: RegisteredPlateModel) -> RegisteredPlate:
        return RegisteredPlate(
            id=model.id,
            workspace_id=model.workspace_id,
            barcode=Barcode(value=model.barcode),
            plate_label=model.plate_label,
            format=PlateFormat(model.format),
            plate_type=PlateType(model.plate_type),
            registered_by=model.registered_by,
            status=PlateStatus(model.status),
            well_map=model.well_map if model.well_map is not None else {},
            storage_location_id=model.storage_location_id,
            parent_plate_id=model.parent_plate_id,
            project_id=model.project_id,
            template_id=model.template_id,
            notes=model.notes,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: RegisteredPlate) -> RegisteredPlateModel:
        return RegisteredPlateModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            barcode=aggregate.barcode.value,
            plate_label=aggregate.plate_label,
            format=aggregate.format.value,
            plate_type=aggregate.plate_type.value,
            registered_by=aggregate.registered_by,
            status=aggregate.status.value,
            well_map=aggregate.well_map if aggregate.well_map else None,
            storage_location_id=aggregate.storage_location_id,
            parent_plate_id=aggregate.parent_plate_id,
            project_id=aggregate.project_id,
            template_id=aggregate.template_id,
            notes=aggregate.notes,
            version=aggregate.version,
        )

    def _update_model(self, model: RegisteredPlateModel, aggregate: RegisteredPlate) -> None:
        model.barcode = aggregate.barcode.value
        model.plate_label = aggregate.plate_label
        model.format = aggregate.format.value
        model.plate_type = aggregate.plate_type.value
        model.status = aggregate.status.value
        model.well_map = aggregate.well_map if aggregate.well_map else None
        model.storage_location_id = aggregate.storage_location_id
        model.parent_plate_id = aggregate.parent_plate_id
        model.project_id = aggregate.project_id
        model.template_id = aggregate.template_id
        model.notes = aggregate.notes
