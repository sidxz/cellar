"""ResolvePositionLabels: match a run's position labels to registered compounds again.

A label names a compound exactly when the instrument import would have suggested it:
the whole label, then the part before a "(...)", by registered identifier. The compound
takes its batch the way a layout file's Compound cell with an empty Batch cell does.
One answer comes back per distinct label, in the order first given; blank labels get
none. Writes nothing; filling the table's positions is the browser's job.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.screening.instrument_import_plan import LabelMoleculeLookup
from cellar.application.screening.layout_compound_resolver import (
    LayoutCompound,
    LayoutCompoundResolver,
)
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.screening_assay.repository import RunRepository
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError

MAX_POSITION_LABELS = 500


@dataclass(frozen=True)
class LabelMatch:
    # The label as given, trimmed.
    label: str
    # None when the label names no registered compound.
    compound: LayoutCompound | None


@dataclass(frozen=True, kw_only=True)
class ResolvePositionLabelsQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    labels: tuple[str, ...]


class ResolvePositionLabels:
    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        molecule_repo: MoleculeRepository,
        batch_repo: BatchRepository,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._molecule_repo = molecule_repo
        self._batch_repo = batch_repo

    async def __call__(
        self, input: ResolvePositionLabelsQuery, auth: AuthContext | None = None
    ) -> Result[tuple[LabelMatch, ...], DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        if len(input.labels) > MAX_POSITION_LABELS:
            return Failure(ValidationError(f"More than {MAX_POSITION_LABELS} labels were given"))

        async with self._uow:
            run = await self._run_repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))

            find_molecule = LabelMoleculeLookup(input.workspace_id, self._molecule_repo)
            compounds = LayoutCompoundResolver(
                input.workspace_id, self._molecule_repo, self._batch_repo
            )
            matches = []
            for label in dict.fromkeys(text for raw in input.labels if (text := raw.strip())):
                molecule = await find_molecule(label)
                compound = await compounds.for_molecule(molecule) if molecule is not None else None
                matches.append(LabelMatch(label, compound))

        return Success(tuple(matches))
