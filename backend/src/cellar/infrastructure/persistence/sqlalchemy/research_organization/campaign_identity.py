from __future__ import annotations

import uuid

from sqlalchemy import or_, select

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import MoleculeModel
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyCampaignIdentityReader:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def matching_ids(
        self, workspace_id: uuid.UUID, molecule_ids: list[uuid.UUID], search: str
    ) -> set[uuid.UUID]:
        matches: set[uuid.UUID] = set()
        # Bound IN lists; no per-compound reads or full molecule hydration.
        for offset in range(0, len(molecule_ids), 1000):
            statement = select(MoleculeModel.id).where(
                MoleculeModel.workspace_id == workspace_id,
                MoleculeModel.id.in_(molecule_ids[offset : offset + 1000]),
                or_(
                    MoleculeModel.registration_number.icontains(search, autoescape=True),
                    MoleculeModel.name.icontains(search, autoescape=True),
                ),
            )
            result = await self._uow.session.execute(statement)
            matches.update(result.scalars())
        return matches
