"""Repository for CompoundFlag."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from cellar.domain.screening_assay.compound_flag import CompoundFlag, FlagType
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.compound_flag_model import (
    CompoundFlagModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyCompoundFlagRepository:
    """Persists CompoundFlag entities to PostgreSQL."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def list_by_protocol(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> list[CompoundFlag]:
        stmt = select(CompoundFlagModel).where(
            CompoundFlagModel.workspace_id == workspace_id,
            CompoundFlagModel.protocol_id == protocol_id,
        )
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def save(self, flag: CompoundFlag) -> None:
        existing = await self._uow.session.get(CompoundFlagModel, flag.id)
        if existing is not None:
            if existing.workspace_id != flag.workspace_id:
                from cellar.domain.shared.errors import AuthorizationError

                raise AuthorizationError("Cannot update CompoundFlag from a different workspace")
            self._update_model(existing, flag)
        else:
            model = self._to_model(flag)
            self._uow.session.add(model)

    @staticmethod
    def _update_model(model: CompoundFlagModel, flag: CompoundFlag) -> None:
        model.flag_type = flag.flag_type.value
        model.note = flag.note

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> CompoundFlag | None:
        """Load by PK scoped to workspace (used by admin hard-delete)."""
        stmt = select(CompoundFlagModel).where(
            CompoundFlagModel.id == id,
            CompoundFlagModel.workspace_id == workspace_id,
        )
        result = await self._uow.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def delete(self, workspace_id: uuid.UUID, flag_id: uuid.UUID) -> None:
        stmt = delete(CompoundFlagModel).where(
            CompoundFlagModel.id == flag_id,
            CompoundFlagModel.workspace_id == workspace_id,
        )
        await self._uow.session.execute(stmt)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(m: CompoundFlagModel) -> CompoundFlag:
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

    @staticmethod
    def _to_model(f: CompoundFlag) -> CompoundFlagModel:
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
