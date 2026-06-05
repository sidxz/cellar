"""ListReadoutDataEnriched — readout data with resolved molecule/batch names."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.screening.readout_data_enriched_reader import (
    ReadoutDataEnrichedReader,
)
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.repository import ReadoutDataRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListReadoutDataEnrichedQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID


@dataclass(frozen=True)
class EnrichedReadoutData:
    readout: ReadoutData
    registration_number: str | None
    molecule_name: str | None
    synonyms: list[str]
    batch_number: str | None
    smiles: str | None = None


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
        async with self._uow:
            data = await self._repo.find_by_run(input.workspace_id, input.run_id)

            mol_ids = list({rd.molecule_id for rd in data if rd.molecule_id})
            batch_ids = list({rd.batch_id for rd in data if rd.batch_id})

            mol_info = await self._reader.resolve_molecules(input.workspace_id, mol_ids)
            batch_map = await self._reader.resolve_batch_numbers(input.workspace_id, batch_ids)

            return Success(
                [
                    EnrichedReadoutData(
                        readout=rd,
                        registration_number=(
                            mol_info[rd.molecule_id].registration_number
                            if rd.molecule_id and rd.molecule_id in mol_info
                            else None
                        ),
                        molecule_name=(
                            mol_info[rd.molecule_id].name
                            if rd.molecule_id and rd.molecule_id in mol_info
                            else None
                        ),
                        synonyms=(
                            mol_info[rd.molecule_id].synonyms
                            if rd.molecule_id and rd.molecule_id in mol_info
                            else []
                        ),
                        smiles=(
                            mol_info[rd.molecule_id].smiles
                            if rd.molecule_id and rd.molecule_id in mol_info
                            else None
                        ),
                        batch_number=batch_map.get(rd.batch_id) if rd.batch_id else None,
                    )
                    for rd in data
                ]
            )
