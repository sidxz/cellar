"""GetMoleculeTestCounts query — count distinct protocols each molecule has been tested in."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import DoseResponseCurveRepository


@dataclass(frozen=True)
class GetMoleculeTestCountsQuery:
    workspace_id: uuid.UUID
    molecule_ids: list[uuid.UUID] = field(default_factory=list)
    project_id: uuid.UUID | None = None


class GetMoleculeTestCounts:
    """Query: count distinct protocols each molecule has been tested in.

    Uses the dose_response_curve → run → protocol join path.  When
    ``project_id`` is supplied, only protocols linked to that project are
    counted.  Molecules with no DR curves are returned with count=0.
    """

    def __init__(self, uow: UnitOfWork, dr_curve_repo: DoseResponseCurveRepository) -> None:
        self._uow = uow
        self._repo = dr_curve_repo

    async def execute(
        self,
        q: GetMoleculeTestCountsQuery,
        auth: AuthContext | None = None,
    ) -> dict[uuid.UUID, int]:
        require_workspace_role(auth, "viewer")
        if not q.molecule_ids:
            return {}
        async with self._uow:
            return await self._repo.count_distinct_protocols_per_molecule(
                workspace_id=q.workspace_id,
                molecule_ids=q.molecule_ids,
                project_id=q.project_id,
            )
