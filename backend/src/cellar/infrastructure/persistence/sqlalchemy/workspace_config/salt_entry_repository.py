"""SQLAlchemy repository for SaltEntry aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from cellar.domain.workspace_config.salt_entry import SaltEntry
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.models import (
    SaltEntryModel,
)


class SQLAlchemySaltEntryRepository(SQLAlchemyRepository[SaltEntry, SaltEntryModel]):
    model_class = SaltEntryModel

    def _to_domain(self, model: SaltEntryModel) -> SaltEntry:
        return SaltEntry(
            id=model.id,
            workspace_id=model.workspace_id,
            code=model.code,
            name=model.name,
            smiles=model.smiles,
            molecular_weight=model.molecular_weight,
            is_default=model.is_default,
            is_active=model.is_active,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, aggregate: SaltEntry) -> SaltEntryModel:
        return SaltEntryModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            code=aggregate.code,
            name=aggregate.name,
            smiles=aggregate.smiles,
            molecular_weight=aggregate.molecular_weight,
            is_default=aggregate.is_default,
            is_active=aggregate.is_active,
            version=aggregate.version,
        )

    def _update_model(self, model: SaltEntryModel, aggregate: SaltEntry) -> None:
        model.name = aggregate.name
        model.smiles = aggregate.smiles
        model.molecular_weight = aggregate.molecular_weight
        model.is_default = aggregate.is_default
        model.is_active = aggregate.is_active

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        active_only: bool = True,
    ) -> list[SaltEntry]:
        stmt = select(SaltEntryModel).where(SaltEntryModel.workspace_id == workspace_id)
        if active_only:
            stmt = stmt.where(SaltEntryModel.is_active.is_(True))
        stmt = stmt.order_by(SaltEntryModel.code)
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def find_by_code(self, workspace_id: uuid.UUID, code: str) -> SaltEntry | None:
        stmt = select(SaltEntryModel).where(
            SaltEntryModel.workspace_id == workspace_id,
            SaltEntryModel.code == code,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def find_by_smiles(self, workspace_id: uuid.UUID, smiles: str) -> SaltEntry | None:
        stmt = select(SaltEntryModel).where(
            SaltEntryModel.workspace_id == workspace_id,
            SaltEntryModel.smiles == smiles,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = delete(SaltEntryModel).where(
            SaltEntryModel.workspace_id == workspace_id,
            SaltEntryModel.id == id,
        )
        await self._session.execute(stmt)
