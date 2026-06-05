"""Repository for CompoundFlag."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.screening_assay.compound_flag import CompoundFlag, FlagType
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    EntityRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.compound_flag_model import (
    CompoundFlagModel,
)


class SQLAlchemyCompoundFlagRepository(EntityRepository[CompoundFlag, CompoundFlagModel]):
    """Persists CompoundFlag entities to PostgreSQL."""

    model_class = CompoundFlagModel

    async def list_by_protocol(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> list[CompoundFlag]:
        stmt = select(CompoundFlagModel).where(
            CompoundFlagModel.workspace_id == workspace_id,
            CompoundFlagModel.protocol_id == protocol_id,
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    def _to_domain(self, m: CompoundFlagModel) -> CompoundFlag:
        return CompoundFlag(
            id=m.id,
            workspace_id=m.workspace_id,
            molecule_id=m.molecule_id,
            protocol_id=m.protocol_id,
            flagged_by=m.flagged_by,
            flag_type=FlagType(m.flag_type),
            note=m.note,
            created_at=m.created_at,
        )

    def _to_model(self, f: CompoundFlag) -> CompoundFlagModel:
        return CompoundFlagModel(
            id=f.id,
            workspace_id=f.workspace_id,
            molecule_id=f.molecule_id,
            protocol_id=f.protocol_id,
            flagged_by=f.flagged_by,
            flag_type=f.flag_type.value,
            note=f.note,
            created_at=f.created_at,
        )

    def _update_model(self, model: CompoundFlagModel, flag: CompoundFlag) -> None:
        model.flag_type = flag.flag_type.value
        model.note = flag.note
