"""Repository for CDD plate sync tracking records.

Direct SQL repository (not a domain aggregate repository).
Maps CDD plate IDs to local RegisteredPlate IDs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert

from cellar.infrastructure.persistence.sqlalchemy.inventory.cdd_plate_import_models import (
    CddPlateSyncModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class CddPlateSyncRepository:
    """Tracks CDD plate ID -> local plate ID mappings per workspace/vault."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    @property
    def _session(self):
        return self._uow.session

    async def bulk_upsert(
        self,
        workspace_id: uuid.UUID,
        cdd_vault_id: str,
        mappings: list[tuple[int, uuid.UUID]],
    ) -> None:
        """Insert or update sync records.

        mappings = [(cdd_plate_id, plate_id), ...]
        On conflict (same workspace + vault + cdd_plate_id), updates ``updated_at``.
        """
        if not mappings:
            return

        now = datetime.now(UTC)
        rows = [
            {
                "id": uuid.uuid4(),
                "workspace_id": workspace_id,
                "cdd_vault_id": cdd_vault_id,
                "cdd_plate_id": cdd_plate_id,
                "plate_id": plate_id,
                "created_at": now,
                "updated_at": now,
            }
            for cdd_plate_id, plate_id in mappings
        ]

        stmt = insert(CddPlateSyncModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["workspace_id", "cdd_vault_id", "cdd_plate_id"],
            set_={"updated_at": now},
        )
        await self._session.execute(stmt)

    async def find_plate_id_by_cdd_plate_id(
        self,
        workspace_id: uuid.UUID,
        cdd_vault_id: str,
        cdd_plate_id: int,
    ) -> uuid.UUID | None:
        """Lookup internal plate_id for a CDD plate ID."""
        from sqlalchemy import select

        stmt = select(CddPlateSyncModel.plate_id).where(
            CddPlateSyncModel.workspace_id == workspace_id,
            CddPlateSyncModel.cdd_vault_id == cdd_vault_id,
            CddPlateSyncModel.cdd_plate_id == cdd_plate_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
