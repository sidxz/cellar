"""SQLAlchemy implementation of BulkRegistrationItemReader."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chem_vault.application.chemical_registration.bulk_registration_item_reader import (
    BulkRegistrationItemPage,
    BulkRegistrationItemRow,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.bulk_registration_models import (
    BulkRegistrationItemModel,
)


class SQLAlchemyBulkRegistrationItemReader:
    """Read projection over bulk_registration_items, scoped by workspace + bulk_reg id."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_items(
        self,
        *,
        workspace_id: uuid.UUID,
        bulk_registration_id: uuid.UUID,
        action: str | None,
        limit: int,
        offset: int,
    ) -> BulkRegistrationItemPage:
        async with self._session_factory() as session:
            base = select(BulkRegistrationItemModel).where(
                BulkRegistrationItemModel.workspace_id == workspace_id,
                BulkRegistrationItemModel.bulk_registration_id == bulk_registration_id,
            )
            if action is not None:
                base = base.where(BulkRegistrationItemModel.action == action)

            total_stmt = select(func.count()).select_from(base.subquery())
            total = (await session.execute(total_stmt)).scalar_one()

            page_stmt = (
                base.order_by(BulkRegistrationItemModel.row_index)
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(page_stmt)).scalars().all()

            return BulkRegistrationItemPage(
                rows=[
                    BulkRegistrationItemRow(
                        id=r.id,
                        bulk_registration_id=r.bulk_registration_id,
                        row_index=r.row_index,
                        action=r.action,
                        success=r.success,
                        molecule_id=r.molecule_id,
                        molecule_name=r.molecule_name,
                        registration_number=r.registration_number,
                        batch_id=r.batch_id,
                        batch_number=r.batch_number,
                        error=r.error,
                        created_at=r.created_at,
                    )
                    for r in rows
                ],
                total=total,
            )
