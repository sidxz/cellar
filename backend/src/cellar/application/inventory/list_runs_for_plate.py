"""ListRunsForPlate — runs that carry a given inventory plate, newest first (S15 §5.4)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.inventory.plate_runs_reader import PlateRunRow, PlateRunsReader
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.repository import RegisteredPlateRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class ListRunsForPlateQuery(Query):
    workspace_id: uuid.UUID
    plate_id: uuid.UUID


class ListRunsForPlate:
    """Same guard + visibility sequence as ``GetPlate``, then the read model."""

    def __init__(
        self,
        uow: UnitOfWork,
        plate_repo: RegisteredPlateRepository,
        visibility: PlateVisibilityService,
        reader: PlateRunsReader,
    ) -> None:
        self._uow = uow
        self._plate_repo = plate_repo
        self._visibility = visibility
        self._reader = reader

    async def __call__(
        self, input: ListRunsForPlateQuery, auth: AuthContext | None = None
    ) -> Result[list[PlateRunRow], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            plate = await self._plate_repo.find_by_id_in_workspace(
                input.workspace_id, input.plate_id
            )
            if plate is None:
                return Failure(NotFoundError("RegisteredPlate", str(input.plate_id)))
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            borrowed = await self._visibility.borrowed_plate_ids(input.workspace_id, auth)
            if not self._visibility.can_view(plate, auth, excluded, borrowed):
                # No existence leak — a hidden plate 404s exactly like a missing one.
                return Failure(NotFoundError("RegisteredPlate", str(input.plate_id)))
            return Success(await self._reader.runs_for_plate(input.workspace_id, input.plate_id))
