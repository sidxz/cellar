"""SQLAlchemy repository for MergeEvent entities.

MergeEvent is insert-only (not an AggregateRoot), so this does NOT extend
SQLAlchemyRepository — no optimistic concurrency, no version tracking.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chem_vault.domain.chemical_registration.enums import MergeReason
from chem_vault.domain.chemical_registration.merge_event import MergeEvent
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.disclosure_models import (
    MergeEventModel,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyMergeEventRepository:
    """Simple repository for append-only MergeEvent records."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    @property
    def _session(self) -> AsyncSession:
        return self._uow.session

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(model: MergeEventModel) -> MergeEvent:
        return MergeEvent(
            id=model.id,
            source_molecule_id=model.source_molecule_id,
            target_molecule_id=model.target_molecule_id,
            disclosure_request_id=model.disclosure_request_id,
            reason=MergeReason(model.reason),
            merged_by=model.merged_by,
            merged_at=model.merged_at,
            snapshot=model.snapshot,
            notes=model.notes,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_model(entity: MergeEvent) -> MergeEventModel:
        return MergeEventModel(
            id=entity.id,
            source_molecule_id=entity.source_molecule_id,
            target_molecule_id=entity.target_molecule_id,
            disclosure_request_id=entity.disclosure_request_id,
            reason=entity.reason.value,
            merged_by=entity.merged_by,
            merged_at=entity.merged_at,
            snapshot=entity.snapshot,
            notes=entity.notes,
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def find_by_id(self, id: uuid.UUID) -> MergeEvent | None:
        model = await self._session.get(MergeEventModel, id)
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_source(
        self, source_molecule_id: uuid.UUID
    ) -> list[MergeEvent]:
        stmt = select(MergeEventModel).where(
            MergeEventModel.source_molecule_id == source_molecule_id,
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def find_by_target(
        self, target_molecule_id: uuid.UUID
    ) -> list[MergeEvent]:
        stmt = select(MergeEventModel).where(
            MergeEventModel.target_molecule_id == target_molecule_id,
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def save(self, entity: MergeEvent) -> None:
        self._session.add(self._to_model(entity))
