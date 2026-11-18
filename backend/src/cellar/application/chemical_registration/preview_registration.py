"""PreviewRegistration — what POST /molecules WOULD do for a batch of inputs.

ADVISORY ONLY. Runs the same structure processor and the same classifier as
``RegisterMolecule`` inside a read-only transaction and commits nothing. A
registration landing between this preview and the real call can change the
answer; ``POST /molecules`` stays the authority via its single-UoW
read-branch-write. Deliberately no locking, reservations or preview tokens —
a stale forecast the real call corrects is the correct behaviour.

In practice the forecast is registered / deduplicated / disclosed / conflict;
merge_candidate only arises in a race on the disclosure path.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Literal

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_authenticated, require_same_workspace
from cellar.application.chemical_registration.protocols import StructureProcessorProtocol
from cellar.application.chemical_registration.registration_classifier import (
    classify_disclosed,
    classify_undisclosed,
    collect_identifiers,
)
from cellar.application.chemical_registration.row_batch import classify_row_batch, row_batch_ids
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.enums import RegistrationAction
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.shared.errors import DomainError, ValidationError

# find_by_inchi_key is one indexed read per item; keep a batch to something a
# wizard page or an API caller can reasonably wait on.
MAX_PREVIEW_ITEMS = 500


@dataclass(frozen=True, kw_only=True)
class PreviewRegistrationItem:
    name: str | None
    smiles: str | None  # None = the caller intends an undisclosed registration
    external_ids: list[str] = field(default_factory=list)
    # The row's batch IDs; when given, the forecast also says what happens to its batch.
    batch_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class PreviewRegistrationQuery(Query):
    workspace_id: uuid.UUID
    items: list[PreviewRegistrationItem]


@dataclass(frozen=True)
class RegistrationPreviewItem:
    index: int
    action: RegistrationAction | None  # None when the structure could not be processed
    matched_molecule_id: uuid.UUID | None = None
    conflict_reason: str | None = None
    error: str | None = None
    # What the compound was classified by (InChIKey, or its identifiers when
    # undisclosed) — rows with the same key are the same compound.
    compound_key: str | None = None
    batch_action: Literal["new", "existing", "problem"] | None = None
    matched_batch_number: str | None = None
    batch_problem: str | None = None


@dataclass(frozen=True)
class PreviewRegistrationOutcome:
    items: list[RegistrationPreviewItem]


class PreviewRegistration:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: MoleculeRepository,
        structure_processor: StructureProcessorProtocol,
        batch_repo: BatchRepository | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._processor = structure_processor
        self._batch_repo = batch_repo

    async def __call__(
        self,
        query: PreviewRegistrationQuery,
        auth: AuthContext | None = None,
    ) -> Result[PreviewRegistrationOutcome, DomainError]:
        require_authenticated(auth)
        require_same_workspace(auth, query.workspace_id)
        if len(query.items) > MAX_PREVIEW_ITEMS:
            return Failure(
                ValidationError(
                    f"Preview at most {MAX_PREVIEW_ITEMS} items per request "
                    f"({len(query.items)} given)"
                )
            )

        results: list[RegistrationPreviewItem] = []
        # Read-only: the UoW is entered for a consistent session and exited
        # without commit.
        async with self._uow:
            for index, item in enumerate(query.items):
                results.append(await self._forecast(index, item, query.workspace_id))
        return Success(PreviewRegistrationOutcome(items=results))

    async def _forecast(
        self, index: int, item: PreviewRegistrationItem, workspace_id: uuid.UUID
    ) -> RegistrationPreviewItem:
        # Same rule as RegisterMolecule / bulk registration: a given name is promoted
        # to an identifier; an absent name (auto-named row) is not.
        identifiers = collect_identifiers(
            item.name, item.external_ids, promote_name=bool(item.name)
        )

        if item.smiles is None:
            forecast = await classify_undisclosed(self._repo, workspace_id, identifiers)
            compound_key = "ids:" + "|".join(sorted(identifiers)) if identifiers else None
        else:
            # RDKit work is synchronous and ~ms per structure; 500 in a row would
            # stall the single uvicorn worker, so run it off the event loop.
            processed = await asyncio.to_thread(self._processor.process, item.smiles)
            if isinstance(processed, Failure):
                return RegistrationPreviewItem(index, None, error=str(processed.failure()))
            inchi_key = processed.unwrap().structure.inchi_key
            if inchi_key is None:
                return RegistrationPreviewItem(
                    index, None, error="Structure processor returned no InChI key"
                )
            forecast = await classify_disclosed(
                self._repo, workspace_id, inchi_key, identifiers, detect_undisclosed=True
            )
            compound_key = inchi_key

        matched_id = forecast.matched_molecule.id if forecast.matched_molecule else None
        batch_action, batch_number, batch_problem = await self._forecast_batch(
            workspace_id, matched_id, item.batch_ids
        )
        return RegistrationPreviewItem(
            index,
            forecast.action,
            matched_molecule_id=matched_id,
            conflict_reason=forecast.conflict_reason,
            compound_key=compound_key,
            batch_action=batch_action,
            matched_batch_number=batch_number,
            batch_problem=batch_problem,
        )

    async def _forecast_batch(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID | None, batch_ids: list[str]
    ) -> tuple[Literal["new", "existing", "problem"] | None, str | None, str | None]:
        """Same rule as the import (row_batch.classify_row_batch). Database only:
        rows of one file are grouped by the caller via ``compound_key``."""
        if not batch_ids or self._batch_repo is None:
            return None, None, None
        match = await classify_row_batch(
            self._batch_repo,
            workspace_id,
            molecule_id,
            row_batch_ids([{"identifier": b, "source": ""} for b in batch_ids]),
        )
        if match.kind == "existing" and match.batch is not None:
            return "existing", match.batch.batch_number.value, None
        return match.kind, None, match.problem
