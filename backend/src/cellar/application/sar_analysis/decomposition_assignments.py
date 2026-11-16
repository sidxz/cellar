"""Every R-group assignment of a finished decomposition run in one read.

The paged ``/rows`` read caps a page at ``MAX_PAGE_SIZE``; callers that join the
assignments onto their own rows (keyed by molecule) need them all at once.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.sar_analysis.decomposition_rows import DecompositionRowReader
from cellar.application.sar_analysis.repositories import RGroupDecompositionRunRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.async_job import AsyncJobStatus
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True)
class FetchDecompositionAssignmentsInput:
    run_id: UUID
    workspace_id: UUID


@dataclass(frozen=True)
class DecompositionAssignments:
    core_smiles: str
    labels: list[str]
    assignments: dict[UUID, dict[str, str]]


class FetchDecompositionAssignments:
    def __init__(
        self,
        *,
        repository: RGroupDecompositionRunRepository,
        reader: DecompositionRowReader,
        uow: UnitOfWork,
    ) -> None:
        self._repo = repository
        self._reader = reader
        self._uow = uow

    async def execute(
        self, payload: FetchDecompositionAssignmentsInput, auth: AuthContext | None = None
    ) -> Result[DecompositionAssignments, DomainError]:
        require_same_workspace(auth, payload.workspace_id)
        async with self._uow:
            run = await self._repo.find_by_id_in_workspace(payload.workspace_id, payload.run_id)
            if run is None:
                return Failure(NotFoundError("RGroupDecompositionRun", str(payload.run_id)))
            if run.status != AsyncJobStatus.READY:
                return Failure(ValidationError("This decomposition is not ready yet."))
            assignments = await self._reader.fetch_assignments(
                payload.run_id, workspace_id=payload.workspace_id
            )
        return Success(
            DecompositionAssignments(
                core_smiles=run.core_smiles,
                labels=list(run.rgroup_labels),
                assignments=assignments,
            )
        )
