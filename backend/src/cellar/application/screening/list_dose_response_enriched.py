"""ListDoseResponseEnriched — dose-response curves with resolved names."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.screening.dose_response_enriched_reader import (
    DoseResponseEnrichedReader,
)
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.repository import (
    DoseResponseCurveRepository,
    ProtocolRepository,
    RunRepository,
)
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListDoseResponseEnrichedQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID


@dataclass(frozen=True)
class EnrichedDoseResponseCurve:
    curve: DoseResponseCurve
    registration_number: str | None
    molecule_name: str | None
    batch_number: str | None
    smiles: str | None
    synonyms: list[str]
    # The owning protocol's dose_unit. Used to label IC50 in callers.
    dose_unit: str


class ListDoseResponseEnriched:
    """Return dose-response curves for a run with resolved molecule/batch names.

    Delegates cross-context name resolution to DoseResponseEnrichedReader (infrastructure).
    """

    def __init__(
        self,
        uow: UnitOfWork,
        repo: DoseResponseCurveRepository,
        reader: DoseResponseEnrichedReader,
        run_repo: RunRepository,
        protocol_repo: ProtocolRepository,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._reader = reader
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo

    async def __call__(
        self,
        input: ListDoseResponseEnrichedQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[EnrichedDoseResponseCurve], DomainError]:
        require_same_workspace(auth, input.workspace_id)
        async with self._uow as uow:
            curves = await self._repo.find_by_run(input.workspace_id, input.run_id)

            mol_ids = list({c.molecule_id for c in curves})
            batch_ids = list({c.batch_id for c in curves})

            mol_info = await self._reader.resolve_molecules(input.workspace_id, mol_ids)
            batch_numbers = await self._reader.resolve_batch_numbers(
                input.workspace_id, batch_ids
            )

            run = await self._run_repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            dose_unit = "uM"
            if run is not None:
                protocol = await self._protocol_repo.find_by_id_in_workspace(
                    input.workspace_id, run.protocol_id
                )
                if protocol is not None:
                    dose_unit = protocol.dose_unit.value

            return Success(
                [
                    EnrichedDoseResponseCurve(
                        curve=c,
                        registration_number=(
                            mol_info[c.molecule_id].registration_number
                            if c.molecule_id in mol_info
                            else None
                        ),
                        molecule_name=(
                            mol_info[c.molecule_id].name if c.molecule_id in mol_info else None
                        ),
                        batch_number=batch_numbers.get(c.batch_id),
                        smiles=(
                            mol_info[c.molecule_id].smiles if c.molecule_id in mol_info else None
                        ),
                        synonyms=(
                            mol_info[c.molecule_id].synonyms if c.molecule_id in mol_info else []
                        ),
                        dose_unit=dose_unit,
                    )
                    for c in curves
                ]
            )
