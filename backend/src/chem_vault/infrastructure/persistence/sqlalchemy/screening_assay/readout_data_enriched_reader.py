"""SQLAlchemy implementation of ReadoutDataEnrichedReader."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
)


class SQLAlchemyReadoutDataEnrichedReader:
    """Infrastructure-layer read model for enriched readout data queries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def resolve_molecule_registration_numbers(
        self, molecule_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        if not molecule_ids:
            return {}
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(MoleculeModel.id, MoleculeModel.registration_number).where(
                        MoleculeModel.id.in_(molecule_ids)
                    )
                )
            ).all()
            return {r.id: r.registration_number for r in rows}

    async def resolve_batch_numbers(
        self, batch_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        if not batch_ids:
            return {}
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(BatchModel.id, BatchModel.batch_number).where(
                        BatchModel.id.in_(batch_ids)
                    )
                )
            ).all()
            return {r.id: r.batch_number for r in rows}
