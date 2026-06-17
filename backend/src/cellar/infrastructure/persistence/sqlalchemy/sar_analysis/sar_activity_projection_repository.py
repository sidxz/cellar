"""SQLAlchemy implementation of SarActivityProjectionRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, insert, select

from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection
from cellar.domain.shared.async_job import AsyncJobStatus
from cellar.infrastructure.persistence.sqlalchemy.base_repository import SQLAlchemyRepository
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_models import (  # noqa: E501
    SarActivityProjectionModel,
    SarActivityValueModel,
)


class SQLAlchemySarActivityProjectionRepository(
    SQLAlchemyRepository[SarActivityProjection, SarActivityProjectionModel]
):
    model_class = SarActivityProjectionModel

    def _to_domain(self, model: SarActivityProjectionModel) -> SarActivityProjection:
        return SarActivityProjection(
            id=model.id,
            workspace_id=model.workspace_id,
            requested_by=model.requested_by,
            membership_hash=model.membership_hash,
            channel_hash=model.channel_hash,
            channel_spec=dict(model.channel_spec or {}),
            requested_at=model.requested_at,
            status=AsyncJobStatus(model.status),
            started_at=model.started_at,
            completed_at=model.completed_at,
            error_message=model.error_message,
            value_count=model.value_count,
            version=model.version,
        )

    def _to_model(self, aggregate: SarActivityProjection) -> SarActivityProjectionModel:
        return SarActivityProjectionModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            requested_by=aggregate.requested_by,
            membership_hash=aggregate.membership_hash,
            channel_hash=aggregate.channel_hash,
            channel_spec=dict(aggregate.channel_spec),
            requested_at=aggregate.requested_at,
            status=aggregate.status.value,
            started_at=aggregate.started_at,
            completed_at=aggregate.completed_at,
            error_message=aggregate.error_message,
            value_count=aggregate.value_count,
            version=aggregate.version,
        )

    def _update_model(
        self, model: SarActivityProjectionModel, aggregate: SarActivityProjection
    ) -> None:
        # version is owned by the base save()'s optimistic-concurrency UPDATE.
        model.status = aggregate.status.value
        model.started_at = aggregate.started_at
        model.completed_at = aggregate.completed_at
        model.error_message = aggregate.error_message
        model.value_count = aggregate.value_count

    async def find_cached(
        self, *, workspace_id: UUID, membership_hash: str, channel_hash: str
    ) -> SarActivityProjection | None:
        stmt = (
            select(SarActivityProjectionModel)
            .where(
                SarActivityProjectionModel.workspace_id == workspace_id,
                SarActivityProjectionModel.membership_hash == membership_hash,
                SarActivityProjectionModel.channel_hash == channel_hash,
                SarActivityProjectionModel.status == AsyncJobStatus.READY.value,
            )
            .order_by(SarActivityProjectionModel.completed_at.desc())
            .limit(1)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def write_values(self, projection_id: UUID, values: list[ActivityScalar]) -> None:
        batch = 1000
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
        for i in range(0, len(rows), batch):
            await self._session.execute(insert(SarActivityValueModel), rows[i : i + batch])

    async def delete_values(self, projection_id: UUID) -> None:
        """Reset value rows before recompute, so a re-run (e.g. a Temporal retry)
        is idempotent and never collides on the (projection_id, molecule_id) PK."""
        await self._session.execute(
            sa_delete(SarActivityValueModel).where(
                SarActivityValueModel.projection_id == projection_id
            )
        )

    async def count_values(self, projection_id: UUID, *, workspace_id: UUID) -> int:
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
        return int((await self._session.execute(stmt)).scalar_one())
