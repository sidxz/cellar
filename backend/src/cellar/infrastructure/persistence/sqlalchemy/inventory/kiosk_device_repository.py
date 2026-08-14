"""SQLAlchemy repository for KioskDevice aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update

from cellar.domain.inventory.kiosk_device import KioskDevice
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.kiosk_device_models import (
    KioskDeviceModel,
)


class SQLAlchemyKioskDeviceRepository(SQLAlchemyRepository[KioskDevice, KioskDeviceModel]):
    model_class = KioskDeviceModel

    async def find_by_workspace(self, workspace_id: uuid.UUID) -> list[KioskDevice]:
        stmt = (
            select(KioskDeviceModel)
            .where(KioskDeviceModel.workspace_id == workspace_id)
            .order_by(KioskDeviceModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def find_by_name(self, workspace_id: uuid.UUID, name: str) -> KioskDevice | None:
        stmt = select(KioskDeviceModel).where(
            KioskDeviceModel.workspace_id == workspace_id,
            KioskDeviceModel.name == name,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def find_active_by_token_hash(self, token_hash: str) -> KioskDevice | None:
        stmt = select(KioskDeviceModel).where(
            KioskDeviceModel.token_hash == token_hash,
            KioskDeviceModel.is_active.is_(True),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def touch_last_seen(self, device_id: uuid.UUID) -> None:
        # ponytail: raw UPDATE, no version bump — last_seen is telemetry;
        # rapid scans must not trade optimistic-concurrency conflicts.
        await self._session.execute(
            update(KioskDeviceModel)
            .where(KioskDeviceModel.id == device_id)
            .values(last_seen_at=func.now())
        )

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def _to_domain(self, model: KioskDeviceModel) -> KioskDevice:
        return KioskDevice(
            id=model.id,
            workspace_id=model.workspace_id,
            org_id=model.org_id,
            name=model.name,
            token_hash=model.token_hash,
            is_active=model.is_active,
            last_seen_at=model.last_seen_at,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: KioskDevice) -> KioskDeviceModel:
        return KioskDeviceModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            org_id=aggregate.org_id,
            name=aggregate.name,
            token_hash=aggregate.token_hash,
            is_active=aggregate.is_active,
            last_seen_at=aggregate.last_seen_at,
            created_by=aggregate.created_by,
            version=aggregate.version,
        )

    def _update_model(self, model: KioskDeviceModel, aggregate: KioskDevice) -> None:
        # org_id/name/token_hash/created_by are set once at KioskDevice.create()
        # and have no domain setter — excluded here, same rationale as
        # PlateLoan's owner_org_id/borrower_org_id/requested_by. last_seen_at
        # is intentionally NOT synced here — touch_last_seen() owns it via a
        # raw UPDATE that deliberately skips the version bump (see above).
        model.is_active = aggregate.is_active
