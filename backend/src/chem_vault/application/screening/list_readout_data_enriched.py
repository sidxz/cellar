"""ListReadoutDataEnriched — readout data with resolved molecule/batch names."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_same_workspace
from chem_vault.application.screening.readout_data_enriched_reader import (
    ReadoutDataEnrichedReader,
)
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.readout_data import ReadoutData
from chem_vault.domain.screening_assay.repository import ReadoutDataRepository
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListReadoutDataEnrichedQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID


@dataclass(frozen=True)
class EnrichedReadoutData:
    readout: ReadoutData
    registration_number: str | None
    batch_number: str | None


class ListReadoutDataEnriched:
    """Return readout data for a run with resolved molecule/batch names.

    Delegates cross-context name resolution to ReadoutDataEnrichedReader (infrastructure).
    """

    def __init__(
        self,
        uow: UnitOfWork,
        repo: ReadoutDataRepository,
        reader: ReadoutDataEnrichedReader,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._reader = reader

    async def __call__(
        self,
        input: ListReadoutDataEnrichedQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[EnrichedReadoutData], DomainError]:
        require_same_workspace(auth, input.workspace_id)
        async with self._uow as uow:
            data = await self._repo.find_by_run(input.workspace_id, input.run_id)

            mol_ids = list({rd.molecule_id for rd in data if rd.molecule_id})
            batch_ids = list({rd.batch_id for rd in data if rd.batch_id})

            mol_map = await self._reader.resolve_molecule_registration_numbers(mol_ids)
            batch_map = await self._reader.resolve_batch_numbers(batch_ids)

            return Success([
                EnrichedReadoutData(
                    readout=rd,
                    registration_number=mol_map.get(rd.molecule_id) if rd.molecule_id else None,
                    batch_number=batch_map.get(rd.batch_id) if rd.batch_id else None,
                )
                for rd in data
            ])
