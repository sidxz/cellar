"""SQLAlchemy implementation of DoseResponseEnrichedReader."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chem_vault.application.screening.dose_response_enriched_reader import (
    MoleculeDisplayInfo,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeIdentifierModel,
    MoleculeModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
)


class SQLAlchemyDoseResponseEnrichedReader:
    """Infrastructure-layer read model for enriched dose-response queries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def resolve_molecules(
        self, molecule_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, MoleculeDisplayInfo]:
        if not molecule_ids:
            return {}
        async with self._session_factory() as session:
            mol_rows = (
                await session.execute(
                    select(
                        MoleculeModel.id,
                        MoleculeModel.registration_number,
                        MoleculeModel.name,
                        MoleculeModel.smiles,
                    ).where(MoleculeModel.id.in_(molecule_ids))
                )
            ).all()
            ident_rows = (
                await session.execute(
                    select(
                        MoleculeIdentifierModel.molecule_id,
                        MoleculeIdentifierModel.identifier,
                        MoleculeIdentifierModel.identifier_type,
                    ).where(MoleculeIdentifierModel.molecule_id.in_(molecule_ids))
                )
            ).all()

        synonyms_by_mol: dict[uuid.UUID, list[str]] = {}
        for mid, ident, ident_type in ident_rows:
            # Display synonyms are user-supplied custom names; vendor IDs and
            # InChI/InChIKey are not displayed in the DR table.
            if ident_type in ("custom", "synonym", "common_name"):
                synonyms_by_mol.setdefault(mid, []).append(ident)

        return {
            mid: MoleculeDisplayInfo(
                registration_number=reg or "",
                name=name or "",
                smiles=smiles,
                synonyms=synonyms_by_mol.get(mid, []),
            )
            for mid, reg, name, smiles in mol_rows
        }

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
            return {r[0]: r[1] for r in rows}
