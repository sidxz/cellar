"""Repository for CDD molecule sync tracking records.

This is a direct SQL repository (not a domain aggregate repository).
It manages the mapping between CDD molecule IDs and local molecule IDs
to support sync imports.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from dateutil.parser import isoparse
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

from .cdd_molecule_sync_model import (
    CddMoleculeSyncModel,
)


class CddMoleculeSyncRepository:
    """Tracks CDD molecule ID -> local molecule ID mappings per workspace/vault."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    @property
    def _session(self):
        return self._uow.session

    async def get_known_cdd_ids(self, workspace_id: uuid.UUID, cdd_vault_id: str) -> set[int]:
        """Return the set of CDD molecule IDs already synced for this workspace/vault."""
        stmt = (
            select(CddMoleculeSyncModel.cdd_molecule_id)
            .where(CddMoleculeSyncModel.workspace_id == workspace_id)
            .where(CddMoleculeSyncModel.cdd_vault_id == cdd_vault_id)
        )
        result = await self._session.execute(stmt)
        return {row[0] for row in result.all()}

    async def get_last_modified_at(
        self, workspace_id: uuid.UUID, cdd_vault_id: str
    ) -> datetime | None:
        """Return the latest cdd_modified_at for this workspace/vault, or None if empty."""
        stmt = (
            select(func.max(CddMoleculeSyncModel.cdd_modified_at))
            .where(CddMoleculeSyncModel.workspace_id == workspace_id)
            .where(CddMoleculeSyncModel.cdd_vault_id == cdd_vault_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def bulk_upsert(
        self,
        workspace_id: uuid.UUID,
        cdd_vault_id: str,
        mappings: list[tuple[int, uuid.UUID, str | None]],
    ) -> None:
        """Insert or update sync records.

        mappings = [(cdd_molecule_id, molecule_id, cdd_modified_at_iso), ...]
        On conflict (same workspace + vault + cdd_molecule_id), updates
        ``last_synced_at``, ``cdd_modified_at``, and ``updated_at``.
        """
        if not mappings:
            return

        # Deduplicate: a molecule with N batches produces N identical entries.
        unique: dict[int, tuple[uuid.UUID, str | None]] = {}
        for cdd_mol_id, mol_id, mod_at in mappings:
            unique[cdd_mol_id] = (mol_id, mod_at)

        now = datetime.now(UTC)
        rows = [
            {
                "id": uuid.uuid4(),
                "workspace_id": workspace_id,
                "cdd_vault_id": cdd_vault_id,
                "cdd_molecule_id": cdd_mol_id,
                "molecule_id": mol_id,
                "cdd_modified_at": isoparse(mod_at) if mod_at else None,
                "last_synced_at": now,
                "created_at": now,
                "updated_at": now,
            }
            for cdd_mol_id, (mol_id, mod_at) in unique.items()
        ]

        stmt = insert(CddMoleculeSyncModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_cdd_sync_ws_vault_mol",
            set_={
                "cdd_modified_at": stmt.excluded.cdd_modified_at,
                "last_synced_at": now,
                "updated_at": now,
            },
        )
        await self._session.execute(stmt)
