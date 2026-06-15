"""SQLAlchemy implementation of SarActivityProjectionRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, insert, select

from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
from cellar.domain.sar_analysis.sar_activity_projection import (
    SarActivityProjection,
    SarActivityProjectionStatus,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_models import (  # noqa: E501
    SarActivityProjectionModel,
    SarActivityValueModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemySarActivityProjectionRepository:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def save(self, projection: SarActivityProjection) -> None:
        session = self._uow.session
        existing = await session.get(SarActivityProjectionModel, projection.id)
        if existing is None:
            session.add(_to_model(projection))
        else:
            _apply_to_model(existing, projection)

    async def find_by_id(
        self, projection_id: UUID, *, workspace_id: UUID
    ) -> SarActivityProjection | None:
        session = self._uow.session
        stmt = select(SarActivityProjectionModel).where(
            SarActivityProjectionModel.id == projection_id,
            SarActivityProjectionModel.workspace_id == workspace_id,
        )
        model = (await session.execute(stmt)).scalar_one_or_none()
        return _to_domain(model) if model else None

    async def find_cached(
        self, *, membership_hash: str, channel_hash: str
    ) -> SarActivityProjection | None:
        session = self._uow.session
        stmt = (
            select(SarActivityProjectionModel)
            .where(
                SarActivityProjectionModel.membership_hash == membership_hash,
                SarActivityProjectionModel.channel_hash == channel_hash,
                SarActivityProjectionModel.status == SarActivityProjectionStatus.READY.value,
            )
            .order_by(SarActivityProjectionModel.completed_at.desc())
            .limit(1)
        )
        model = (await session.execute(stmt)).scalar_one_or_none()
        return _to_domain(model) if model else None

    async def write_values(self, projection_id: UUID, values: list[ActivityScalar]) -> None:
        session = self._uow.session
        BATCH = 1000
        rows = [
            {
                "projection_id": projection_id,
                "molecule_id": v.molecule_id,
                "scalar": v.scalar,
                "unit": v.unit,
                "qualifier": v.qualifier,
                "source": v.source,
                "snapshot": v.snapshot,
            }
            for v in values
        ]
        for i in range(0, len(rows), BATCH):
            await session.execute(insert(SarActivityValueModel), rows[i : i + BATCH])

    async def count_values(self, projection_id: UUID, *, workspace_id: UUID) -> int:
        session = self._uow.session
        stmt = (
            select(func.count())
            .select_from(SarActivityValueModel)
            .join(
                SarActivityProjectionModel,
                SarActivityProjectionModel.id == SarActivityValueModel.projection_id,
            )
            .where(
                SarActivityValueModel.projection_id == projection_id,
                SarActivityProjectionModel.workspace_id == workspace_id,
            )
        )
        return int((await session.execute(stmt)).scalar_one())


def _to_model(p: SarActivityProjection) -> SarActivityProjectionModel:
    return SarActivityProjectionModel(
        id=p.id,
        workspace_id=p.workspace_id,
        requested_by=p.requested_by,
        membership_hash=p.membership_hash,
        channel_hash=p.channel_hash,
        channel_spec=dict(p.channel_spec),
        requested_at=p.requested_at,
        status=p.status.value,
        started_at=p.started_at,
        completed_at=p.completed_at,
        error_message=p.error_message,
        value_count=p.value_count,
        version=p.version,
    )


def _apply_to_model(model: SarActivityProjectionModel, p: SarActivityProjection) -> None:
    model.status = p.status.value
    model.started_at = p.started_at
    model.completed_at = p.completed_at
    model.error_message = p.error_message
    model.value_count = p.value_count
    model.version = p.version


def _to_domain(model: SarActivityProjectionModel) -> SarActivityProjection:
    return SarActivityProjection(
        id=model.id,
        workspace_id=model.workspace_id,
        requested_by=model.requested_by,
        membership_hash=model.membership_hash,
        channel_hash=model.channel_hash,
        channel_spec=dict(model.channel_spec or {}),
        requested_at=model.requested_at,
        status=SarActivityProjectionStatus(model.status),
        started_at=model.started_at,
        completed_at=model.completed_at,
        error_message=model.error_message,
        value_count=model.value_count,
        version=model.version,
    )
