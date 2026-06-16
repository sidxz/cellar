"""SaveDecompositionCollection — persist all matched molecules of a decomposition
run (optionally under the live grid filter) as a new collection.

Resolves the matched ``molecule_id``s via the same reader the ``/rows`` endpoint
uses (so the saved set equals the filtered total the table shows), then reuses the
``CreateCollection`` + ``AddMoleculesToCollection`` use cases (uuid refs). The
reused use cases enforce ``require_editor`` / workspace scoping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from returns.pipeline import is_successful
from returns.result import Failure, Result, Success

from cellar.application.research_organization.collection_membership import (
    AddMoleculesToCollection,
    AddMoleculesToCollectionCommand,
)
from cellar.application.research_organization.create_collection import (
    CreateCollection,
    CreateCollectionCommand,
)
from cellar.application.sar_analysis.decomposition_rows import DecompositionRowReader
from cellar.application.sar_analysis.repositories import (
    RGroupDecompositionRunRepository,
    SarActivityProjectionRepository,
)
from cellar.application.shared.molecule_resolver import MoleculeReference, RefType
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class SaveDecompositionCollectionInput:
    run_id: UUID
    workspace_id: UUID
    requested_by: UUID
    name: str
    project_id: UUID | None = None
    filter: dict[str, Any] | None = None
    projection_id: UUID | None = None


class SaveDecompositionCollection:
    def __init__(
        self,
        *,
        run_repository: RGroupDecompositionRunRepository,
        projection_repository: SarActivityProjectionRepository,
        reader: DecompositionRowReader,
        create_collection: CreateCollection,
        add_molecules: AddMoleculesToCollection,
        uow: UnitOfWork,
    ) -> None:
        self._repo = run_repository
        self._projections = projection_repository
        self._reader = reader
        self._create_collection = create_collection
        self._add_molecules = add_molecules
        self._uow = uow

    async def execute(
        self, payload: SaveDecompositionCollectionInput, auth: Any = None
    ) -> Result[UUID, DomainError]:
        async with self._uow:
            run = await self._repo.find_by_id(payload.run_id, workspace_id=payload.workspace_id)
            if run is None:
                return Failure(NotFoundError("RGroupDecompositionRun", str(payload.run_id)))
            # Validate projection ownership explicitly (mirrors FetchDecompositionRows)
            # so the activity-filter join never relies on UUID disjointness to stay
            # tenant-safe.
            if payload.projection_id is not None:
                projection = await self._projections.find_by_id(
                    payload.projection_id, workspace_id=payload.workspace_id
                )
                if projection is None:
                    return Failure(
                        NotFoundError("SarActivityProjection", str(payload.projection_id))
                    )
            ids = await self._reader.fetch_matched_ids(
                payload.run_id,
                workspace_id=payload.workspace_id,
                projection_id=payload.projection_id,
                filter=payload.filter,
            )

        create_result = await self._create_collection(
            CreateCollectionCommand(
                workspace_id=payload.workspace_id,
                name=payload.name,
                project_id=payload.project_id,
                created_by=payload.requested_by,
            ),
            auth=auth,
        )
        if not is_successful(create_result):
            return create_result  # propagate the DomainError Failure
        collection = create_result.unwrap()

        if ids:
            add_result = await self._add_molecules(
                AddMoleculesToCollectionCommand(
                    workspace_id=payload.workspace_id,
                    collection_id=collection.id,
                    refs=[MoleculeReference(value=str(i), ref_type=RefType.UUID) for i in ids],
                    added_by=payload.requested_by,
                ),
                auth=auth,
            )
            if not is_successful(add_result):
                return add_result  # propagate the DomainError Failure

        return Success(collection.id)
