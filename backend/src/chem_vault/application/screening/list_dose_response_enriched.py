"""ListDoseResponseEnriched — dose-response curves with resolved names."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_same_workspace
from chem_vault.application.screening.dose_response_enriched_reader import (
    DoseResponseEnrichedReader,
)
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.dose_response_curve import DoseResponseCurve
from chem_vault.domain.screening_assay.repository import DoseResponseCurveRepository
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListDoseResponseEnrichedQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID


@dataclass(frozen=True)
class EnrichedDoseResponseCurve:
    curve: DoseResponseCurve
    molecule_name: str | None
    batch_number: str | None


class ListDoseResponseEnriched:
    """Return dose-response curves for a run with resolved molecule/batch names.

    Delegates cross-context name resolution to DoseResponseEnrichedReader (infrastructure).
    """

    def __init__(
        self,
        uow: UnitOfWork,
        repo: DoseResponseCurveRepository,
        reader: DoseResponseEnrichedReader,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._reader = reader

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

            mol_names = await self._reader.resolve_molecule_names(mol_ids)
            batch_numbers = await self._reader.resolve_batch_numbers(batch_ids)

            return Success([
                EnrichedDoseResponseCurve(
                    curve=c,
                    molecule_name=mol_names.get(c.molecule_id),
                    batch_number=batch_numbers.get(c.batch_id),
                )
                for c in curves
            ])
